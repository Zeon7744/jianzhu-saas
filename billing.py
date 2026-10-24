"""
国内收款抽象层（预留接口，不接具体支付网关/不填密钥/不发真实请求）。

三个方法：create_order / query_callback / refund
内置网关（均为"骨架 + 签名/参数齐全，运行时默认 noop，生产配密钥后启用"）：

  - WxPayGateway      : 微信商户（企业主体，JSAPI/H5 下单 + 回调验签 + 退款）
  - AishouqianGateway : 爱收钱聚合（MVP 门槛最低，二维码收银台）

  - MbdGateway        : 面包多 Pay（个人可实名收款，支付宝即时/微信次日到卡；费率 2%+0.1 元/笔，以开通页为准）
环境变量 MBD_APP_ID / MBD_API_KEY / MBD_GATEWAY_URL / MBD_WEBHOOK_URL / MBD_PAY_CHANNEL
选择：环境变量 JZ_SAAS_BILLING_GATEWAY=noop|wepay|aishouqian|mbd（缺省 mbd）
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



class MbdGateway(Gateway):
    """
    面包多 Pay 真实网关（个人可实名收款：支付宝即时 5 分钟内到账，微信次日到卡）。
    官方文档 https://doc.mbd.pub/ ；费率 2% + 0.1 元/笔（<0.5 元免收），以开通页为准。

    环境变量（敏感，env 注入不入库）：
      MBD_APP_ID      面包多控制台 app_id
      MBD_API_KEY     面包多 app_key（签名用，= 面包多"开发者 key"）
      MBD_GATEWAY_URL API 基址（默认 https://newapi.mbd.pub/release）
      MBD_WEBHOOK_URL 控制台 Webhook 异步通知 URL（charge_succeeded / complaint）
      MBD_PAY_CHANNEL alipay（默认）| wx_h5（需控制台先过 H5 域名审核）

    签名：MD5(ASCII 字典序 k=v&... + &key=app_key)（doc.mbd.pub/api/qian-ming-suan-fa）
    未配凭据时降级：created_pending_key + needs_secret（不发真实请求）。
    """

    name = "mbd"
    DEFAULT_BASE = "https://newapi.mbd.pub/release"

    def _cred(self):
        return {
            "app_id": os.environ.get("MBD_APP_ID", ""),
            "api_key": _secret("MBD_API_KEY"),
            "base": os.environ.get("MBD_GATEWAY_URL", self.DEFAULT_BASE),
            "webhook": os.environ.get("MBD_WEBHOOK_URL", ""),
            "channel": os.environ.get("MBD_PAY_CHANNEL", "alipay"),
        }

    @staticmethod
    def _mbd_sign(data: dict, api_key: str) -> str:
        ordered = {k: v for k, v in sorted(data.items()) if v not in ("", None)}
        s = "&".join(f"{k}={v}" for k, v in ordered.items())
        return hashlib.md5((s + "&key=" + api_key).encode("utf-8")).hexdigest()

    def _post(self, path: str, payload: dict):
        c = self._cred()
        body = dict(payload)
        body["app_id"] = c["app_id"]
        body["sign"] = self._mbd_sign(body, c["api_key"])
        req = urllib.request.Request(
            f"{c['base']}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _missing(self, c: dict):
        return [k for k in ("MBD_APP_ID", "MBD_API_KEY") if not c.get({"MBD_APP_ID": "app_id", "MBD_API_KEY": "api_key"}[k])]

    def create_order(self, tenant_id, amount_cents, product, plan, order_meta=None):
        """面包多 Pay 下单：amount_total 单位=分；支付宝→pay_body（前端唤起），微信 H5→h5_url。"""
        c = self._cred()
        missing = self._missing(c)
        if missing:
            oid = "mbd_" + str(uuid.uuid4())[:12]
            return {
                "order_id": oid,
                "status": "created_pending_key",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "mbd",
                "needs_secret": missing,
                "note": "面包多 Pay 未开通：注册 mbd.pub → 闪电结算 → 控制台取 app_id/app_key → 填 MBD_APP_ID + MBD_API_KEY 即可真下单",
                "ts": int(time.time()),
                "meta": order_meta or {},
            }
        out_trade_no = "mbd_" + str(uuid.uuid4())[:16]
        payload = {
            "description": f"{product}({plan})"[:42],
            "amount_total": int(amount_cents),
            "out_trade_no": out_trade_no,
        }
        path = "/wx/prepay" if c["channel"] == "wx_h5" else "/alipay/pay"
        if c["channel"] == "wx_h5":
            payload["channel"] = "h5"
        try:
            result = self._post(path, payload)
        except Exception as e:
            return {"order_id": out_trade_no, "status": "gateway_error", "amount_cents": amount_cents,
                    "plan": plan, "product": product, "gateway": "mbd", "error": str(e),
                    "ts": int(time.time()), "meta": order_meta or {}}
        if "error" in result:
            return {"order_id": out_trade_no, "status": "gateway_rejected", "amount_cents": amount_cents,
                    "plan": plan, "product": product, "gateway": "mbd", "error": result["error"],
                    "ts": int(time.time()), "meta": order_meta or {}}
        out = {"order_id": out_trade_no, "status": "created", "amount_cents": amount_cents,
               "plan": plan, "product": product, "gateway": "mbd", "ts": int(time.time()),
               "meta": order_meta or {}}
        out["h5_url" if c["channel"] == "wx_h5" else "pay_body"] = result.get("h5_url" if c["channel"] == "wx_h5" else "body", "")
        return out

    def query_callback(self, order_id):
        """面包多订单查询：POST /search_order（辅助查询；高频状态走 Webhook 异步通知）。"""
        c = self._cred()
        if self._missing(c):
            return {"order_id": order_id, "status": "pending_key", "paid": False,
                    "needs_secret": self._missing(c), "gateway": "mbd"}
        payload = {"out_trade_no": order_id}
        payload["app_id"] = c["app_id"]
        payload["sign"] = self._mbd_sign(payload, c["api_key"])
        try:
            result = self._post("/search_order", payload)
            if "error" in result:
                return {"order_id": order_id, "status": "query_error", "paid": False,
                        "error": result["error"], "gateway": "mbd"}
            state = str(result.get("state", ""))
            return {"order_id": order_id, "status": state, "paid": state in ("1", "2"),
                    "amount_cents": int(result.get("amount", 0)), "gateway": "mbd"}
        except Exception as e:
            return {"order_id": order_id, "status": "query_failed", "paid": False,
                    "error": str(e), "gateway": "mbd"}

    def verify_callback(self, payload: dict) -> bool:
        """Webhook 异步通知验证：charge_succeeded / complaint，控制台直连 URL + out_trade_no 去重。"""
        if not isinstance(payload, dict):
            return False
        data = payload.get("data") or {}
        return payload.get("type") in ("charge_succeeded", "complaint") and bool(data.get("out_trade_no"))

    def refund(self, order_id, amount_cents, reason=""):
        """面包多 Pay 退款：POST /refund（除 API 外，控制台也可直接退款）。"""
        c = self._cred()
        if self._missing(c):
            return {"order_id": order_id, "ok": False, "note": "面包多 Pay 凭据未配",
                    "needs_secret": self._missing(c), "gateway": "mbd"}
        payload = {"out_trade_no": order_id, "refund_amount": int(amount_cents or 0)}
        payload["app_id"] = c["app_id"]
        payload["sign"] = self._mbd_sign(payload, c["api_key"])
        try:
            result = self._post("/refund", payload)
            ok = "error" not in result
            return {"order_id": order_id, "ok": ok,
                    "refunded_cents": amount_cents if ok else 0, "reason": reason, "gateway": "mbd"}
        except Exception as e:
            return {"order_id": order_id, "ok": False, "error": str(e), "gateway": "mbd"}


register_gateway(NoopGateway)
register_gateway(WxPayGateway)
register_gateway(AishouqianGateway)
register_gateway(MbdGateway)



def get_gateway(name: str = None) -> Gateway:
    """按名字取网关；缺省读环境变量 JZ_SAAS_BILLING_GATEWAY，未设置回退 noop。"""
    name = name or os.environ.get("JZ_SAAS_BILLING_GATEWAY", "mbd")
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
    # 面包多 Webhook（charge_succeeded）：控制台直连 + out_trade_no 去重
    if isinstance(g, MbdGateway) and g.verify_callback(payload):
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
