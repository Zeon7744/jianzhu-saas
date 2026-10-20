"""
BufPay 支付网关（个人收款聚合码）
文档：https://bufpay.com
"""
import os
import re
import time
import uuid
import json
import hashlib
import urllib.request
import urllib.parse

from billing import Gateway, register_gateway


class BufPayGateway(Gateway):
    """
    BufPay 个人收款网关
    环境变量:
      JZ_SAAS_BUFPAY_AID        BufPay 应用 ID
      JZ_SAAS_BUFPAY_APP_SECRET BufPay App Secret
      JZ_SAAS_BUFPAY_NOTIFY_URL 支付回调地址
      JZ_SAAS_BUFPAY_RETURN_URL 支付成功跳转地址
    """
    
    name = "bufpay"
    BASE_URL = "https://bufpay.com"
    
    def _keys(self):
        return {
            "aid": os.environ.get("JZ_SAAS_BUFPAY_AID", ""),
            "app_secret": os.environ.get("JZ_SAAS_BUFPAY_APP_SECRET", ""),
            "notify_url": os.environ.get("JZ_SAAS_BUFPAY_NOTIFY_URL", ""),
            "return_url": os.environ.get("JZ_SAAS_BUFPAY_RETURN_URL", ""),
        }
    
    def _sign(self, *args):
        """MD5 签名，纯值拼接（不含 + 号）"""
        return hashlib.md5(''.join(args).encode('utf-8')).hexdigest().lower()
    
    def _post(self, path, payload):
        """POST 请求，返回响应内容"""
        try:
            data = urllib.parse.urlencode(payload).encode('utf-8')
            req = urllib.request.Request(
                f"{self.BASE_URL}{path}",
                data=data,
                method='POST'
            )
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode('utf-8')
                # 检测是否是错误页面
                if "签名错误" in content or "缺少参数" in content:
                    return {"status": "error", "message": content}
                return content
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _get(self, path):
        """GET 请求，返回 JSON"""
        try:
            req = urllib.request.Request(f"{self.BASE_URL}{path}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def create_order(self, tenant_id, amount_cents, product, plan, order_meta=None):
        c = self._keys()
        if not c.get("aid") or not c.get("app_secret"):
            oid = "bufpay_" + str(uuid.uuid4())[:12]
            return {
                "order_id": oid,
                "status": "created_pending_key",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "bufpay",
                "needs_secret": ["JZ_SAAS_BUFPAY_AID", "JZ_SAAS_BUFPAY_APP_SECRET"],
                "meta": order_meta or {},
            }
        
        price = round(amount_cents / 100.0, 2)
        order_id = "jz_" + str(uuid.uuid4())[:16]
        
        # 签名参数（aid 不在签名中，只在 URL 路径）
        sign_str = (
            product + 
            "wechat" + 
            f"{price:.2f}" + 
            order_id + 
            str(tenant_id) + 
            c.get("notify_url", "") + 
            c.get("return_url", "") + 
            "" + 
            c.get("app_secret", "")
        )
        sign = self._sign(sign_str)
        
        # 构建请求
        payload = {
            "name": product,
            "pay_type": "wechat",
            "price": f"{price:.2f}",
            "order_id": order_id,
            "order_uid": str(tenant_id),
            "notify_url": c.get("notify_url", ""),
            "return_url": c.get("return_url", ""),
            "feedback_url": "",
            "sign": sign,
        }
        
        result = self._post(f"/api/pay/{c.get('aid')}", payload)
        
        # 检查是否是错误
        if isinstance(result, dict) and result.get("status") == "error":
            return {
                "order_id": order_id,
                "status": "gateway_error",
                "amount_cents": amount_cents,
                "plan": plan,
                "product": product,
                "gateway": "bufpay",
                "error": result.get("message", "签名验证失败"),
                "meta": order_meta or {},
            }
        
        # 从 HTML 中提取 aoid（订单号）
        aoid = None
        if isinstance(result, str):
            # 尝试从 HTML 中提取 aoid
            match = re.search(r'aoid["\s:]+(\d+)', result)
            if match:
                aoid = match.group(1)
            else:
                # 使用 order_id 作为标识
                aoid = order_id.replace("jz_", "", 1)
        
        return {
            "order_id": order_id,
            "aoid": aoid,
            "status": "created",
            "amount_cents": amount_cents,
            "plan": plan,
            "product": product,
            "gateway": "bufpay",
            "pay_url": f"{self.BASE_URL}/api/pay/{c.get('aid')}?order_id={order_id}",
            "html": result if isinstance(result, str) else None,
            "meta": order_meta or {},
        }
    
    def query_callback(self, order_id):
        c = self._keys()
        if not c.get("aid") or not c.get("app_secret"):
            return {"order_id": order_id, "status": "pending_key", "paid": False}
        
        # 使用 aoid 查询
        aoid = order_id.replace("jz_", "", 1) if order_id.startswith("jz_") else order_id
        result = self._get(f"/api/query/{aoid}")
        
        paid = result.get("status") in ("paid", "success", "payed")
        return {
            "order_id": order_id,
            "aoid": aoid,
            "status": result.get("status", "unknown"),
            "paid": paid,
            "gateway": "bufpay",
        }
    
    def refund(self, order_id, amount_cents, reason=""):
        # BufPay 不支持退款 API，返回占位
        return {
            "order_id": order_id,
            "ok": False,
            "note": "BufPay 暂不支持自动退款",
            "gateway": "bufpay",
        }


register_gateway(BufPayGateway)
