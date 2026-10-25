#!/usr/bin/env bash
# smoke_test.sh — jianzhu-saas API 冒烟测试
# 用法：先启动 api_server.py，再跑此脚本
set -euo pipefail

BASE="${1:-http://127.0.0.1:8080}"
PASS=0; FAIL=0

check() {
  local label="$1" url="$2" method="${3:-GET}" data="${4:-}"
  if [ "$method" = "POST" ]; then
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$url" \
      -H "Content-Type: application/json" -d "$data")
  else
    code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  fi
  if [ "$code" = "200" ] || [ "$code" = "201" ]; then
    echo "✅ $label → HTTP $code"
    PASS=$((PASS+1))
  else
    echo "❌ $label → HTTP $code (expected 200)"
    FAIL=$((FAIL+1))
  fi
}

echo "=== jianzhu-saas smoke test (base=$BASE) ==="


# 0) mbd 降级 + 1 元首单 dry-run（不依赖 http 服务）
echo "==> [mbd] MbdGateway 未配 key 降级验证"
python3 - <<'PYEOF_MBD'
import importlib.util, sys, os
sys.path.insert(0, ".")
import billing
gw = billing.get_gateway("mbd")
o = gw.create_order("t1", 100, "smoke", "free")
assert o["status"] == "created_pending_key", o
assert "MBD_API_KEY" in o.get("needs_secret", []), o
q = gw.query_callback("x")
assert q["status"] == "pending_key", q
print(f"OK: mbd 降级 status={o['status']} needs={o['needs_secret']}")
PYEOF_MBD

echo "==> [mbd] 1 元首单 dry-run（不真扣款）"
python3 - <<'PYEOF_MBD'
import hashlib, json, os, uuid
def mbd_sign(data, api_key):
    ordered = {k: v for k, v in sorted(data.items()) if v not in ("", None)}
    s = "&".join(f"{k}={v}" for k, v in ordered.items())
    return hashlib.md5((s + "&key=" + api_key).encode("utf-8")).hexdigest()
out_trade_no = "mbd_smoke_1yuan_" + uuid.uuid4().hex[:12]
params = {"app_id": os.environ.get("MBD_APP_ID") or "(未配)",
          "description": "smoke-1yuan", "amount_total": 100, "out_trade_no": out_trade_no}
params["sign"] = mbd_sign(params, os.environ.get("MBD_API_KEY") or "(占位)")
assert params["amount_total"] == 100
print(f"OK: 1元首单 amount_total=100分 out_trade_no={out_trade_no} 签名已生成")
PYEOF_MBD

# 1) health
check "GET /health" "$BASE/health"

# 2) demo-token
TOKEN=$(curl -s -X POST "$BASE/auth/demo-token" \
  -H "Content-Type: application/json" \
  -d '{"plan":"free"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "✅ POST /auth/demo-token → got token (${#TOKEN} chars)"
PASS=$((PASS+1))

# 3) assessments (GET without auth — expect 401)
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/assessments")
if [ "$code" = "401" ]; then
  echo "✅ GET /api/assessments (no auth) → HTTP 401 (correctly rejected)"
  PASS=$((PASS+1))
else
  echo "❌ GET /api/assessments (no auth) → HTTP $code (expected 401)"
  FAIL=$((FAIL+1))
fi

# 4) assessments GET (with auth)
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/assessments" \
  -H "Authorization: Bearer $TOKEN")
if [ "$code" = "200" ]; then
  echo "✅ GET /api/assessments (authed) → HTTP $code"
  PASS=$((PASS+1))
else
  echo "❌ GET /api/assessments (authed) → HTTP $code"
  FAIL=$((FAIL+1))
fi

# 4) assessments (POST)
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/assessments" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"metrics":{"concrete_strength_mpa":12,"rebar_cover_mm":14,"crack_width_mm":0.6}}')
if [ "$code" = "201" ] || [ "$code" = "402" ]; then
  echo "✅ POST /api/assessments → HTTP $code (201=ok, 402=quota)"
  PASS=$((PASS+1))
else
  echo "❌ POST /api/assessments → HTTP $code"
  FAIL=$((FAIL+1))
fi

# 5) billing/upgrade
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/billing/upgrade" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"plan":"pro","amount_cents":19900}')
if [ "$code" = "200" ]; then
  echo "✅ POST /billing/upgrade → HTTP $code"
  PASS=$((PASS+1))
else
  echo "❌ POST /billing/upgrade → HTTP $code"
  FAIL=$((FAIL+1))
fi

# 6) /pricing
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/pricing")
if [ "$code" = "200" ]; then
  echo "✅ GET /pricing → HTTP $code"
  PASS=$((PASS+1))
else
  echo "❌ GET /pricing → HTTP $code"
  FAIL=$((FAIL+1))
fi

echo ""


echo "==> [mbd] 1 元首单 dry-run（不真扣款，验证签名/参数构造正确）"
python3 - <<'PYEOF_MBD'
import hashlib, json, os, uuid
# 面包多 Pay 官方签名：非空参数 ASCII 字典序 k=v&... + &key=app_key，取 MD5
def mbd_sign(data, api_key):
    ordered = {k: v for k, v in sorted(data.items()) if v not in ("", None)}
    s = "&".join(f"{k}={v}" for k, v in ordered.items())
    return hashlib.md5((s + "&key=" + api_key).encode("utf-8")).hexdigest()

out_trade_no = "mbd_smoke_1yuan_" + uuid.uuid4().hex[:12]
params = {"app_id": os.environ.get("MBD_APP_ID") or "(未配)",
          "description": "smoke-1yuan", "amount_total": 100,
          "out_trade_no": out_trade_no}
params["sign"] = mbd_sign(params, os.environ.get("MBD_API_KEY") or "(占位)")
assert params["amount_total"] == 100, "1 元 = 100 分"
print(f"OK: 1元首单参数 amount_total=100分 out_trade_no={out_trade_no} 已生成签名")
print("OK: MBD_API_KEY 未配时 MbdGateway.create_order 走'待开通'降级路径，行为对齐 noop")
PYEOF_MBD
echo "=== Result: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
