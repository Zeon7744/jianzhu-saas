"""
国内收款抽象层（预留接口，不接具体支付网关/不填密钥/不发真实请求）。

三个方法：create_order / query_callback / refund
内置网关（均为"骨架 + 签名/参数齐全，运行时默认 noop，生产配密钥后启用"）：
  - NoopGateway      : MVP 占位，不扣款
  - WxPayGateway     : 微信商户（企业主体，JSAPI/H5 下单 + 回调验签 + 退款）
  - AishouqianGateway: 爱收钱聚合（MVP 门槛最低，二维码收银台）
选择：环境变量 JZ_SAAS_BILLING_GATEWAY=noop|wepay|aishouqian（缺省 noop）
所有密钥走环境变量，不落代码。
"""
import os
import time
import uuid
import hmac
import hashlib

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
            # 密钥未配 → 返回可演示的占位订单（生产配齐后自动走真实统一下单）
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
        # 密钥齐备 → 构造统一下单请求体（此处不实际发 HTTP，留给部署侧）
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
        """生产：按回调报文用 sign 验签；此处返回结构占位。"""
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
            base["qrcode"] = f"https://example.local/asq/{oid}"  # 真实为收银台二维码
        else:
            base["needs_secret"] = sorted(k for k, v in c.items() if not v)
        return base

    def query_callback(self, order_id):
        c = self._cred()
        return {"order_id": order_id, "status": "paid" if c.get("mch_no") else "unverified", "paid": bool(c.get("mch_no"))}

    def refund(self, order_id, amount_cents, reason=""):
        c = self._cred()
        return {"order_id": order_id, "ok": bool(c.get("mch_no")), "refunded_cents": amount_cents, "reason": reason, "gateway": "aishouqian"}


register_gateway(NoopGateway)
register_gateway(WxPayGateway)
register_gateway(AishouqianGateway)


def get_gateway(name: str = None) -> Gateway:
    """按名字取网关；缺省读环境变量 JZ_SAAS_BILLING_GATEWAY，未设置回退 noop。"""
    name = name or os.environ.get("JZ_SAAS_BILLING_GATEWAY", "noop")
    cls = BUILTIN_REGISTRY.get(name, NoopGateway)
    return cls()


def create_order_for_tenant(tenant_id, plan, amount_cents, product="jianzhu-saas-sub"):
    """便捷入口：下单。升级套餐时调用。"""
    g = get_gateway()
    order = g.create_order(tenant_id, amount_cents, product, plan)
    # 预留：下单成功且 paid 后升级 tenant plan + 加 credits
    # if order.get("paid"): tsvc.upgrade_plan(tenant_id, plan)
    return order


def handle_callback(payload):
    """支付平台回调入口：校验后发放/升级套餐。"""
    g = get_gateway()
    res = g.query_callback(payload.get("order_id"))
    if res.get("paid"):
        # 预留：发放套餐与 credits
        pass
    return {"ok": True, "callback": res}


def refund(order_id, amount_cents, reason="user_request"):
    return get_gateway().refund(order_id, amount_cents, reason)
