"""
BufPay 支付网关（个人收款聚合码）
文档：https://bufpay.com
"""
import os
import time
import uuid
import json
import urllib.request

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from billing import Gateway, register_gateway


class BufPayGateway(Gateway):
    """
    BufPay 个人收款网关
    环境变量:
      JZ_SAAS_BUFPAY_API_KEY    BufPay API Key
      JZ_SAAS_BUFPAY_NOTIFY_URL 支付回调地址
    """
    
    name = "bufpay"
    BASE_URL = "https://api.bufpay.com/v1"
    
    def _keys(self):
        return {
            "api_key": os.environ.get("JZ_SAAS_BUFPAY_API_KEY", ""),
            "notify_url": os.environ.get("JZ_SAAS_BUFPAY_NOTIFY_URL", ""),
        }
    
    def _post(self, path, payload):
        c = self._keys()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {c['api_key']}",
        }
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"error": str(e)}
    
    def create_order(self, tenant_id, amount_cents, product, plan, order_meta=None):
        c = self._keys()
        if not c.get("api_key"):
            oid = "bufpay_" + str(uuid.uuid4())[:12]
            return {
                "order_id": oid,
                "status": "created_pending_key",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "bufpay",
                "needs_secret": ["JZ_SAAS_BUFPAY_API_KEY"],
                "meta": order_meta or {},
            }
        
        price = round(amount_cents / 100.0, 2)
        out_trade_no = "jz_" + str(uuid.uuid4())[:16]
        
        payload = {
            "out_trade_no": out_trade_no,
            "amount": price,
            "subject": f"{product}({plan})",
            "notify_url": c.get("notify_url") or "https://your-domain.com/hpj/callback",
            "attach": tenant_id,
        }
        
        result = self._post("/orders/create", payload)
        
        if "error" in result:
            return {
                "order_id": out_trade_no,
                "status": "gateway_error",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "bufpay",
                "error": result["error"],
                "meta": order_meta or {},
            }
        
        return {
            "order_id": out_trade_no,
            "status": "created",
            "amount_cents": amount_cents,
            "plan": plan,
            "product": product,
            "gateway": "bufpay",
            "pay_url": result.get("pay_url", ""),
            "qrcode": result.get("qrcode", ""),
            "meta": order_meta or {},
        }
    
    def query_callback(self, order_id):
        c = self._keys()
        if not c.get("api_key"):
            return {"order_id": order_id, "status": "pending_key", "paid": False}
        
        payload = {"out_trade_no": order_id}
        result = self._post("/orders/query", payload)
        
        if "error" in result:
            return {"order_id": order_id, "status": "query_failed", "paid": False, "error": result["error"]}
        
        paid = result.get("status") in ("paid", "success")
        return {"order_id": order_id, "status": result.get("status", "unknown"), "paid": paid, "gateway": "bufpay"}
    
    def refund(self, order_id, amount_cents, reason=""):
        c = self._keys()
        if not c.get("api_key"):
            return {"order_id": order_id, "ok": False, "note": "需配置 API Key"}
        
        price = round(amount_cents / 100.0, 2)
        payload = {
            "out_trade_no": order_id,
            "amount": price,
            "reason": reason,
        }
        
        result = self._post("/orders/refund", payload)
        ok = result.get("code") == 0
        return {
            "order_id": order_id,
            "ok": ok,
            "refunded_cents": amount_cents if ok else 0,
            "reason": reason,
            "gateway": "bufpay",
        }


register_gateway(BufPayGateway)
