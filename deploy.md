# jianzhu-saas 部署指南

## 1. Docker 部署

```bash
# 构建镜像（已含 Dockerfile）
docker build -t jianzhu-saas:latest .

# 运行（默认端口 8080，noop 网关）
docker run -d --name jz-saas \
  -p 8080:8080 \
  -e JZ_SAAS_BILLING_GATEWAY=noop \
  -e JZ_SAAS_DEMO_TENANT=demo \
  jianzhu-saas:latest

# 接爱发电真实网关
docker run -d --name jz-saas \
  -p 8080:8080 \
  -e JZ_SAAS_BILLING_GATEWAY=afdian \
  -e JZ_SAAS_AFDIAN_USER=your_user_id \
  -e JZ_SAAS_AFDIAN_TOKEN=your_api_token \
  -e JZ_SAAS_AFDIAN_RETURN=https://yourdomain.com/success \
  jianzhu-saas:latest
```

## 2. 本地一键启动

```bash
# 克隆 + 启动（零依赖，纯标准库）
git clone https://gitee.com/Zeon7744/jianzhu-saas.git
cd jianzhu-saas
chmod +x run.sh smoke_test.sh
./run.sh --open        # 启动 API + 自动打开浏览器
./smoke_test.sh        # 跑冒烟测试（6 项断言）
```

环境变量（可选）：
- `JZ_SAAS_PORT`：API 端口（默认 8080）
- `JZ_SAAS_BILLING_GATEWAY`：noop/wepay/aishouqian/afdian
- `JZ_SAAS_DEMO_TENANT`：演示租户 ID

## 3. 微信小程序审核要点

1. **主体资质**：需企业主体（个体工商户也行）才能上架小程序；个人主体只能用"体验版"分发
2. **支付接入**：小程序内购必须走微信支付方式（JSAPI），即 `JZ_SAAS_BILLING_GATEWAY=wepay`；爱发电/爱收钱仅用于 H5/公众号场景
3. **内容合规**：建筑风险评估属于"工具类"小程序，需在简介中注明"仅供参考，不作为工程验收依据"（免责声明已内置在 API 输出和前端页面）；避免使用"鉴定""认证"等需资质的措辞
