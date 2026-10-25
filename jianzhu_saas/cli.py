# -*- coding: utf-8 -*-
"""jianzhu-saas 一键启动 CLI

设计目标：clone 后 30 秒内能跑起一个可用的建筑 SaaS 演示（Web 版即用，零第三方依赖）。

入口:
    python -m jianzhu_saas.cli                     # 默认 :8080，浏览器开 http://127.0.0.1:8080/
    python -m jianzhu_saas.cli --port 8000         # 换端口
    python -m jianzhu_saas.cli --db :memory:        # 内存库（临时演示，不落 data/）
    python -m jianzhu_saas.cli --gateway mbd    # 切换支付网关
    python -m jianzhu_saas.cli --print-token demo   # 打印演示 Bearer token + 现成 curl 后退出

演示路径（30 秒跑通）:
  1. 启动:  python -m jianzhu_saas.cli
  2. 浏览器打开 http://127.0.0.1:8080/ → 点「登录演示租户」→ 三项指标 → 评估风险
  3. 或 curl（另开终端）:
     TOKEN=$(curl -s -X POST :8080/auth/demo-token -d '{"plan":"free"}' -H 'Content-Type: application/json' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
     curl -s -X POST :8080/api/assessments -H "Authorization: Bearer $TOKEN" \
          -H "Content-Type: application/json" \
          -d '{"metrics":{"concrete_strength_mpa":12,"rebar_cover_mm":14,"crack_width_mm":0.6}}'
     # → 201 {"risk_score":...,"risk_level":"CRITICAL","recommendations":[...],"disclaimer":"..."}
"""
import argparse
import json
import os
import sys

# Windows GBK 控制台中文输出兵陷：强制 stdout 转 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# 把仓库根加进 sys.path（api_server/store/auth/billing 都是仓库根级模块）
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import api_server  # noqa: E402
import billing     # noqa: E402
import store       # noqa: E402


def _print_token(known_tenants) -> None:
    """打印演示 token 生成方式（服务端 /auth/demo-token 是权威来源），附现成 curl。"""
    port = os.environ.get("JZ_SAAS_PORT", "8080")
    print(f"# 1) 获取演示 token（服务端签发，权威来源）:")
    print(f'curl -s -X POST http://127.0.0.1:{port}/auth/demo-token \\')
    print('  -d \'{"plan":"free"}\' -H "Content-Type: application/json"')
    print()
    print(f"# 2) 拿 token 调评估接口（CRITICAL 场景）:")
    print(f'TOKEN=$(curl -s -X POST http://127.0.0.1:{port}/auth/demo-token \\')
    print(f'  -d \'{{"plan":"free"}}\' -H "Content-Type: application/json" | python -c "import sys,json;print(json.load(sys.stdin)[\'token\'])")')
    print(f'curl -s -X POST http://127.0.0.1:{port}/api/assessments \\')
    print(f'  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\')
    print('  -d \'{"metrics":{"concrete_strength_mpa":12,"rebar_cover_mm":14,"crack_width_mm":0.6}}\'')


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="python -m jianzhu_saas.cli",
        description="jianzhu-saas 一键启动（Web 演示版，纯标准库，无第三方依赖）",
    )
    ap.add_argument("--port", type=int, default=None,
                    help="覆盖 JZ_SAAS_PORT（默认 8080）")
    ap.add_argument("--db", default=None,
                    help="覆盖 JZ_SAAS_DB（默认 data/jianzhu_saas.db，可传 :memory:）")
    ap.add_argument("--gateway", default=None,
                    choices=sorted(billing.BUILTIN_REGISTRY),
                    help="覆盖 JZ_BILLING_GATEWAY（默认 noop）")
    ap.add_argument("--print-token", action="store_true",
                    help="打印演示 token 获取 + 现成 curl 示例后退出（不启动服务）")
    args = ap.parse_args()

    if args.port:
        os.environ["JZ_SAAS_PORT"] = str(args.port)
    if args.db:
        os.environ["JZ_SAAS_DB"] = args.db
    if args.gateway:
        os.environ["JZ_BILLING_GATEWAY"] = args.gateway

    if args.print_token:
        _print_token(api_server.DEMO_TENANT)
        return 0

    port = int(os.environ.get("JZ_SAAS_PORT", "8080"))
    print("=" * 62)
    print(" jianzhu-saas  结构评估 SaaS · 一键演示模式")
    print("=" * 62)
    print(f"  数据源    {os.environ.get('JZ_SAAS_DB', store.DB_PATH)}")
    print(f"  支付网关  {os.environ.get('JZ_BILLING_GATEWAY', 'noop')}"
          f"（可选: {', '.join(sorted(billing.BUILTIN_REGISTRY))}）")
    print(f"  演示页    浏览器打开 http://127.0.0.1:{port}/")
    print(f"  API 文档  /health  /auth/demo-token  /api/assessments  /billing/credit")
    print(f"  静态落地页 另开浏览器打开 ./landing/index.html（免费/Pro/企业 CTA）")
    print("-" * 62)
    print(" Ctrl+C 停止。")
    print("-" * 62)

    server = api_server.build_server(port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[stop] 已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
