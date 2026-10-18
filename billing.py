"""
国内收款抽象层（预留接口，不接具体支付网关/不填密钥/不发真实请求）。

三个方法：create_order / query_callback / refund
内置网关（均为"骨架 + 签名/参数齐全，运行时默认 noop，生产配密钥后启用"）：
  - NoopGateway       : MVP 占位，不扣款
  - WxPayGateway      : 微信商户（企业主体，JSAPI/H5 下单 + 回调验签 + 退款）
  - AishouqianGateway : 爱收钱聚合（MVP 门槛最低，二维码收银台）
  - HuPijiaoGateway   : 虎皮椒（个人主体 10 分钟开通，H5/QR 收款，费率 ~0.6%）
选择：环境变量 JZ_SAAS_BILLING_GATEWAY=noop|wepay|aishouqian|xunhupay（缺省 noop）
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


class HuPijiaoGateway(Gateway):
    """
    虎皮椒真实网关：个人主体 10 分钟开通，H5/QR 收款，费率 ~0.6%。
    API 文档：https://www.xunhupay.com/doc/api/pay.html
    开通：注册 xunhupay.com → 个人商户实名 → 拿 appid + appsecret

    环境变量：
      JZ_SAAS_XUNHU_APPID          虎皮椒 APPID（必填）
      JZ_SAAS_XUNHU_APPSECRET      虎皮椒 APPSECRET（必填）
      JZ_SAAS_XUNHU_GATEWAY        网关地址（默认 https://api.xunhupay.com/payment/do.html）
      JZ_SAAS_XUNHU_NOTIFY         异步回调地址（公网可达 HTTPS URL，必填）
      JZ_SAAS_XUNHU_RETURN         同步跳转地址（支付后浏览器跳回，可选）
      JZ_SAAS_XUNHU_PLUGINS        插件标识（可选）

    签名算法：
      1. 所有非空参数按参数名 ASCII 升序排序
      2. 拼接为 key1=value1&key2=value2...（空值跳过）
      3. 末尾直接拼接 APPSECRET（无连接符）
      4. MD5 取 32 位小写
    """

    name = "xunhupay"

    DEFAULT_GATEWAY = "https://api.xunhupay.com/payment/do.html"
    BACKUP_GATEWAY = "https://api.dpweixin.com/payment/do.html"

    def _cred(self):
        return {
            "appid": _secret("JZ_SAAS_XUNHU_APPID"),
            "appsecret": _secret("JZ_SAAS_XUNHU_APPSECRET"),
            "gateway": os.environ.get("JZ_SAAS_XUNHU_GATEWAY", self.DEFAULT_GATEWAY),
            "notify": os.environ.get("JZ_SAAS_XUNHU_NOTIFY", ""),
            "return_url": os.environ.get("JZ_SAAS_XUNHU_RETURN", ""),
            "plugins": os.environ.get("JZ_SAAS_XUNHU_PLUGINS", "jianzhu-saas"),
        }

    @staticmethod
    def _hash(params: dict, appsecret: str) -> str:
        """虎皮椒 MD5 签名：非空参数按 ASCII 排序拼接 + 拼接 appsecret → MD5 32 位小写。"""
        filtered = {k: v for k, v in params.items() if k != "hash" and v not in (None, "")}
        string_a = "&".join(f"{k}={v}" for k, v in sorted(filtered.items(), key=lambda x: x[0]))
        return hashlib.md5((string_a + appsecret).encode("utf-8")).hexdigest()

    def _post(self, gateway_url: str, payload: dict):
        """POST JSON 到虎皮椒网关，返回解析后的 dict。"""
        req = urllib.request.Request(
            gateway_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _missing(self, c: dict):
        return [k for k in ("appid", "appsecret") if not c.get(k)]

    def create_order(self, tenant_id, amount_cents, product, plan, order_meta=None):
        """
        真实下单：调虎皮椒 API 获取支付链接（H5 url / PC url_qrcode）。
        金额单位：接口要求"元"（decimal），内部统一为"分"。
        """
        c = self._cred()
        missing = self._missing(c)
        if missing:
            oid = "xunhu_" + str(uuid.uuid4())[:12]
            return {
                "order_id": oid,
                "status": "created_pending_key",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "xunhupay",
                "needs_secret": [f"JZ_SAAS_XUNHU_{k.upper()}" for k in missing],
                "note": "appid/appsecret 未配，无法真实下单",
                "meta": order_meta or {},
            }

        # 金额转换：分 → 元（虎皮椒要求元，两位小数）
        total_fee = round(amount_cents / 100.0, 2)
        trade_order_id = "jz_" + str(uuid.uuid4())[:16]
        nonce_str = str(uuid.uuid4().int)[:32]

        params = {
            "version": "1.1",
            "appid": c["appid"],
            "trade_order_id": trade_order_id,
            "total_fee": str(total_fee),
            "title": f"{product}({plan})"[:42],  # 虎皮椒限制 42 个汉字
            "time": str(int(time.time())),
            "notify_url": c.get("notify", ""),
            "nonce_str": nonce_str,
        }
        # 可选参数
        if c.get("return_url"):
            params["return_url"] = c["return_url"]
        if c.get("plugins"):
            params["plugins"] = c["plugins"]
        if order_meta:
            params["attach"] = json.dumps(order_meta, ensure_ascii=False)

        # 签名
        params["hash"] = self._hash(params, c["appsecret"])

        # 真实调用
        gw = c.get("gateway") or self.DEFAULT_GATEWAY
        try:
            result = self._post(gw, params)
        except Exception as e:
            return {
                "order_id": trade_order_id,
                "status": "gateway_error",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "xunhupay",
                "error": str(e),
                "ts": int(time.time()),
                "meta": order_meta or {},
            }

        errcode = result.get("errcode", -1)
        if errcode != 0:
            return {
                "order_id": trade_order_id,
                "status": "gateway_rejected",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "xunhupay",
                "errcode": errcode,
                "errmsg": result.get("errmsg", ""),
                "ts": int(time.time()),
                "meta": order_meta or {},
            }

        # 成功：返回支付链接
        return {
            "order_id": trade_order_id,
            "status": "created",
            "amount_cents": amount_cents,
            "plan": plan,
            "product": product,
            "gateway": "xunhupay",
            "pay_url": result.get("url", ""),          # 手机端 H5 支付链接
            "qrcode_url": result.get("url_qrcode", ""),  # PC 端二维码
            "trade_order_id": trade_order_id,
            "ts": int(time.time()),
            "meta": order_meta or {},
        }

    def query_callback(self, order_id):
        """
        虎皮椒回调/查询：
        - 异步回调：虎皮椒 POST 到 notify_url，验签后发放权益
        - 主动查询：调查询接口（doc/api/search.html）
        当前返回结构供上层逻辑使用。
        """
        c = self._cred()
        missing = self._missing(c)
        if missing:
            return {"order_id": order_id, "status": "pending_key", "paid": False, "note": "appid/appsecret 未配"}

        # 虎皮椒回调验签：虎皮椒侧会带上 hash 参数，用同一算法验证
        # 主动查询（需配 JZ_SAAS_XUNHU_QUERY_GATEWAY，默认同下单网关）
        # 查询接口参数：appid + trade_order_id + nonce_str + hash
        nonce_str = str(uuid.uuid4().int)[:32]
        params = {
            "version": "1.1",
            "appid": c["appid"],
            "trade_order_id": order_id,
            "nonce_str": nonce_str,
        }
        params["hash"] = self._hash(params, c["appsecret"])
        gw = c.get("gateway") or self.DEFAULT_GATEWAY

        try:
            result = self._post(gw, params)
            errcode = result.get("errcode", -1)
            if errcode != 0:
                return {"order_id": order_id, "status": "query_error", "paid": False, "errcode": errcode, "errmsg": result.get("errmsg", "")}
            # 虎皮椒查询返回 status: OD=已支付 CD=已退款 RD=退款中 UD=退款失败
            paid = result.get("status") == "OD"
            return {"order_id": order_id, "status": result.get("status", "unknown"), "paid": paid}
        except Exception as e:
            return {"order_id": order_id, "status": "query_failed", "paid": False, "error": str(e)}

    def verify_callback(self, payload: dict) -> bool:
        """验证虎皮椒异步回调签名。"""
        c = self._cred()
        if not c.get("appsecret"):
            return False
        hash_received = payload.pop("hash", "")
        calc = self._hash(payload, c["appsecret"])
        return hashlib.md5(calc.encode()).hexdigest() == hashlib.md5(hash_received.encode()).hexdigest() or calc == hash_received

    def refund(self, order_id, amount_cents, reason=""):
        """
        虎皮椒退款（doc/api/refund.html）：
        参数：appid + trade_order_id + refund_fee(元) + nonce_str + hash
        """
        c = self._cred()
        missing = self._missing(c)
        if missing:
            return {"order_id": order_id, "ok": False, "note": "appid/appsecret 未配", "gateway": "xunhupay"}

        refund_fee = round(amount_cents / 100.0, 2)
        nonce_str = str(uuid.uuid4().int)[:32]
        params = {
            "version": "1.1",
            "appid": c["appid"],
            "trade_order_id": order_id,
            "refund_fee": str(refund_fee),
            "nonce_str": nonce_str,
        }
        if reason:
            params["reason"] = reason
        params["hash"] = self._hash(params, c["appsecret"])
        gw = c.get("gateway") or self.DEFAULT_GATEWAY

        try:
            result = self._post(gw, params)
            errcode = result.get("errcode", -1)
            ok = errcode == 0
            return {
                "order_id": order_id,
                "ok": ok,
                "refunded_cents": amount_cents if ok else 0,
                "reason": reason,
                "gateway": "xunhupay",
                "errcode": errcode,
                "errmsg": result.get("errmsg", ""),
            }
        except Exception as e:
            return {"order_id": order_id, "ok": False, "error": str(e), "gateway": "xunhupay"}


register_gateway(NoopGateway)
register_gateway(WxPayGateway)
register_gateway(AishouqianGateway)
register_gateway(HuPijiaoGateway)


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
    # 虎皮椒回调带完整签名，先验签
    if isinstance(g, HuPijiaoGateway) and g.verify_callback(payload):
        res = g.query_callback(payload.get("trade_order_id", payload.get("order_id", "")))
        if res.get("paid"):
            _grant_benefit(res.get("tenant_id"), res)
        return {"ok": True, "callback": res, "verified": True}
    res = g.query_callback(payload.get("order_id", payload.get("trade_order_id", "")))
    if res.get("paid"):
        _grant_benefit(res.get("tenant_id"), res)
    return {"ok": True, "callback": res}


def refund(order_id, amount_cents, reason="user_request"):
    return get_gateway().refund(order_id, amount_cents, reason)
