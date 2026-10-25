"""
jianzhu-saas: 建筑结构风险评估 SaaS API（最小付费功能）

改造点（对照方案第 4 节）：
1. tenant_id 多租户隔离（store.py SQLite）
2. JWT 鉴权 + 角色 free/pro/enterprise（auth.py）
3. 计量事件 + 套餐 Credit 配额（store.UsageMeter）
4. order_service 三方法预留国内收款（billing.py）
5. 最小前端演示页（GET /）
6. 免责声明叠加在 API / 报告 / 产品三处
P0 改造：
7. 检测记录台账入口（GET /ledger）
8. Free 用户付费墙（导出完整报告需 Pro）
9. 销售话术落地页展示
10. 爱收钱/面包多 Pay网关收款闭环
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
PRO_PRICE_CENTS = 19900  # ¥199/月 Pro


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
        if self.path == "/ledger":
            return self._send(200, LEDGER_HTML, "text/html; charset=utf-8")
        if self.path == "/health":
            return self._send(200, {"status": "ok", "time": time.time()})
        if self.path == "/pricing":
            return self._send(200, billing.get_pricing_plans())

        claims, err = require_tenant(self)
        if err:
            return self._send(err[1], {"error": err[0]})
        tid = claims.get("tenant_id")
        t = tsvc.get(tid) or tsvc.ensure_tenant(tid, plan=claims.get("plan", "free"))

        if self.path == "/auth/whoami":
            return self._send(200, {"tenant": t, "role": claims.get("role")})
        if self.path == "/billing/credit":
            return self._send(200, {"tenant_id": tid, "credits": t["credits"], "plan": t["plan"]})
        if self.path == "/billing/rights":
            r = tsvc.get_rights(tid)
            if r is None:
                tsvc.apply_plan_rights(tid, t.get("plan", "free"))
                r = tsvc.get_rights(tid)
            return self._send(200, {
                "tenant_id": tid, "plan": t["plan"], "credits": t["credits"],
                "rights": r, "monthly_quota": r["monthly_quota"] if r else 100,
                "report_level": r["report_level"] if r else "basic", "seats": r["seats"] if r else 1,
            })
        if self.path.startswith("/billing/order/"):
            oid = self.path.split("/")[-1]
            g = billing.get_gateway()
            res = g.query_callback(oid)
            return self._send(200, {"order_id": oid, **res})
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
            if not items:
                return self._send(404, {"error": "Not found"})
            item = items[0]
            # 付费墙：导出完整报告需 Pro
            r = tsvc.get_rights(tid)
            can_export_full = r and r.get("report_level") == "full"
            if not can_export_full:
                # Free 用户只返回风险分和评级，隐藏条文引用
                item["full_report"] = False
                item["code_citations"] = []
            else:
                item["full_report"] = True
            return self._send(200, {**item, "disclaimer": store.RiskEngine.DISCLAIMER})
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
            # 付费墙：Free 用户每日限 3 次评估
            _t = tsvc.get(tid) or tsvc.ensure_tenant(tid, plan=claims.get("plan", "free"))
            plan = _t.get("plan", "free")
            pw = billing.enforce_paywall(plan, "assessment", tenant_id=tid)
            if not pw.get("allowed"):
                return self._send(402, {"error": "paywall", "reason": pw["reason"], "upgrade_url": pw.get("upgrade_url", "/pricing")})
            # 计量 Credit：每次评估扣 1
            r = meter.record(tid, "assessment", 1)
            if not r.get("allowed"):
                return self._send(402, {"error": "quota_exceeded", "hint": "套餐 Credit 不足，请升级或充值"})
            rec = store_conn.create_assessment(tid, body)
            # 免责声明叠加（API 输出层）
            rec["disclaimer"] = store.RiskEngine.DISCLAIMER
            # 付费墙：Free 用户不返回条文引用
            rights = tsvc.get_rights(tid)
            if rights and rights.get("report_level") == "full":
                rec["full_report"] = True
                rec["code_citations"] = rec.get("code_citations", [])
            else:
                rec["full_report"] = False
                rec["code_citations"] = []
            return self._send(201, {**rec, "credit_remaining": r.get("remaining")})

        if self.path == "/billing/upgrade":
            if role != "admin":
                return self._send(403, {"error": "admin_only"})
            plan = body.get("plan", "pro")
            amount = body.get("amount_cents", PRO_PRICE_CENTS)
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
<title>建筑风险评估 SaaS - 检测记录台账</title>
<style>
 body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:900px;margin:0;padding:20px;line-height:1.6;background:#f8fafc}
 h1{font-size:1.5em;color:#1e293b} h2{font-size:1.2em;margin-top:20px}
 .card{border:1px solid #e2e8f0;border-radius:12px;padding:20px;margin:16px 0;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.05)}
 .badge{display:inline-block;padding:4px 10px;border-radius:20px;font-size:.8em;font-weight:600}
 .badge-free{background:#fee2e2;color:#dc2626} .badge-pro{background:#dcfce7;color:#16a34a}
 label{display:block;margin-top:12px;font-weight:600;color:#475569}
 input,select{padding:10px;width:100%;max-width:360px;border:1px solid #cbd5e1;border-radius:6px;font-size:14px}
 button{margin-top:16px;padding:10px 20px;background:#c62828;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600}
 button:hover{background:#b71c1c} button.muted{background:#f1f5f9;color:#475569} button.muted:hover{background:#e2e8f0}
 .lvl{font-size:1.3em;font-weight:700} .muted{color:#64748b;font-size:.9em}
 .rec li{margin-left:18px} .ok{color:#16a34a}.warn{color:#e65100}.danger{color:#dc2626}
 table{width:100%;border-collapse:collapse;font-size:.9em;margin-top:12px}
 th,td{padding:8px 12px;border:1px solid #e2e8f0;text-align:left}
 th{background:#f8fafc;font-weight:600}
 .paywall{background:#fffbeb;border:1px solid #fbbf24;border-radius:8px;padding:16px;margin-top:16px}
 .cta{display:inline-block;padding:10px 24px;background:#16a34a;color:#fff;border-radius:6px;text-decoration:none;font-weight:600;margin-top:12px}
 .cta:hover{background:#15803d}
 .tabs{display:flex;gap:8px;margin-bottom:16px} .tab{padding:8px 16px;border-radius:6px;cursor:pointer;font-weight:600}
 .tab.active{background:#c62828;color:#fff} .tab:not(.active){background:#f1f5f9;color:#64748b}
 .sales{text-align:center;padding:30px 20px;background:linear-gradient(135deg,#1e293b,#334155);color:#fff;border-radius:12px;margin-bottom:20px}
 .sales h2{color:#fff;margin-bottom:12px} .sales p{color:#cbd5e1;margin:8px 0}
</style></head>
<body>
<!-- 销售话术落地页 -->
<div class="sales">
 <h2>🏗️ 建筑结构风险智能评估</h2>
 <p>输入检测数据，<strong>5 秒内</strong>自动输出风险分 + 评级 + 条文引用</p>
 <p style="font-size:.9em;color:#94a3b8">面向结构工程师 / 施工方 / 高校科研——让合规风险一目了然</p>
 <a href="#ledger" class="cta" style="background:#fff;color:#c62828">免费试用</a>
</div>

<div class="card">
 <h1>📋 检测记录台账</h1>
 <div id="st" class="muted">未登录</div>
 <button id="login" onclick="login()">登录演示租户</button>
</div>

<div class="tabs" id="tabs" style="display:none">
 <div class="tab active" onclick="switchTab('assess')">风险检测</div>
 <div class="tab" onclick="switchTab('ledger')">台账记录</div>
 <div class="tab" onclick="switchTab('billing')">订阅 Pro</div>
</div>

<div class="card" id="assess-panel" style="display:none">
 <h2>输入检测指标</h2>
 <label>混凝土强度 (MPa)</label><input id="cs" type="number" step="0.1" value="12">
 <label>钢筋保护层 (mm)</label><input id="rc" type="number" step="0.1" value="14">
 <label>裂缝宽度 (mm)</label><input id="cw" type="number" step="0.01" value="0.6">
 <label>钢筋锈蚀率 (%)</label><input id="corr" type="number" step="0.1" value="0">
 <label>碳化深度 (mm)</label><input id="carb" type="number" step="0.1" value="0">
 <label>沉降位移 (mm)</label><input id="settle" type="number" step="0.1" value="0">
 <label>荷载比 (-)</label><input id="load" type="number" step="0.01" value="0.5">
 <button onclick="assess()">评估风险</button>
</div>

<div class="card" id="result-panel" style="display:none">
 <h2>评估结果</h2>
 <div>风险分：<span id="score" class="lvl"></span> ｜ 等级：<span id="level" class="lvl"></span></div>
 <div id="paywall" class="paywall" style="display:none">
  <p>🔒 <strong>完整报告（含条文引用）需 Pro 订阅</strong></p>
  <p class="muted">Free 用户仅显示风险分与评级，Pro 用户可导出含条文引用的完整报告</p>
  <a href="#" class="cta" onclick="showBilling()">立即升级 Pro (¥199/月)</a>
 </div>
 <h3>分项得分</h3>
 <table id="bd"><tr style="font-weight:600"><td>维度</td><td>值</td><td>风险</td><td>权重</td><td>贡献</td></tr></table>
 <h3>整改建议</h3>
 <ul id="recs" class="rec"></ul>
 <div id="citations" style="display:none">
  <h3>条文引用</h3>
  <ul id="cit-list"></ul>
 </div>
 <div class="muted" id="dis"></div>
 <div id="credit-info" class="muted"></div>
</div>

<div class="card" id="ledger-panel" style="display:none">
 <h2>检测记录台账</h2>
 <p class="muted">历史评估记录列表</p>
 <button onclick="loadLedger()">刷新台账</button>
 <table id="ledger-table">
  <tr style="font-weight:600"><td>时间</td><td>风险分</td><td>等级</td><td>指标数</td></tr>
 </table>
</div>

<div class="card" id="billing-panel" style="display:none">
 <h2>升级 Pro 订阅</h2>
 <div class="card" style="border-color:#16a34a">
  <h3>Pro 套餐 ¥199/月</h3>
  <ul style="margin:12px 0;padding-left:20px">
   <li>无限次风险评估</li>
   <li>导出含条文引用的完整报告</li>
   <li>3 人团队协作</li>
   <li>优先技术支持</li>
  </ul>
  <button onclick="upgrade()" style="background:#16a34a">立即订阅</button>
 </div>
 <div id="order-info" class="muted"></div>
</div>

<script>
 let token="",tenant="demo",currentPlan="free";
 function switchTab(name){
  ["assess","ledger","billing"].forEach(t=>{
   document.getElementById(t+"-panel").style.display=t===name?"block":"none";
  });
  document.querySelectorAll(".tab").forEach((el,i)=>{
   el.classList.toggle("active",["assess","ledger","billing"][i]===name);
  });
 }
 async function login(){
  const r=await fetch("/auth/demo-token",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({plan:"free"})});
  const d=await r.json();token=d.token;currentPlan=d.tenant.plan;
  document.getElementById("st").textContent="已登录 demo (plan="+d.tenant.plan+")";
  document.getElementById("form").style.display="block";
  document.getElementById("tabs").style.display="flex";
  document.getElementById("assess-panel").style.display="block";
  updatePlanBadge();
 }
 function updatePlanBadge(){
  const badge=document.createElement("span");
  badge.className="badge badge-"+(currentPlan==="pro"?"pro":"free");
  badge.textContent=currentPlan.toUpperCase();
  document.getElementById("st").prepend(badge);
 }
 async function assess(){
  const body={metrics:{concrete_strength_mpa:+document.getElementById("cs").value,
    rebar_cover_mm:+document.getElementById("rc").value,crack_width_mm:+document.getElementById("cw").value,
    rebar_corrosion_pct:+document.getElementById("corr").value,
    carbonation_depth_mm:+document.getElementById("carb").value,
    settlement_mm:+document.getElementById("settle").value,
    load_ratio:+document.getElementById("load").value}};
  const r=await fetch("/api/assessments",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+token},body:JSON.stringify(body)});
  if(r.status===402){alert("Credit 不足，请升级 Pro");return;}
  const d=await r.json();
  document.getElementById("result-panel").style.display="block";
  document.getElementById("score").textContent=d.risk_score;
  document.getElementById("level").textContent=d.risk_level;
  const lvl=document.getElementById("level");
  lvl.className="lvl "+(d.risk_score>=70?"danger":d.risk_score>=50?"warn":"ok");
  (d.breakdown||[]).forEach(b=>{var tr=document.createElement("tr");
    tr.innerHTML="<td>"+b.dimension+"</td><td>"+b.value+"</td><td>"+b.item_risk+"</td><td>"+b.weight+"</td><td>"+b.contribution+"</td>";
    var t=document.getElementById("bd");t.insertBefore(tr,t.firstChild);});
  document.getElementById("recs").innerHTML=d.recommendations.map(x=>"<li>"+x+"</li>").join("");
  // 付费墙逻辑
  if(d.full_report){
   document.getElementById("paywall").style.display="none";
   document.getElementById("citations").style.display="block";
   document.getElementById("cit-list").innerHTML=(d.code_citations||[]).map(x=>"<li>"+x+"</li>").join("");
  }else{
   document.getElementById("paywall").style.display="block";
   document.getElementById("citations").style.display="none";
  }
  document.getElementById("dis").textContent=d.disclaimer;
  document.getElementById("credit-info").textContent="剩余 Credit: "+d.credit_remaining;
 }
 async function loadLedger(){
  const r=await fetch("/api/assessments",{headers:{Authorization:"Bearer "+token}});
  const d=await r.json();
  const t=document.getElementById("ledger-table");
  (d.items||[]).forEach(a=>{
   var tr=document.createElement("tr");
   var dt=new Date(a.created*1000).toLocaleString("zh-CN");
   tr.innerHTML="<td>"+dt+"</td><td>"+a.risk_score+"</td><td>"+a.risk_level+"</td><td>"+Object.keys(a.data?.metrics||{}).length+"</td>";
   t.insertBefore(tr,t.firstChild);
  });
 }
 function showBilling(){switchTab("billing");}
 async function upgrade(){
  const r=await fetch("/billing/upgrade",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({plan:"pro",amount_cents:19900})});
  const d=await r.json();
  if(d.order.pay_url){
   window.open(d.order.pay_url,"_blank");
   document.getElementById("order-info").textContent="订单创建成功，请在打开的页面完成支付";
  }else{
   document.getElementById("order-info").textContent="下单失败: "+JSON.stringify(d.order);
  }
 }
</script>
</body></html>
"""

LEDGER_HTML = """<!doctype html>
<html lang="zh">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>检测记录台账 - jianzhu-saas</title>
<style>
 body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:900px;margin:20px auto;padding:0 16px}
 .card{border:1px solid #e2e8f0;border-radius:12px;padding:20px;margin:16px 0;background:#fff}
 table{width:100%;border-collapse:collapse;font-size:.9em}
 th,td{padding:10px;border:1px solid #e2e8f0;text-align:left}
 th{background:#f8fafc}
 .btn{padding:8px 16px;background:#c62828;color:#fff;border:none;border-radius:6px;cursor:pointer}
</style></head>
<body>
<h1>📋 检测记录台账</h1>
<div class="card">
 <button class="btn" onclick="login()">登录获取台账</button>
 <div id="st" class="muted">未登录</div>
</div>
<div class="card" id="table-card" style="display:none">
 <button class="btn" onclick="loadLedger()">刷新台账</button>
 <table id="ledger">
  <tr><th>时间</th><th>风险分</th><th>等级</th><th>指标数</th></tr>
 </table>
</div>
<script>
let token="";
async function login(){
 const r=await fetch("/auth/demo-token",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({plan:"free"})});
 const d=await r.json();token=d.token;
 document.getElementById("st").textContent="已登录 demo";
 document.getElementById("table-card").style.display="block";
}
async function loadLedger(){
 const r=await fetch("/api/assessments",{headers:{Authorization:"Bearer "+token}});
 const d=await r.json();
 const t=document.getElementById("ledger");
 (d.items||[]).forEach(a=>{
  var tr=document.createElement("tr");
  tr.innerHTML="<td>"+new Date(a.created*1000).toLocaleString("zh-CN")+"</td><td>"+a.risk_score+"</td><td>"+a.risk_level+"</td><td>"+Object.keys(a.data?.metrics||{}).length+"</td>";
  t.insertBefore(tr,t.firstChild);
 });
}
</script>
</body></html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("JZ_SAAS_PORT", 8080))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"jianzhu-saas API (tenant+jwt+meter+billing+billing+爱收钱/面包多 Pay) running on :{port}")
    server.serve_forever()
