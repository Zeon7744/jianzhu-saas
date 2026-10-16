# jianzhu-saas 最小付费功能改造记录 · 20261016

## 目标
把 jianzhu-saas 从空壳 README 落地为"建筑结构评估 API + 单用户 + 1 个收款 SKU"最小可收费原型，对齐投资顾问结论。

## 改动清单（commit 8caaf5f）
| 文件 | 说明 |
| --- | --- |
| store.py | SQLite 多租户存储层，tenants/inspections/assessments/usage_events 全带 tenant_id |
| auth.py | 纯标准库 HMAC-SHA256 自实现 JWT，free/pro/enterprise 角色来自 tenant.plan |
| billing.py | 收款抽象 create_order/query_callback/refund，NoopGateway 默认，BUILTIN_REGISTRY 预留 |
| api_server.py | 路由层强制 require_tenant，assess 扣 1 Credit 配额（free=100/pro=10000/enterprise 不限），超额 402 quota_exceeded |
| requirements.txt | 无第三方依赖声明 |
| .gitignore | 忽略 __pycache__、data/*.db |
| README.md | 重写为真实能力清单 + 免责声明 + 持证工程师背书 |

## 合规约束落实（三处免责）
1. API 响应：assessments 返回带 disclaimer 字段
2. 产品层：README + 演示页叠加免责声明
3. 报告层：records 导出保留 disclaimer

## 本地验证
- 启动自检：`python api_server.py` 正常监听（timeout=124 超时退出）
- whoami / assess(100分 CRITICAL 扣 1 Credit) / credit(100→99) / 缺 token 401 / 首页 200

## 遗留项
- 真实支付网关接入（当前 NoopGateway）
- 正式租户签发流程（生产关闭 demo 免密入口）
- SQLite → PostgreSQL
- 升级套餐自动发放 credits 闭环
- PDF 报告导出
