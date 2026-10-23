#!/usr/bin/env bash
# jianzhu-saas 静态冒烟：billing.enforce_paywall + 入口语法（不依赖运行中服务）
set -uo pipefail
cd "$(dirname "$0")"
PASS=0; FAIL=0
python3 -c "
import billing
r = billing.enforce_paywall('free','arch')
assert r.get('allowed') is True, r
print('billing.enforce_paywall OK', r)
plans = billing.get_pricing_plans()
print('get_pricing_plans 档位数:', len(plans))
" && PASS=$((PASS+1)) || { echo "FAIL: billing"; FAIL=$((FAIL+1)); }
python3 -c "import ast; ast.parse(open('api_server.py').read()); print('api_server.py 语法 OK')" \
  && PASS=$((PASS+1)) || { echo "FAIL: 入口语法"; FAIL=$((FAIL+1)); }
echo "smoke_static: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && echo "=== SMOKE PASS ===" && exit 0 || { echo "=== SMOKE FAIL ==="; exit 1; }
