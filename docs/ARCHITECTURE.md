# jianzhu-saas 模块结构

## 目录
```
jianzhu-saas/
├── app/              # SaaS 应用（蓝图/路由）
├── billing/          # 收款层（gateway: WxPay/Aishouqian/mbd + Noop）
├── landing/          # 落地页 + 样片展示
├── smoke_test.sh / run.sh
└── docs/
```

## 数据流
1. Web 客户端 → Flask 路由 → 架构分析引擎
2. 调用前走 `billing` 门控（PAYWALL_RULES: free 3/天, pro 999/天, team 999/天 5 租户）
3. 超限 402 + 升级链接（面包多 Pay https://mbd.com/@Zeon7744）

## 门控模型
- 4 网关：NoopGateway / WxPayGateway / AishouqianGateway / MbdGateway
- Pro ¥199/月，Team ¥399/月
