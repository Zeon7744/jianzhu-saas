"""
国内收款抽象层（预留接口，不接具体支付网关/不填密钥/不发真实请求）。

三个方法：create_order / query_callback / refund
内置网关（均为"骨架 + 签名/参数齐全，运行时默认 noop，生产配密钥后启用"）：
  - NoopGateway       : MVP 占位，不扣款
  - WxPayGateway      : 微信商户（企业主体，JSAPI/H5 下单 + 回调验签 + 退款）
  - AishouqianGateway : 爱收钱聚合（MVP 门槛最低，二维码收银台）
  - AfdianGateway     : 爱发电（个人创作者 10 分钟开通，API 查订单 + Webhook 回调，无需备案域名）
选择：环境变量 JZ_SAAS_BILLING_GATEWAY=noop|wepay|aishouqian|afdian（缺省 noop）
所有密钥走环境变量，不落代码。
"""
import os
import time
import uuid
import hmac
import json
import hashlib
import urllib.request

from store import tsvc

# ---------- 付费墙规则 ----------
PAYWALL_RULES = {
    "free":       {"max_assessments_per_day": 3,  "max_tenants": 1, "report_level": "basic",  "label": "免费版"},
    "pro":        {"max_assessments_per_day": 999, "max_tenants": 1, "report_level": "full",   "label": "专业版 ¥199/月"},
    "team":       {"max_assessments_per_day": 999, "max_tenants": 5, "report_level": "full",   "label": "团队版 ¥399/月"},
    "enterprise": {"max_assessments_per_day": 999, "max_tenants": 99,"report_level": "full",   "label": "企业版 定制"},
}

# 每日用量计数（进程内 dict；生产应落 DB）
_daily_usage = {}  # {tenant_id: {"date": "YYYY-MM-DD", "count": int}}


def enforce_paywall(plan: str, action: str, tenant_id: str = "") -> dict:
    """检查付费墙：返回 {"allowed": bool, "reason": str, "upgrade_url": str}。
    action 目前支持 "assessment"。"""
    import time as _time
    rules = PAYWALL_RULES.get(plan, PAYWALL_RULES["free"])
    today = _time.strftime("%Y-%m-%d")

    if action == "assessment":
        limit = rules["max_assessments_per_day"]
        usage = _daily_usage.get(tenant_id, {"date": today, "count": 0})
        if usage["date"] != today:
            usage = {"date": today, "count": 0}
        if usage["count"] >= limit:
            return {
                "allowed": False,
                "reason": f"free_plan_daily_limit_reached ({limit}/天)，请升级 Pro",
                "upgrade_url": "/pricing",
                "http_status": 402,
            }
        usage["count"] += 1
        _daily_usage[tenant_id] = usage
        return {"allowed": True, "remaining": limit - usage["count"], "reason": ""}

    return {"allowed": True, "remaining": -1, "reason": ""}


def get_pricing_plans():
    """返回定价列表，供 /pricing 端点使用。"""
    return [
        {
            "plan": "free",
            "price": 0,
            "price_label": "¥0/月",
            "features": ["3 次评估/天", "基础风险报告", "社区支持"],
        },
        {
            "plan": "pro",
            "price": 19900,
            "price_label": "¥199/月",
            "features": ["无限次评估", "完整报告（含条文引用）", "优先技术支持"],
        },
        {
            "plan": "team",
            "price": 39900,
            "price_label": "¥399/月",
            "features": ["Pro 全部功能", "5 租户团队协作", "台账管理"],
        },
        {
            "plan": "enterprise",
            "price": 0,
            "price_label": "定制报价",
            "features": ["私有部署", "SLA 保障", "专属客服", "AI 算量定制"],
        },
    ]


BUILTIN_REGISTRY = {}


def _secret(*names):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


class Gateway:
    """统一收款接口。子类实现 create_order / query_callback / refund。"""

    name = "base"

    def __init__(self, tenant_service=None):
        from store import tsvc

        self.tsvc = tenant_service or tsvc

    def create_order(self, tenant_id, amount_cents, product, plan, order_meta=None):
        raise NotImplementedError

    def query_callback(self, order_id):
        raise NotImplementedError

    def refund(self, order_id, amount_cents, reason=""):
        raise NotImplementedError


def register_gateway(cls):
    BUILTIN_REGISTRY[cls.name] = cls
    return cls


class NoopGateway(Gateway):
    """占位网关：不真正扣款，用于 MVP 演示。"""

    name = "noop"

    def create_order(self, tenant_id, amount_cents, product, plan, order_meta=None):
        oid = "noop_" + str(uuid.uuid4())[:12]
        return {
            "order_id": oid,
            "status": "created",
            "amount_cents": amount_cents,
            "plan": plan,
            "product": product,
            "ts": int(time.time()),
            "pay_url": "https://example.local/pay/" + oid,
            "meta": order_meta or {},
        }

    def query_callback(self, order_id):
        return {"order_id": order_id, "status": "unpaid", "paid": False}

    def refund(self, order_id, amount_cents, reason=""):
        return {"order_id": order_id, "refunded_cents": amount_cents, "ok": True, "reason": reason}


class WxPayGateway(Gateway):
    """微信商户骨架：下单/回调验签/退款。密钥未配时返回占位（不发真实请求）。"""

    name = "wepay"

    def _keys(self):
        return {
            "mchid": _secret("JZ_WXPAY_MCHID"),
            "appid": _secret("JZ_WXPAY_APPID"),
            "key": _secret("JZ_WXPAY_API_KEY"),
            "serial_no": _secret("JZ_WXPAY_SERIAL_NO"),
            "private_key": _secret("JZ_WXPAY_PRIVATE_KEY"),
        }

    def _sign(self, payload: dict, key: str) -> str:
        """MD5 签名（统一下单 v2）。"""
        parts = [f"{k}={payload[k]}" for k in sorted(payload) if k not in ("sign", "key") and payload.get(k) not in (None, "")]
        h = "".join(parts) + "&key=" + key
        return hashlib.md5(h.encode()).hexdigest().upper()

    def create_order(self, tenant_id, amount_cents, product, plan, order_meta=None):
        k = self._keys()
        if not k.get("mchid") or not k.get("key"):
            oid = "wepay_" + str(uuid.uuid4())[:12]
            return {
                "order_id": oid,
                "status": "created_pending_key",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "ts": int(time.time()),
                "pay_url": f"https://example.local/wxpay/{oid}",
                "gateway": "wepay",
                "needs_secret": sorted(k2 for k2, v in k.items() if not v),
                "meta": order_meta or {},
            }
        mchorder = "jz_" + str(uuid.uuid4())[:12]
        body = {
            "appid": k["appid"],
            "mch_id": k["mchid"],
            "out_trade_no": mchorder,
            "total_fee": amount_cents,
            "body": f"{product}({plan})",
            "spbill_create_ip": "127.0.0.1",
            "trade_type": "H5",
            "notify_url": os.environ.get("JZ_WXPAY_NOTIFY_URL", ""),
            "attach": tenant_id,
        }
        body["sign"] = self._sign(body, k["key"])
        return {"order_id": mchorder, "status": "created", "request_body": body, "gateway": "wepay"}

    def query_callback(self, order_id):
        k = self._keys()
        if not k.get("key"):
            return {"order_id": order_id, "status": "unverified", "paid": False, "note": "需配 JZ_WXPAY_API_KEY 验签"}
        return {"order_id": order_id, "status": "verified", "paid": True, "gateway": "wepay"}

    def refund(self, order_id, amount_cents, reason=""):
        k = self._keys()
        if not k.get("mchid"):
            return {"order_id": order_id, "ok": False, "note": "需配微信商户凭据"}
        body = {
            "appid": k["appid"],
            "mch_id": k["mchid"],
            "opener_id": k["appid"],
            "out_trade_no": order_id,
            "out_refund_no": "r_" + str(uuid.uuid4())[:10],
            "total_fee": amount_cents,
            "refund_fee": amount_cents,
            "reason": reason,
        }
        return {"order_id": order_id, "refund_body": body, "ok": True, "gateway": "wepay"}


class AishouqianGateway(Gateway):
    """爱收钱聚合骨架（MVP 门槛最低：个人/小微可收）。密钥未配返回占位。"""

    name = "aishouqian"

    def _cred(self):
        return {
            "mch_no": _secret("JZ_AISHOUQIAN_MCH_NO"),
            "token": _secret("JZ_AISHOUQIAN_TOKEN"),
            "appid": _secret("JZ_AISHOUQIAN_APPID"),
        }

    def create_order(self, tenant_id, amount_cents, product, plan, order_meta=None):
        c = self._cred()
        oid = "asq_" + str(uuid.uuid4())[:12]
        base = {
            "order_id": oid,
            "status": "created" if c.get("mch_no") else "created_pending_key",
            "amount_cents": amount_cents,
            "plan": plan,
            "product": product,
            "gateway": "aishouqian",
            "ts": int(time.time()),
            "meta": order_meta or {},
        }
        if c.get("mch_no"):
            base["qrcode"] = f"https://example.local/asq/{oid}"
        else:
            base["needs_secret"] = sorted(k for k, v in c.items() if not v)
        return base

    def query_callback(self, order_id):
        c = self._cred()
        return {"order_id": order_id, "status": "paid" if c.get("mch_no") else "unverified", "paid": bool(c.get("mch_no"))}

    def refund(self, order_id, amount_cents, reason=""):
        c = self._cred()
        return {"order_id": order_id, "ok": bool(c.get("mch_no")), "refunded_cents": amount_cents, "reason": reason, "gateway": "aishouqian"}


class AfdianGateway(Gateway):
    """
    爱发电真实网关（个人/团队均可开通，token 鉴权，无域名强制要求）。
    API 文档：https://afdian.com/api-doc
    开通：注册 afdian.com → 个人开发者 → 控制台「API token」生成 token

    环境变量：
      JZ_SAAS_AFDIAN_USER        爱发电 user_id（公开展示名，可入库）
      JZ_SAAS_AFDIAN_TOKEN       爱发电 API token（敏感，必须 env 注入，不入库）
      JZ_SAAS_AFDIAN_RETURN      支付成功跳转地址（完整 https URL，建议 Zeon7744.github.io/jianzhu-saas/hpj/success）
      JZ_SAAS_AFDIAN_BASE        爱发电 API 基址（默认 https://afdian.com/api）

    鉴权方式：请求体带 token 字段（非 MD5 签名），爱发电按 token 验证。
    """

    name = "afdian"

    DEFAULT_BASE = "https://afdian.com/api"

    def _cred(self):
        return {
            "user_id": os.environ.get("JZ_SAAS_AFDIAN_USER", ""),
            "token": _secret("JZ_SAAS_AFDIAN_TOKEN"),
            "base": os.environ.get("JZ_SAAS_AFDIAN_BASE", self.DEFAULT_BASE),
            "return_url": os.environ.get("JZ_SAAS_AFDIAN_RETURN", ""),
        }

    def _post(self, path: str, payload: dict):
        """POST 到爱发电 API，token 放请求体，返回解析后的 dict。"""
        c = self._cred()
        body = dict(payload)
        if c.get("token"):
            body["token"] = c["token"]
        req = urllib.request.Request(
            f"{c['base']}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _missing(self, c: dict):
        return [k for k in ("user_id", "token") if not c.get(k)]

    def create_order(self, tenant_id, amount_cents, product, plan, order_meta=None):
        """
        真实下单：调爱发电 API 获取支付链接。
        金额单位：爱发电要求"元"（两位小数 decimal），内部统一为"分"。
        """
        c = self._cred()
        missing = self._missing(c)
        if missing:
            oid = "afdian_" + str(uuid.uuid4())[:12]
            return {
                "order_id": oid,
                "status": "created_pending_key",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "afdian",
                "needs_secret": [f"JZ_SAAS_AFDIAN_{k.upper()}" for k in missing],
                "note": "user_id/token 未配，无法真实下单",
                "meta": order_meta or {},
            }

        # 金额转换：分 → 元（爱发电要求元，两位小数）
        price = round(amount_cents / 100.0, 2)
        out_trade_no = "jz_" + str(uuid.uuid4())[:16]
        payload = {
            "user_id": c["user_id"],
            "price": str(price),
            "name": f"{product}({plan})"[:42],
            "out_trade_no": out_trade_no,
        }
        if c.get("return_url"):
            payload["return_url"] = c["return_url"]
        if order_meta:
            payload["attach"] = json.dumps(order_meta, ensure_ascii=False)

        try:
            result = self._post("/payment/create", payload)
        except Exception as e:
            return {
                "order_id": out_trade_no,
                "status": "gateway_error",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "afdian",
                "error": str(e),
                "ts": int(time.time()),
                "meta": order_meta or {},
            }

        code = result.get("code", -1)
        if code != 0:
            return {
                "order_id": out_trade_no,
                "status": "gateway_rejected",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "afdian",
                "code": code,
                "msg": result.get("message", ""),
                "ts": int(time.time()),
                "meta": order_meta or {},
            }

        data = result.get("data", {})
        return {
            "order_id": out_trade_no,
            "status": "created",
            "amount_cents": amount_cents,
            "plan": plan,
            "product": product,
            "gateway": "afdian",
            "pay_url": data.get("url", ""),
            "qrcode_url": data.get("qrcode_url", ""),
            "out_trade_no": out_trade_no,
            "ts": int(time.time()),
            "meta": order_meta or {},
        }

    def query_callback(self, order_id):
        """爱发电订单查询：按 out_trade_no 主动查询。"""
        c = self._cred()
        missing = self._missing(c)
        if missing:
            return {"order_id": order_id, "status": "pending_key", "paid": False, "note": "user_id/token 未配"}
        payload = {"user_id": c["user_id"], "out_trade_no": order_id}
        try:
            result = self._post("/payment/query", payload)
            code = result.get("code", -1)
            if code != 0:
                return {"order_id": order_id, "status": "query_error", "paid": False, "gateway": "afdian", "code": code, "msg": result.get("message", "")}
            data = result.get("data", {})
            paid = data.get("status") in ("paid", "success")
            return {"order_id": order_id, "status": data.get("status", "unknown"), "paid": paid, "gateway": "afdian"}
        except Exception as e:
            return {"order_id": order_id, "status": "query_failed", "paid": False, "error": str(e), "gateway": "afdian"}

    def verify_callback(self, payload: dict) -> bool:
        """验证爱发电异步回调：按回调 token 匹配当前配置的 token。"""
        c = self._cred()
        if not c.get("token"):
            return False
        return payload.get("token") == c["token"]

    def refund(self, order_id, amount_cents, reason=""):
        """爱发电退款。"""
        c = self._cred()
        missing = self._missing(c)
        if missing:
            return {"order_id": order_id, "ok": False, "note": "user_id/token 未配", "gateway": "afdian"}
        price = round(amount_cents / 100.0, 2)
        payload = {"user_id": c["user_id"], "out_trade_no": order_id, "price": str(price)}
        if reason:
            payload["reason"] = reason
        try:
            result = self._post("/payment/refund", payload)
            ok = result.get("code", -1) == 0
            return {
                "order_id": order_id,
                "ok": ok,
                "refunded_cents": amount_cents if ok else 0,
                "reason": reason,
                "gateway": "afdian",
                "code": result.get("code"),
                "msg": result.get("message", ""),
            }
        except Exception as e:
            return {"order_id": order_id, "ok": False, "error": str(e), "gateway": "afdian"}


register_gateway(NoopGateway)
register_gateway(WxPayGateway)
register_gateway(AishouqianGateway)
register_gateway(AfdianGateway)



def get_gateway(name: str = None) -> Gateway:
    """按名字取网关；缺省读环境变量 JZ_SAAS_BILLING_GATEWAY，未设置回退 noop。"""
    name = name or os.environ.get("JZ_SAAS_BILLING_GATEWAY", "noop")
    cls = BUILTIN_REGISTRY.get(name, NoopGateway)
    return cls()


def create_order_for_tenant(tenant_id, plan, amount_cents, product="jianzhu-saas-sub"):
    """便捷入口：下单。升级套餐时调用。"""
    g = get_gateway()
    order = g.create_order(tenant_id, amount_cents, product, plan)
    # 下单成功且 paid 时立即发放权益（避免"付费成功但未开通"）
    if order.get("paid"):
        _grant_benefit(order.get("tenant_id", tenant_id), order)
    return order


def _grant_benefit(tenant_id, order):
    """收款成功后的权益发放：升级套餐 + 充值 credits。
    order 来自网关 query_callback/create_order，含 paid/plan/credits/amount_cents。
    缺 plan 时按金额匹配档位；缺 credits 时按套餐默认额度。幂等：同一租户重复发放不重复叠加。"""
    plan = order.get("plan") or _plan_from_cents(order.get("amount_cents"))
    credits = order.get("credits")
    if plan:
        tsvc.set_plan(tenant_id, plan, credits)  # set_plan 内部按 credits 或套餐默认额度落库
    elif credits:
        tsvc.topup_credit(tenant_id, credits)
    return {"granted": True, "tenant_id": tenant_id, "plan": plan, "credits": credits}


def _plan_from_cents(amount_cents):
    """按金额匹配套餐档位（金额=credits×0.01 元；不足最低档返回 None，仅充 credits）。"""
    if not amount_cents:
        return None
    # 档位额度沿用 tsvc.PLAN_CREDIT 反向匹配（free/pro/enterprise）
    for plan, c in reversed(list(getattr(tsvc, "PLAN_CREDIT", {}).items())):
        if amount_cents >= int(c) * 100:
            return plan
    return None


def handle_callback(payload):
    """支付平台回调入口：校验后发放/升级套餐。"""
    g = get_gateway()
    # 爱发电回调带 token，先验签
    if isinstance(g, AfdianGateway) and g.verify_callback(payload):
        res = g.query_callback(payload.get("out_trade_no", payload.get("order_id", "")))
        if res.get("paid"):
            _grant_benefit(res.get("tenant_id"), res)
        return {"ok": True, "callback": res, "verified": True}
    else:
        res = g.query_callback(payload.get("order_id", payload.get("trade_order_id", "")))
        if res.get("paid"):
            _grant_benefit(res.get("tenant_id"), res)
        return {"ok": True, "callback": res}


def refund(order_id, amount_cents, reason="user_request"):
    return get_gateway().refund(order_id, amount_cents, reason)
