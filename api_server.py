"""
jianzhu-saas: 建筑结构风险评估 SaaS API（最小付费功能）

改造点（对照方案第 4 节）：
1. tenant_id 多租户隔离（store.py SQLite）
2. JWT 鉴权 + 角色 free/pro/enterprise（auth.py）
3. 计量事件 + 套餐 Credit 配额（store.UsageMeter）
4. order_service 三方法预留国内收款（billing.py）
5. 最小前端演示页（GET /）
6. 免责声明叠加在 API / 报告 / 产品三处
"""
import os
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import store
import auth
import billing

store_conn = store.store
meter = store.usage
tsvc = store.tsvc

DEMO_TENANT = os.environ.get("JZ_SAAS_DEMO_TENANT", "demo")


def _json_body(code, body, extra_headers=None):
    def handler(self, code=code, body=body, extra_headers=extra_headers):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode())
    return handler


def require_tenant(self):
    """从 Authorization: Bearer <jwt> 解析 tenant + 角色。返回 (claims, error_body_or_None)"""
    authz = self.headers.get("Authorization", "")
    if not authz.startswith("Bearer "):
        return None, ("missing_token", 401)
    token = authz.split(" ", 1)[1].strip()
    claims, err = auth.verify_token(token)
    if err:
        return None, (err, 401)
    return claims, None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {fmt % args}")

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(data)

    # ---------- 路由：演示页（免鉴权） ----------
    def do_GET(self):
        if self.path in ("/", "/index.html", "/demo"):
            return self._send(200, INDEX_HTML, "text/html; charset=utf-8")
        if self.path == "/health":
            return self._send(200, {"status": "ok", "time": time.time()})

        claims, err = require_tenant(self)
        if err:
            return self._send(err[1], {"error": err[0]})
        tid = claims.get("tenant_id")
        t = tsvc.get(tid) or tsvc.ensure_tenant(tid, plan=claims.get("plan", "free"))

        if self.path == "/auth/whoami":
            return self._send(200, {"tenant": t, "role": claims.get("role")})
        if self.path == "/billing/credit":
            return self._send(200, {"tenant_id": tid, "credits": t["credits"], "plan": t["plan"]})
        # 管理后台：列出所有租户（仅 admin）
        if self.path == "/admin/tenants":
            role = claims.get("role", "operator")
            if role != "admin":
                return self._send(403, {"error": "admin_only"})
            tenants = tsvc.list_tenants()
            return self._send(200, {"count": len(tenants), "tenants": tenants})

        if self.path.startswith("/api/inspections/"):
            iid = self.path.split("/")[-1]
            rec = store_conn.get_inspection(tid, iid)
            return self._send(200, rec) if rec else self._send(404, {"error": "Not found"})
        if self.path == "/api/assessments":
            items = store_conn.list_assessments(tid)
            return self._send(200, {"count": len(items), "items": items, "disclaimer": store.RiskEngine.DISCLAIMER})
        if self.path.startswith("/api/assessments/"):
            aid = self.path.split("/")[-1]
            items = [a for a in store_conn.list_assessments(tid) if a["id"] == aid]
            return self._send(200, items[0]) if items else self._send(404, {"error": "Not found"})
        return self._send(404, {"error": "Not found"})

    # ---------- 路由：鉴权 + 计量 + 业务 ----------
    def do_POST(self):
        # /auth/demo-token：演示环境免密签 token（生产删除）
        if self.path == "/auth/demo-token":
            body = self._read_body()
            plan = body.get("plan", "free")
            t = tsvc.ensure_tenant(DEMO_TENANT, plan=plan)
            tok = auth.issue_token(DEMO_TENANT, "admin", plan)
            return self._send(200, {"token": tok, "tenant": t})

        claims, err = require_tenant(self)
        if err:
            return self._send(err[1], {"error": err[0]})
        tid = claims.get("tenant_id")
        role = claims.get("role", "operator")

        body = self._read_body()

        if self.path == "/api/inspections":
            rec = store_conn.create_inspection(tid, body)
            return self._send(201, rec)

        if self.path == "/api/assessments":
            # 计量 Credit：每次评估扣 1
            r = meter.record(tid, "assessment", 1)
            if not r.get("allowed"):
                return self._send(402, {"error": "quota_exceeded", "hint": "套餐 Credit 不足，请升级或充值"})
            rec = store_conn.create_assessment(tid, body)
            # 免责声明叠加（API 输出层）
            rec["disclaimer"] = store.RiskEngine.DISCLAIMER
            return self._send(201, {**rec, "credit_remaining": r.get("remaining")})

        if self.path == "/billing/upgrade":
            if role != "admin":
                return self._send(403, {"error": "admin_only"})
            plan = body.get("plan")
            amount = body.get("amount_cents", 0)
            order = billing.create_order_for_tenant(tid, plan, amount)
            t = tsvc.ensure_tenant(tid, plan=plan)
            return self._send(200, {"order": order, "tenant": t})

        # 管理后台：套餐升降级 + 充值（仅 admin）
        if self.path == "/admin/set-plan":
            if role != "admin":
                return self._send(403, {"error": "admin_only"})
            target = body.get("tenant_id") or tid
            plan = body.get("plan")
            res = tsvc.set_plan(target, plan, credits=body.get("credits"))
            return self._send(200, res) if res else self._send(400, {"error": "bad_plan"})
        if self.path == "/billing/topup":
            if role != "admin":
                return self._send(403, {"error": "admin_only"})
            amount = int(body.get("amount", 0))
            res = tsvc.topup_credit(tid, amount)
            return self._send(200, res) if res else self._send(400, {"error": "bad_amount"})

        return self._send(404, {"error": "Not found"})

    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw) if raw else {}
        except Exception:
            return {}


INDEX_HTML = """<!doctype html>
<html lang="zh">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>建筑风险评估 SaaS 演示</title>
<style>
 body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:880px;margin:24px auto;padding:0 16px;line-height:1.6}
 h1{font-size:1.4em} .card{border:1px solid #e5e5e5;border-radius:10px;padding:16px;margin:14px 0}
 label{display:block;margin-top:10px;font-weight:600} input{padding:8px;width:100%;max-width:320px}
 button{margin-top:16px;padding:9px 18px;background:#c62828;color:#fff;border:none;border-radius:6px;cursor:pointer}
 .lvl{font-size:1.2em;font-weight:700} .muted{color:#888;font-size:.9em}
 .rec li{margin-left:18px} .ok{color:#2e7d32}.warn{color:#e65100}
</style></head>
<body>
<h1>🏗️ 建筑结构风险评估 SaaS（演示）</h1>
<div class="card">
 <button id="login" onclick="login()">登录演示租户</button>
 <span class="muted" id="st">未登录</span>
</div>
<div class="card" id="form" style="display:none">
 <label>混凝土强度 (MPa)</label><input id="cs" type="number" step="0.1" value="12">
 <label>钢筋保护层 (mm)</label><input id="rc" type="number" step="0.1" value="14">
 <label>裂缝宽度 (mm)</label><input id="cw" type="number" step="0.01" value="0.6">
 <button onclick="assess()">评估风险</button>
 <button onclick="credit()" class="muted" style="background:none;color:#888">查看 Credit</button>
</div>
<div class="card" id="out" style="display:none">
 <h2>结果</h2>
 <div>风险分：<span id="score"></span> ｜ 等级：<span id="level" class="lvl"></span></div>
 <h3>建议</h3><ul id="recs" class="rec"></ul>
 <div class="muted" id="dis"></div>
</div>
<script>
 let token="",tenant="demo";
 function token(){return token;}
 async function login(){
   const r=await fetch("/auth/demo-token",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({plan:"free"})});
   const d=await r.json();token=d.token;
   document.getElementById("st").textContent="已登录 demo (plan="+d.tenant.plan+")";
   document.getElementById("form").style.display="block";
 }
 async function assess(){
   const body={metrics:{concrete_strength_mpa:+document.getElementById("cs").value,
     rebar_cover_mm:+document.getElementById("rc").value,crack_width_mm:+document.getElementById("cw").value}};
   const r=await fetch("/api/assessments",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+token},body:JSON.stringify(body)});
   if(r.status===402){alert("Credit 不足");document.getElementById("st").textContent="Credit 不足";return;}
   const d=await r.json();
   document.getElementById("out").style.display="block";
   document.getElementById("score").textContent=d.risk_score;
   document.getElementById("level").textContent=d.risk_level;
   document.getElementById("level").className="lvl "+(d.risk_score>=50?"warn":"ok");
   document.getElementById("recs").innerHTML=d.recommendations.map(x=>"<li>"+x+"</li>").join("");
   document.getElementById("dis").textContent=d.disclaimer;
   document.getElementById("st").textContent="剩余 Credit: "+d.credit_remaining;
 }
 async function credit(){
   const r=await fetch("/billing/credit",{headers:{Authorization:"Bearer "+token}});
   const d=await r.json();alert("plan="+d.plan+" 剩余Credit="+d.credits);
 }
</script>
</body></html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("JZ_SAAS_PORT", 8080))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"jianzhu-saas API (tenant+jwt+meter+billing) running on :{port}")
    server.serve_forever()
