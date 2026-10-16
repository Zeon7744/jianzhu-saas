"""
国内收款抽象层（预留接口，已接爱收钱聚合网关占位）。

三个方法：create_order / query_callback / refund
国内候选接入：微信商户（企业主体）/ 支付宝当面付 / 爱收钱聚合 / 云市场订阅
实现类通过 BUILTIN_REGISTRY 注册，运行时按环境选择，缺省为 NoopGateway。

【MVP 阶段】默认 NoopGateway；爱收钱网关已写骨架，API key 填入后切换。
"""
import os
import time
import uuid
from typing import Optional

BUILTIN_REGISTRY = {}


class NoopGateway:
    """占位网关：不真正扣款，用于 MVP 演示。生产替换为真实网关。"""
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
            "pay_url": f"https://example.local/pay/{oid}",
            "meta": order_meta or {},
        }

    def query_callback(self, order_id):
        return {"order_id": order_id, "status": "unpaid", "paid": False}

    def refund(self, order_id, amount_cents, reason=""):
        return {"order_id": order_id, "refunded_cents": amount_cents, "ok": True, "reason": reason}


class AiShouQianGateway:
    """爱收钱聚合网关（个人/小微可接，支持微信+支付宝）。

    环境变量：
      JZ_SAAS_AISQ_MERCHANT_NO  商户号（必填）
      JZ_SAAS_AISQ_APP_KEY      App Key（必填）
      JZ_SAAS_AISQ_APP_SECRET   App Secret（必填）
      JZ_SAAS_AISQ_NOTIFY_URL   支付回调 URL（可选，默认 /billing/callback）

    爱收钱 API 文档：https://www.aishouqian.com/doc
    费率：微信/支付宝 0.55%–0.6%，无月费，适合个人/小微主体
    """
    name = "aishouqian"

    def __init__(self):
        self.merchant = os.environ.get("JZ_SAAS_AISQ_MERCHANT_NO", "")
        self.app_key = os.environ.get("JZ_SAAS_AISQ_APP_KEY", "")
        self.app_secret = os.environ.get("JZ_SAAS_AISQ_APP_SECRET", "")
        self.notify_url = os.environ.get("JZ_SAAS_AISQ_NOTIFY_URL", "/billing/callback")

    def _sign(self, payload):
        """爱收钱签名：HMAC-SHA256(app_key, app_secret)"""
        import hmac, hashlib, json as _json
        raw = _json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hmac.new(self.app_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

    def create_order(self, tenant_id, amount_cents, product, plan, order_meta=None):
        if not self.merchant:
            raise RuntimeError("JZ_SAAS_AISQ_MERCHANT_NO 未配置，无法真实下单")
        oid = "aisq_" + str(uuid.uuid4())[:12]
        payload = {
            "merchant_no": self.merchant,
            "out_order_id": oid,
            "total_fee": amount_cents,  # 单位：分
            "product_name": product,
            "plan": plan,
            "notify_url": self.notify_url,
            "meta": order_meta or {},
        }
        payload["sign"] = self._sign(payload)
        # TODO: 真实 POST 到爱收钱 API（生产环境启用）
        print(f"[aisq] 下单 {oid} amount={amount_cents} plan={plan}（MVP 占位，未真实调 API）")
        return {
            "order_id": oid,
            "status": "created",
            "amount_cents": amount_cents,
            "plan": plan,
            "product": product,
            "ts": int(time.time()),
            "pay_url": f"https://pay.aishouqian.com/{oid}",
            "meta": order_meta or {},
        }

    def query_callback(self, order_id):
        # TODO: 真实 GET 爱收钱 API 查订单状态
        return {"order_id": order_id, "status": "unpaid", "paid": False}

    def refund(self, order_id, amount_cents, reason="user_request"):
        # TODO: 真实 POST 爱收钱退款 API
        return {"order_id": order_id, "refunded_cents": amount_cents, "ok": True, "reason": reason}


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


register_gateway(NoopGateway)
register_gateway(AiShouQianGateway)


def get_gateway(name: str = None) -> Gateway:
    """按名字取网关；缺省读环境变量 JZ_SAAS_BILLING_GATEWAY，未设置回退 noop。"""
    name = name or os.environ.get("JZ_SAAS_BILLING_GATEWAY", "noop")
    cls = BUILTIN_REGISTRY.get(name)
    if cls is None:
        cls = NoopGateway
    return cls()


def create_order_for_tenant(tenant_id, plan, amount_cents, product="jianzhu-saas-sub"):
    """便捷入口：下单。升级套餐时调用。"""
    g = get_gateway()
    order = g.create_order(tenant_id, amount_cents, product, plan)
    # 预留：下单成功后升级 tenant plan + 加 credits
    # tsvc.upgrade_plan(tenant_id, plan)
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
