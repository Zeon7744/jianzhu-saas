# jianzhu-saas —— 建筑结构风险评估 SaaS（最小付费功能）

面向中小型建筑/检测/监理企业的**建筑结构风险评估** API。
输入混凝土强度、钢筋保护层、裂缝宽度，输出 0–100 风险分、风险等级与整改建议。

## 功能（只列真实具备的）
- 建筑结构风险评估：`POST /api/assessments`
- 检测记录台账：`POST /api/inspections`
- 多租户隔离：数据按 `tenant_id` 隔离，可私有部署
- 计费 Credit 计量：每次评估扣 1 Credit，套餐配额（free/pro/enterprise）
- 收款预留接口：`create_order / query_callback / refund`（未接具体支付网关，MVP 默认 NoopGateway）

## 运行
```
python api_server.py          # 默认 :8080
JZ_SAAS_PORT=9000 python api_server.py
```
访问 `http://127.0.0.1:8080/` 打开演示页，登录 demo 租户后录入三项指标即可出评估。

## 鉴权
```
# 演示环境签发 token（生产替换为正式租户签发）
curl -X POST :8080/auth/demo-token -d '{"plan":"free"}' -H 'Content-Type: application/json'
# 带 token 调用评估
curl -X POST :8080/api/assessments -H "Authorization: Bearer <token>" \
     -d '{"metrics":{"concrete_strength_mpa":12,"rebar_cover_mm":14,"crack_width_mm":0.6}}'
```

## 免责声明（产品层）
本系统输出**仅为算法参考**。任何结构安全判定、加固或停用决策，必须由**持证结构工程师**签字负责。

## 国内收款（预留，不填密钥即可跑通）
- 内置三个网关：`noop`（默认占位）/ `wepay`（微信商户）/ `aishouqian`（爱收钱聚合）。
- 用环境变量 `JZ_SAAS_BILLING_GATEWAY` 切换；缺省 `noop`。
- 配齐密钥后自动走真实下单：`JZ_WXPAY_MCHID / JZ_WXPAY_APPID / JZ_WXPAY_API_KEY`，或 `JZ_AISHOUQIAN_MCH_NO / JZ_AISHOUQIAN_TOKEN / JZ_AISHOUQIAN_APPID`。
- 未配密钥时网关返回 `created_pending_key` 并列出 `needs_secret`，前端据此提示"待开通支付"。

## 测试
```
python3 -m unittest tests.test_api tests.test_billing -v
```
