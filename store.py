"""
多租户数据存储层（最小实现）。

- 用 SQLite 文件型存储替代内存 dict，重启不丢数据
- 所有表带 tenant_id，强制租户隔离
- 计量事件 usage_events 用于计费 Credit 扣减
"""
import os
import time
import uuid
import sqlite3
import threading

DB_PATH = os.environ.get("JZ_SAAS_DB", "data/jianzhu_saas.db")
_local = threading.local()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   TEXT PRIMARY KEY,
    name        TEXT,
    plan        TEXT NOT NULL DEFAULT 'free',   -- free / pro / enterprise
    credits     INTEGER NOT NULL DEFAULT 100,
    app_secret  TEXT,
    created     REAL
);
CREATE TABLE IF NOT EXISTS inspections (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    data        TEXT,
    created     REAL
);
CREATE TABLE IF NOT EXISTS assessments (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    risk_score  REAL,
    risk_level  TEXT,
    recommend   TEXT,
    data        TEXT,
    created     REAL
);
CREATE TABLE IF NOT EXISTS usage_events (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    action      TEXT NOT NULL,
    ts          REAL,
    credit_cost INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS tenant_rights (
    tenant_id   TEXT PRIMARY KEY,
    plan        TEXT NOT NULL DEFAULT 'free',
    monthly_quota INTEGER NOT NULL DEFAULT 0,
    report_level TEXT NOT NULL DEFAULT 'basic',
    seats       INTEGER NOT NULL DEFAULT 1,
    updated     REAL
);
"""

# Pro 权益映射表（产品层定字段，编程专家落库）
# 1000 次/月 + 完整报告 + 3 人协作
PRO_RIGHTS = {
    "free":       {"monthly_quota": 100,   "report_level": "basic",  "seats": 1},
    "pro":        {"monthly_quota": 1000,  "report_level": "full",   "seats": 3},
    "enterprise": {"monthly_quota": 10**9, "report_level": "full",   "seats": 10},
}


def conn():
    if not hasattr(_local, "c"):
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _local.c = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.c.row_factory = sqlite3.Row
        _local.c.executescript(_SCHEMA)
        _local.c.commit()
    return _local.c


def new_id():
    return str(uuid.uuid4())[:8]


class TenantService:
    """租户 + 套餐 + Credit 配额管理。"""

    # 套餐 Credit 上限：free 每月 100，pro 每月 10000，enterprise 不限
    PLAN_CREDIT = {"free": 100, "pro": 10000, "enterprise": 10 ** 9}

    def ensure_tenant(self, tenant_id, name="default", plan="free", app_secret=None):
        c = conn()
        c.execute(
            "INSERT OR IGNORE INTO tenants (tenant_id,name,plan,credits,app_secret,created) VALUES (?,?,?,?,?,?)",
            (tenant_id, name, plan, self.PLAN_CREDIT.get(plan, 100), app_secret, time.time()),
        )
        c.commit()
        self.apply_plan_rights(tenant_id, plan)
        return self.get(tenant_id)

    def get(self, tenant_id):
        c = conn()
        row = c.execute("SELECT * FROM tenants WHERE tenant_id=?", (tenant_id,)).fetchone()
        return dict(row) if row else None

    def has_credit(self, tenant_id, cost=1):
        t = self.get(tenant_id)
        if not t:
            return False, None
        if t["plan"] == "enterprise":
            return True, t
        return t["credits"] >= cost, t

    def deduct_credit(self, tenant_id, cost):
        """原子扣减（防并发超扣）。
        修复：旧逻辑是先 has_credit 查后扣（TOCTOU），并发评估同一租户时可超扣。
        现用 `UPDATE ... WHERE credits >= cost` 原子扣减，按 rowcount 判断是否成功。
        enterprise 租户无 credit 限制，直接放行。返回 (allowed, remaining)。"""
        t = self.get(tenant_id)
        if not t:
            return False, None
        if t["plan"] == "enterprise":
            return True, None
        c = conn()
        cur = c.execute(
            "UPDATE tenants SET credits = credits - ? "
            "WHERE tenant_id = ? AND credits >= ?",
            (int(cost), tenant_id, int(cost)),
        )
        c.commit()
        if cur.rowcount == 0:
            return False, self.get(tenant_id)["credits"]
        return True, self.get(tenant_id)["credits"]



    def list_tenants(self, limit=100):
        """列出所有租户（管理后台 / 运营用）。"""
        c = conn()
        rows = c.execute(
            "SELECT * FROM tenants ORDER BY created DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def apply_plan_rights(self, tenant_id, plan):
        """把 Pro 权益映射表落到 tenant_rights 表（幂等 upsert）。"""
        rights = PRO_RIGHTS.get(plan, PRO_RIGHTS["free"])
        c = conn()
        c.execute(
            "INSERT INTO tenant_rights (tenant_id, plan, monthly_quota, report_level, seats, updated) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(tenant_id) DO UPDATE SET "
            "plan=excluded.plan, monthly_quota=excluded.monthly_quota, "
            "report_level=excluded.report_level, seats=excluded.seats, updated=excluded.updated",
            (tenant_id, plan, rights["monthly_quota"], rights["report_level"], rights["seats"], time.time()),
        )
        c.commit()

    def get_rights(self, tenant_id):
        """查 tenant_rights 行；不存在则返回 None。"""
        c = conn()
        row = c.execute("SELECT * FROM tenant_rights WHERE tenant_id=?", (tenant_id,)).fetchone()
        return dict(row) if row else None

    def check_quota(self, tenant_id, monthly_used):
        """配额检查：(allowed, remaining, quota)。enterprise 不限。"""
        r = self.get_rights(tenant_id) or {"monthly_quota": 10**9}
        quota = r["monthly_quota"]
        remain = max(0, quota - int(monthly_used))
        return (remain > 0 or quota >= 10**9), remain, quota

    def can_use_report_level(self, tenant_id, level):
        """报告级别权限：full 需要 pro/enterprise。"""
        r = self.get_rights(tenant_id)
        if not r:
            return False
        return r["report_level"] == "full" or level == "basic"

    def set_plan(self, tenant_id, plan, credits=None):
        """升降级套餐。credits 显式传则覆盖，否则用新套餐默认额度。权益同步落库。"""
        if plan not in self.PLAN_CREDIT:
            return False
        new_credit = self.PLAN_CREDIT[plan] if credits is None else int(credits)
        c = conn()
        c.execute(
            "UPDATE tenants SET plan=?, credits=? WHERE tenant_id=?",
            (plan, new_credit, tenant_id),
        )
        c.commit()
        self.apply_plan_rights(tenant_id, plan)
        return self.get(tenant_id)

    def topup_credit(self, tenant_id, amount):
        """充值 credits（收款回调成功后调用）。返回最新剩余。"""
        if amount <= 0:
            return None
        c = conn()
        c.execute(
            "UPDATE tenants SET credits=credits+? WHERE tenant_id=?",
            (int(amount), tenant_id),
        )
        c.commit()
        return self.get(tenant_id)

tsvc = TenantService()


class Store:
    """按租户隔离的 inspections / assessments 存取。"""

    def __init__(self, risk_engine=None):
        self.risk = risk_engine or RiskEngine()

    def create_inspection(self, tenant_id, data):
        iid = new_id()
        c = conn()
        c.execute(
            "INSERT INTO inspections (id,tenant_id,status,data,created) VALUES (?,?,?,?,?)",
            (iid, tenant_id, "pending", self._json(data), time.time()),
        )
        c.commit()
        return {"id": iid, "tenant_id": tenant_id, "status": "pending", "data": data}

    def get_inspection(self, tenant_id, iid):
        c = conn()
        row = c.execute(
            "SELECT * FROM inspections WHERE id=? AND tenant_id=?", (iid, tenant_id)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["data"] = self._loads(d.get("data"))
        return d

    def list_assessments(self, tenant_id):
        c = conn()
        rows = c.execute(
            "SELECT * FROM assessments WHERE tenant_id=? ORDER BY created DESC", (tenant_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["data"] = self._loads(d.get("data"))
            d["recommendations"] = self._loads(d.get("recommend"))
            out.append(d)
        return out

    def create_assessment(self, tenant_id, data):
        aid = new_id()
        metrics = data.get("metrics", {}) if isinstance(data, dict) else {}
        # 完善：评估输出分项 breakdown（可解释），兼容 building_type 差异化权重
        risk_score, breakdown = self.risk.score_explained(metrics)
        risk_level = self.risk.level(risk_score)
        recs = self.risk.recommendations(risk_score)
        c = conn()
        c.execute(
            "INSERT INTO assessments (id,tenant_id,risk_score,risk_level,recommend,data,created) "
            "VALUES (?,?,?,?,?,?,?)",
            (aid, tenant_id, risk_score, risk_level, self._json(recs), self._json(data), time.time()),
        )
        c.commit()
        return {
            "id": aid,
            "tenant_id": tenant_id,
            "risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "recommendations": recs,
            "breakdown": breakdown,   # 完善：分项可解释输出
            "data": data,
            "disclaimer": RiskEngine.DISCLAIMER,
        }

    @staticmethod
    def _json(x):
        import json

        return json.dumps(x, ensure_ascii=False)

    @staticmethod
    def _loads(x):
        import json

        try:
            return json.loads(x)
        except Exception:
            return x


class UsageMeter:
    """计量 + Credit 扣减。计费 Credit 的最小实现。"""

    def record(self, tenant_id, action, cost=1):
        # 先原子扣减（防并发超扣），再记 usage 事件。
        ok, remaining = tsvc.deduct_credit(tenant_id, cost)
        if not ok:
            return {"allowed": False, "reason": "insufficient_credits_or_tenant"}
        c = conn()
        c.execute(
            "INSERT INTO usage_events (id,tenant_id,action,ts,credit_cost) VALUES (?,?,?,?,?)",
            (new_id(), tenant_id, action, time.time(), cost),
        )
        c.commit()
        return {"allowed": True, "remaining": remaining}


class RiskEngine:
    """结构风险评估引擎（SaaS 核心能力）。

    完善说明（原理层）：
    - 评估维度从 3 项扩展到 7 项建筑结构核心维度
    - 权重可配置（DEFAULT_WEIGHTS / 按建筑类型差异化 preset）
    - 输出分项 breakdown（可解释），前端与报告可展示每项扣分
    - 保留 DISCLAIMER 合规叠加（API/报告/产品三处）
    """
    DISCLAIMER = (
        "本系统输出仅为算法参考，最终判定必须由持证结构工程师负责。"
        " 任何施工/加固/停止使用决策请以持证工程师签字报告为准。"
    )

    # 评估维度定义：每个维度 (指标键, 默认值, 权重)
    DIMENSIONS = [
        ("concrete_strength_mpa", 25.0, 0.25),  # 混凝土强度
        ("rebar_cover_mm", 30.0, 0.20),          # 钢筋保护层
        ("crack_width_mm", 0.10, 0.20),          # 裂缝宽度
        ("rebar_corrosion_pct", 0.0, 0.15),      # 钢筋锈蚀率（完善新增）
        ("carbonation_depth_mm", 0.0, 0.10),     # 碳化深度（完善新增）
        ("settlement_mm", 0.0, 0.05),            # 沉降位移（完善新增）
        ("load_ratio", 0.5, 0.05),               # 荷载比（完善新增）
    ]

    # 默认权重（按维度索引归一化兜底）
    DEFAULT_WEIGHTS = {name: weight for name, _, weight in DIMENSIONS}

    # 建筑类型差异化 preset（SaaS 按客户类型输出不同权重）
    TYPE_PRESETS = {
        "residential": {   # 住宅：结构冗余高，权重下调
            "concrete_strength_mpa": 0.20,
            "rebar_corrosion_pct": 0.20,
            "crack_width_mm": 0.20,
        },
        "bridge": {        # 桥梁：荷载与沉降敏感
            "load_ratio": 0.25,
            "settlement_mm": 0.20,
            "concrete_strength_mpa": 0.20,
        },
        "industrial": {   # 工业：混凝土强度与锈蚀权重高
            "concrete_strength_mpa": 0.30,
            "rebar_corrosion_pct": 0.20,
            "carbonation_depth_mm": 0.15,
        },
    }

    def __init__(self, building_type=None, weights=None):
        """weights 显式传入则覆盖；否则按 building_type 选 preset 兜底默认。"""
        self.weights = dict(self.DEFAULT_WEIGHTS)
        if building_type:
            self.weights.update(self.TYPE_PRESETS.get(building_type, {}))
        if weights:
            self.weights.update(weights)

    def score(self, m, breakdown=True):
        """结构风险评估（0-100，分数越高越危险）。

        完善：返回 (score, breakdown) 或仅 score（兼容旧调用）。
        旧签名 score(m) 仍返回 float；若调用方需要 breakdown 用 score_explained(m)。
        """
        total, _ = self._evaluate(m)
        return total

    def score_explained(self, m):
        """返回 (总分, 分项 breakdown 列表)，SaaS 报告/前端可解释展示。"""
        return self._evaluate(m)

    def _evaluate(self, m):
        total = 0.0
        breakdown = []
        wsum = 0.0
        for name, default, base_weight in self.DIMENSIONS:
            # 完善：只评估数据中实际提供的指标，缺省维度不惩罚不拉分，
            # 保证旧 3 维度场景（未提供新维度）分数与扩展前语义一致。
            if name not in m:
                continue
            w = self.weights.get(name, base_weight)
            val = float(m.get(name, default))
            item_score = self._dimension_score(name, val)  # 0-100 单项风险
            weighted = item_score * w
            total += weighted
            wsum += w
            breakdown.append({
                "dimension": name,
                "value": val,
                "item_risk": round(item_score, 2),
                "weight": w,
                "contribution": round(weighted, 2),
            })
        # 归一化（权重和 ≠ 1 时缩放；item_risk 已 0-100，乘权重后量纲仍 0-100）
        if wsum > 0:
            total = total / wsum
        elif not breakdown:
            return 0.0, breakdown  # 无任何指标 → 0 风险（合规：无数据不出结论）
        return min(100.0, max(0.0, total)), breakdown

    def _dimension_score(self, name, v):
        """单项维度风险分（0-100），各维度独立阈值。"""
        if name == "concrete_strength_mpa":
            if v < 15: return 100
            if v < 20: return 80
            if v < 25: return 50
            return 10
        if name == "rebar_cover_mm":
            if v < 15: return 100
            if v < 20: return 60
            if v > 50: return 40
            return 10
        if name == "crack_width_mm":
            if v > 0.5: return 100
            if v > 0.3: return 70
            if v > 0.2: return 40
            return 10
        if name == "rebar_corrosion_pct":
            if v > 5: return 100
            if v > 2: return 70
            if v > 1: return 40
            return 10
        if name == "carbonation_depth_mm":
            if v > 20: return 90
            if v > 10: return 50
            return 10
        if name == "settlement_mm":
            if v > 50: return 100
            if v > 30: return 60
            if v > 15: return 30
            return 5
        if name == "load_ratio":
            if v > 0.9: return 100
            if v > 0.7: return 60
            return 10
        return 0

    def level(self, s):
        if s >= 70:
            return "CRITICAL"
        if s >= 50:
            return "HIGH"
        if s >= 30:
            return "MEDIUM"
        if s >= 15:
            return "LOW"
        return "MINIMAL"

    def recommendations(self, s):
        if s >= 70:
            return ["立即进行结构加固", "48 小时内由持证结构工程师介入"]
        if s >= 50:
            return ["2 周内安排详细结构评估", "复核裂缝扩展形态"]
        if s >= 30:
            return ["每月监测裂缝宽度", "核查钢筋锈蚀程度"]
        return ["常规 12 个月巡检"]


store = Store()
usage = UsageMeter()
