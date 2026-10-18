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

---

## ⚖️ 法控声明（SaaS 数据与合规）

- **数据不用于训练**：用户上传的项目数据、评估记录、租户配置**仅用于当次功能计算**，本系统**不将任何用户数据用于模型训练、微调或二次数据开发**；数据按租户隔离存储（`WHERE tenant_id=?`），跨租户不可见。
- **非结构安全判定**：所有算法输出仅为参考，不替代持证工程师的法定判定与签字责任。
- **隐私条款**：仅采集运行必需数据，不采集与功能无关的个人信息；数据保留期限与删除请求见产品层说明。
- **收款合规**：收款走爱发电/爱收钱/微信商户网关（见 `billing.py`，权益发放待联调），本仓不直接经手资金结算，仅做权益发放接口对接。

---

## 🚀 免费 → Pro → 企业（变现入口）

免费=100 次评估/月；Pro=无限评估+PDF 报告导出；企业=私有部署+定制算法

- **免费**：立即 [安装/克隆] 使用，命中配额即可升级。
- **Pro**：[Gitee Pro 订阅](https://gitee.com/Zeon7744) 解锁高级能力。
- **企业**：私有部署 / 定制需求 → 见 `pricing.md`，或联系商务（GitHub Issues / Gitee）。

> 详细定价与 SKU 见 [pricing.md](pricing.md) ｜ 支持项目见 [FUNDING.yml](FUNDING.yml)

---

## 快速上手
依赖安装：
```bash
python3 -m pip install -r requirements.txt
```

## 变现路径
免费 → Pro 订阅 → 企业定制；收款走爱发电/爱收钱/微信商户网关（billing.py），权益发放待联调。
> 定价与赞助：见仓库内 pricing.md / FUNDING.yml（若有）。

---

## 🏢 企业版功能（来自 jianzhu-agent 合并）

以下功能已从 `jianzhu-agent` 合并入企业版：

### 新增能力
- **ReAct Agent 思维引擎**：推理+执行循环，支持自动查询数据库、搜索知识库、风险检查
- **多 Agent 协作**：智管/智财/智项/智检/智安/智石六大专业 Agent
- **知识库检索**：语义检索 + 关键词匹配混合搜索
- **Agent 协作编排**：多 Agent 任务分配与结果汇总

### 企业版 Demo
```bash
# 端到端自动化巡检闭环
python demo_pipeline.py
```

### 企业版调用示例
```python
from src.enterprise.agent import create_agent, ReActAgent

# 创建专业 Agent
agent = create_agent("智检")  # 检测质量 Agent

# ReAct 推理
react = ReActAgent(agent)
result = react.run("帮我分析最近的检测异常报告")
```

> 📦 企业版功能需 Pro/企业订阅解锁；免费版仅含基础 API。
