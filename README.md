# jianzhu-saas 鈥斺€?寤虹瓚缁撴瀯椋庨櫓璇勪及 SaaS锛堟渶灏忎粯璐瑰姛鑳斤級

闈㈠悜涓皬鍨嬪缓绛?妫€娴?鐩戠悊浼佷笟鐨?*寤虹瓚缁撴瀯椋庨櫓璇勪及** API銆?
杈撳叆娣峰嚌鍦熷己搴︺€侀挗绛嬩繚鎶ゅ眰銆佽缂濆搴︼紝杈撳嚭 0鈥?00 椋庨櫓鍒嗐€侀闄╃瓑绾т笌鏁存敼寤鸿銆?
## 蹇€熷紑濮嬶紙30 绉掕窇璧锋紨绀猴級

**闆剁涓夋柟渚濊禆锛岀函鏍囧噯搴?* 鈥斺€?clone 鍚庣洿鎺ヨ窇锛屼笉鐢?pip install锛?

```bash
git clone https://gitee.com/Zeon7744/jianzhu-saas.git && cd jianzhu-saas
python -m jianzhu_saas.cli          # 鍚姩鍚庢祻瑙堝櫒鎵撳紑 http://127.0.0.1:8080/
```

1. **瑁呬緷璧?*锛氭棤銆侾ython 鈮?3.9 鍗冲彲銆?
2. **閰嶇疆**锛氭紨绀烘ā寮忛浂閰嶇疆銆傛帴鐪熷疄鏀粯/鐢熶骇鎵嶉渶鍓埗閰嶇疆锛歚cp .env.example .env` 骞跺～ `JZ_BILLING_GATEWAY` + 瀵瑰簲鍑瘉锛坅fdian / aishouqian / wepay锛夈€?
3. **鍚姩**锛歚python -m jianzhu_saas.cli` 鍚庢祻瑙堝櫒鎵撳紑 `http://127.0.0.1:8080/` 鈫?鐐广€岀櫥褰曟紨绀虹鎴枫€嶁啋 杈撳叆涓夐」鎸囨爣 鈫?璇勪及椋庨櫓锛堢鍑?CRITICAL 鎶ュ憡 + Credit 鎵ｅ噺锛夈€?

curl 涓€琛屼綋楠岋紙鍙﹀紑缁堢锛夛細

```bash
python -m jianzhu_saas.cli --print-token   # 鎵撳嵃鐜版垚鍙矘璐寸殑 curl
```

| 鍙傛暟 | 璇存槑 |
|---|---|
| `--port 8000` | 鎹㈢鍙?|
| `--db :memory:` | 鍐呭瓨搴撲复鏃舵紨绀猴紙涓嶈惤鐩橈紝澶氱嚎绋嬪叡浜悓涓€瀹炰緥锛?|
| `--gateway afdian` | 鍒囨崲鏀舵缃戝叧锛坣oop / aishouqian / wepay / afdian锛?|

### 灏忕▼搴忔笭閬撹鏄?

褰撳墠浜х墿涓?**Web 鐗堝嵆鐢ㄦ紨绀?*锛堟湰浠撳簱鏃犲井淇″皬绋嬪簭宸ョ▼锛夛細
- 婕旂ず/楠岃瘉锛氭湰鍦?CLI 鍚姩鍚庢祻瑙堝櫒鎵撳紑锛屾垨閮ㄧ讲鍒板缃戝煙鍚嶅悗娴忚鍣ㄦ墦寮€锛?
- 鍙樼幇锛氱埍鍙戠數锛坅fdian 缃戝叧宸叉帴鍏ワ級鍙祵鍏ュ井淇″叕浼楀彿/灏忕▼搴忔敹娆鹃摼璺紱灏忕▼搴忎綋楠屽眰寰?P1 鎵╁睍锛堝皝瑁搁」鐩?API锛夛紝褰撳墠涓嶉樆濉炰氦浠欍€?


## 鍔熻兘锛堝彧鍒楃湡瀹炲叿澶囩殑锛?
- 寤虹瓚缁撴瀯椋庨櫓璇勪及锛歚POST /api/assessments`
- 妫€娴嬭褰曞彴璐︼細`POST /api/inspections`
- 澶氱鎴烽殧绂伙細鏁版嵁鎸?`tenant_id` 闅旂锛屽彲绉佹湁閮ㄧ讲
- 璁¤垂 Credit 璁￠噺锛氭瘡娆¤瘎浼版墸 1 Credit锛屽椁愰厤棰濓紙free/pro/enterprise锛?
- 鏀舵棰勭暀鎺ュ彛锛歚create_order / query_callback / refund`锛堟湭鎺ュ叿浣撴敮浠樼綉鍏筹紝MVP 榛樿 NoopGateway锛?

## 杩愯

涓€閿惎鍔紙鎺ㄨ崘锛夛細

```
python -m jianzhu_saas.cli                # 榛樿 :8080
python -m jianzhu_saas.cli --port 9000    # 鎹㈢鍙?
python -m jianzhu_saas.cli --db :memory:   # 涓存椂鍐呭瓨搴?
```

鐩存帴璺戞湇鍔″叆鍙ｏ紙绛変环锛屾棤 CLI 鍖呰锛夛細

```
python api_server.py          # 榛樿 :8080
JZ_SAAS_PORT=9000 python api_server.py
```

## 閴存潈
```
# 婕旂ず鐜绛惧彂 token锛堢敓浜ф浛鎹负姝ｅ紡绉熸埛绛惧彂锛?
curl -X POST :8080/auth/demo-token -d '{"plan":"free"}' -H 'Content-Type: application/json'
# 甯?token 璋冪敤璇勪及
curl -X POST :8080/api/assessments -H "Authorization: Bearer <token>" \
     -d '{"metrics":{"concrete_strength_mpa":12,"rebar_cover_mm":14,"crack_width_mm":0.6}}'
```

## 鍏嶈矗澹版槑锛堜骇鍝佸眰锛?
鏈郴缁熻緭鍑?*浠呬负绠楁硶鍙傝€?*銆備换浣曠粨鏋勫畨鍏ㄥ垽瀹氥€佸姞鍥烘垨鍋滅敤鍐崇瓥锛屽繀椤荤敱**鎸佽瘉缁撴瀯宸ョ▼甯?*绛惧瓧璐熻矗銆?

## 鍥藉唴鏀舵锛堥鐣欙紝涓嶅～瀵嗛挜鍗冲彲璺戦€氾級
- 鍐呯疆涓変釜缃戝叧锛歚noop`锛堥粯璁ゅ崰浣嶏級/ `wepay`锛堝井淇″晢鎴凤級/ `aishouqian`锛堢埍鏀堕挶鑱氬悎锛夈€?
- 鐢ㄧ幆澧冨彉閲?`JZ_SAAS_BILLING_GATEWAY` 鍒囨崲锛涚己鐪?`noop`銆?
- 閰嶉綈瀵嗛挜鍚庤嚜鍔ㄨ蛋鐪熷疄涓嬪崟锛歚JZ_WXPAY_MCHID / JZ_WXPAY_APPID / JZ_WXPAY_API_KEY`锛屾垨 `JZ_AISHOUQIAN_MCH_NO / JZ_AISHOUQIAN_TOKEN / JZ_AISHOUQIAN_APPID`銆?
- 鏈厤瀵嗛挜鏃剁綉鍏宠繑鍥?`created_pending_key` 骞跺垪鍑?`needs_secret`锛屽墠绔嵁姝ゆ彁绀?寰呭紑閫氭敮浠?銆?

## 娴嬭瘯
```
python3 -m unittest tests.test_api tests.test_billing -v
```

---

## ⚖️ 商用与合规

### 开源范围
- 代码（SaaS 后端、计费网关、AI 接口）以 MIT License 开放，可自由使用、修改与商用。
- 以下部分不属于开源范围：Pro/企业档位的托管 SaaS 服务（评估次数配额、PDF 报告导出、私有部署、SLA）。

### 付费功能边界
- 免费（¥0）：100 次评估/月，基础 API 调用
- Pro（¥99/月）：无限评估 + PDF 报告导出 + 优先技术支持
- 企业（¥999/月）：私有部署 + 定制算法 + 多 Agent 协作 + SLA

### 数据与隔离
- 用户数据**不用于模型训练**，SaaS 层数据隔离（按租户隔离）
- 企业版支持私有部署，数据不出境、不上云
- 计费网关（wepay / aishouqian / afdian）仅处理支付，不回传业务数据

### 内容版权
- AIGC 生成的算量/审图结果：版权归使用者，但需遵守建筑行业标准与执业规范
- 开源代码：MIT 适用范围为全部 Python 代码、前端页面、测试

### 合规免责
- 本工具输出**仅供参考**，不替代专业结构工程师审查与施工图设计
- 使用本工具产生的结构安全、工程合规责任由使用者自行承担
- 涉及实际工程决策须由持证工程师复核，遵守《建设工程质量管理条例》及地方规范

---

## 定位与定价（2026-10-22 锁定）

jianzhu-saas 是给中小施工队的"轻建筑 SaaS"——小程序 30 秒上手，对标品茗/广联达 1/5 价格，不拼 BIM 重度建模，拼"轻量、便宜、马上能用"。

**定价档位**（对标品茗 ARPU 走低价长尾）：
- 个人版 ¥39/月 · 团队版 ¥99/月 · 企业版 ¥299/月（企业定制 ¥0.8-3 万/年）
- 免费入口引流 → 付费订阅；年付 8 折
- 已内置 wepay / aishouqian / afdian 四网关付费，AI 算量/审图接口预留

> English: jianzhu-saas is a lightweight construction SaaS for small-to-mid contractors. Open in a WeChat mini-program in 30s, priced at 1/5 of Pinming/Glodon. Free tier to funnel → subscription.



---

## 💛 支持 & 发布（爱发电双通道）

本仓通过**爱发电**完成「**创作者赞赏/订阅收款**」与「**作品/内容社区发布**」双通道运营，二者共存：

| 通道 | 用途 | 入口 |
|------|------|------|
| 💰 爱发电收款 | 赞赏、订阅、Pro 会员、赞助维护 | [爱发电 @Zeon7744](https://afdian.net/@Zeon7744) |
| 📣 爱发电社区发布 | 作品展示、内容连载、粉丝互动、发布分发 | [爱发电社区 @Zeon7744](https://afdian.com/user/0c59dda8a1bb11f19b9552540025c377) |

- **收款**：赞赏 / 订阅 Pro / 企业赞助，支付宝 + 微信支付，无需备案域名
- **社区发布**：把本仓产出（作品 / 剧本 / 工具演示 / 案例）在爱发电社区连载发布，沉淀粉丝、引流回仓
- 两通道独立共存，按需选用；收款不强制绑定社区发布

> 本仓内容仅供创作参考，发布前请完成人工合规审查与平台备案。

---

## 🎯 定价理念：先体验，后付费

**以人为本，让使用者深度体验价值后再做决定：**

- **免费额度拉满**：所有仓库的免费版本提供足够深度的体验额度，不人为设限——把核心能力先跑起来，让你真正用到
- **深度体验再付费**：付费版解锁的是更高频次、更完整功能、更高级资源（模板/工具/分成），不是限制基础体验
- **你的反馈驱动迭代**：每一条回馈都是产品优化的第一手依据，我们据此持续完善

## 💬 用户回馈（驱动迭代）

**使用中发现任何问题、想法、建议 → 直接回馈，驱动下一版：**

| 方式 | 入口 | 说明 |
|------|------|------|
| 社区评论 | [爱发电社区 @Zeon7744](https://afdian.com/user/0c59dda8a1bb11f19b9552540025c377) | 作品下评论/留言，直接驱动迭代 |
| Issue | 本仓 GitHub / Gitee / GitCode 的 Issues | Bug / 功能建议 / 定价反馈 |
| 赞赏反馈 | 爱发电赞赏留言 | 支持的同时留下使用心得 |

> 每一条回馈都是产品优化的第一手依据。不强制，但真诚欢迎。
