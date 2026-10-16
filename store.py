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
"""


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
        risk_score = self.risk.score(metrics)
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
            "risk_score": risk_score,
            "risk_level": risk_level,
            "recommendations": recs,
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
        ok, tenant = tsvc.has_credit(tenant_id, cost)
        if not ok:
            return {"allowed": False, "reason": "insufficient_credits_or_tenant"}
        c = conn()
        c.execute(
            "INSERT INTO usage_events (id,tenant_id,action,ts,credit_cost) VALUES (?,?,?,?,?)",
            (new_id(), tenant_id, action, time.time(), cost),
        )
        if tenant["plan"] != "enterprise":
            c.execute(
                "UPDATE tenants SET credits=credits-? WHERE tenant_id=?", (cost, tenant_id)
            )
        c.commit()
        return {"allowed": True, "remaining": tsvc.get(tenant_id)["credits"]}


class RiskEngine:
    DISCLAIMER = (
        "本系统输出仅为算法参考，最终判定必须由持证结构工程师负责。"
        " 任何施工/加固/停止使用决策请以持证工程师签字报告为准。"
    )

    def score(self, m):
        """结构风险评估（0-100，分数越高越危险）。"""
        score = 0.0
        cs = float(m.get("concrete_strength_mpa", 25))
        if cs < 15:
            score += 40
        elif cs < 20:
            score += 25
        elif cs < 25:
            score += 10
        rc = float(m.get("rebar_cover_mm", 30))
        if rc < 15:
            score += 30
        elif rc < 20:
            score += 15
        elif rc > 50:
            score += 10
        cw = float(m.get("crack_width_mm", 0.1))
        if cw > 0.5:
            score += 30
        elif cw > 0.3:
            score += 20
        elif cw > 0.2:
            score += 10
        return min(100.0, score)

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
