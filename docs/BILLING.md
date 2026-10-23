# jianzhu-saas 收款与门控（爱发电 afdian + 多网关）

## 定价档位（与 billing PAYWALL_RULES 对齐）
| 档位 | 价格 | 限制 |
|---|---|---|
| Free | ¥0 | 3 次/天 |
| Pro | ¥199/月 | 999 次/天 |
| Team | ¥399/月 | 999 次/天 + 5 租户 |
| 企业 | 定制 | SLA+定制 |

## 收款流程（先体验后付费）
1. 免费 3 次/天，超限 402 + 升级链接（爱发电 https://afdian.com/@Zeon7744）
2. 支持 4 网关：Noop/WxPay/Aishouqian/Afdian，默认 noop 安全降级
3. 付款 → gateway.query_callback 核验 → 本地提权

## 环境变量
`JZ_AFDIAN_USER` / `JZ_AFDIAN_TOKEN` / `BILLING_GATEWAY`（noop|wxpay|aishouqian|afdian）
