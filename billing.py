"""
国内收款抽象层（预留接口，不接具体支付网关）。

三个方法：create_order / query_callback / refund
国内候选接入：微信商户（企业主体）/ 支付宝当面付 / 爱收钱聚合 / 云市场订阅
实现类通过 BUILTIN_REGISTRY 注册，运行时按环境选择，缺省为 NoopGateway。
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
