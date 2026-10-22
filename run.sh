#!/usr/bin/env bash
# run.sh — jianzhu-saas 一键启动
# 用法：./run.sh [--open]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "📦 Installing dependencies..."
pip install -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt 2>/dev/null || echo "(no deps needed)"

PORT="${JZ_SAAS_PORT:-8080}"
echo "🚀 Starting jianzhu-saas API on port $PORT..."

# 后台启动
python3 api_server.py &
SERVER_PID=$!
sleep 2

# 健康检查
if curl -s "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then
  echo "✅ Server healthy at http://127.0.0.1:$PORT"
else
  echo "⚠️  Server may still be starting..."
fi

# --open 参数：自动打开浏览器
if [ "${1:-}" = "--open" ]; then
  echo "🌐 Opening landing page..."
  if command -v xdg-open &>/dev/null; then
    xdg-open "http://127.0.0.1:$PORT/landing/index.html" 2>/dev/null &
  elif command -v open &>/dev/null; then
    open "http://127.0.0.1:$PORT/landing/index.html" 2>/dev/null &
  elif command -v start &>/dev/null; then
    start "http://127.0.0.1:$PORT/landing/index.html" 2>/dev/null &
  fi
fi

echo "PID=$SERVER_PID — Press Ctrl+C to stop"
trap "kill $SERVER_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait $SERVER_PID
