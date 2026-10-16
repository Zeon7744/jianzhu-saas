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
