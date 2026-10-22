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
echo "=== Result: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
