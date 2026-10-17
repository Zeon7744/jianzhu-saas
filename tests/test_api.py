"""jianzhu-saas 评估 API 冒烟测试（标准库，无需第三方）。"""
import os
import sys
import json
import threading
import time
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试用独立临时 SQLite，避免与仓库 data/ 冲突
_TMPDB = os.path.join(tempfile.mkdtemp(), "test_jianzhu.db")
os.environ["JZ_SAAS_DB"] = _TMPDB

import store
import auth


class TestRiskEngine(unittest.TestCase):
    def test_critical(self):
        e = store.RiskEngine()
        m = {"concrete_strength_mpa": 12, "rebar_cover_mm": 14, "crack_width_mm": 0.6}
        self.assertEqual(e.level(e.score(m)), "CRITICAL")

    def test_minimal(self):
        e = store.RiskEngine()
        m = {"concrete_strength_mpa": 30, "rebar_cover_mm": 30, "crack_width_mm": 0.1}
        self.assertEqual(e.level(e.score(m)), "MINIMAL")


class TestTenantAndQuota(unittest.TestCase):
    def setUp(self):
        self.store = store.Store()

    def test_tenant_isolation(self):
        a = self.store.create_assessment("tA", {"metrics": {"concrete_strength_mpa": 10}})
        b = self.store.create_assessment("tB", {"metrics": {"concrete_strength_mpa": 10}})
        self.assertEqual(a["tenant_id"], "tA")
        self.assertEqual(b["tenant_id"], "tB")
        # tA 列表里不应有 tB 的记录
        tA = self.store.list_assessments("tA")
        self.assertTrue(all(x["tenant_id"] == "tA" for x in tA))

    def test_credit_deduct(self):
        t = store.tsvc.ensure_tenant("tQ", plan="free")
        r = store.usage.record("tQ", "assessment", 1)
        self.assertTrue(r["allowed"])
        self.assertEqual(r["remaining"], t["credits"] - 1)

    def test_cross_tenant_no_leak(self):
        """P1 信任地基：跨租户数据不可见、计量互不影响。"""
        s = store.Store()
        s.create_assessment("isol_A", {"metrics": {"concrete_strength_mpa": 10}})
        s.create_assessment("isol_B", {"metrics": {"concrete_strength_mpa": 10}})
        # A 列表里只可能看到 A 的记录（租户过滤）
        a_list = s.list_assessments("isol_A")
        self.assertTrue(all(x["tenant_id"] == "isol_A" for x in a_list))
        # B 列表里不应含 A 的记录
        b_list = s.list_assessments("isol_B")
        self.assertTrue(all(x["tenant_id"] == "isol_B" for x in b_list))
        # 计量：A 消耗不扣 B 的 credits
        store.tsvc.ensure_tenant("isol_A", plan="free")
        store.tsvc.ensure_tenant("isol_B", plan="free")
        rA = store.usage.record("isol_A", "assessment", 1)
        self.assertTrue(rA["allowed"])
        b_t = store.tsvc.get("isol_B")
        self.assertEqual(b_t["credits"], store.TenantService.PLAN_CREDIT.get("free", 100))


class TestAuth(unittest.TestCase):
    def test_roundtrip(self):
        tok = auth.issue_token("t1", "admin", "pro")
        claims, err = auth.verify_token(tok)
        self.assertIsNone(err)
        self.assertEqual(claims["tenant_id"], "t1")

    def test_bad_sig(self):
        self.assertIsNotNone(auth.verify_token("a.b.c")[1])


if __name__ == "__main__":
    unittest.main()


class TestHttpSmoke(unittest.TestCase):
    """HTTP 层冒烟：起 ThreadingHTTPServer + urllib 打 4 端点（第二批 patch #7）。"""

    @classmethod
    def setUpClass(cls):
        import socket
        from api_server import Handler
        # 随机空闲端口
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        # 直接用标准库 ThreadingHTTPServer
        from http.server import ThreadingHTTPServer as _T
        cls._srv = _T(("127.0.0.1", cls.port), Handler)
        cls._th = threading.Thread(target=cls._srv.serve_forever, daemon=True)
        cls._th.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls._srv.shutdown()
        cls._srv.server_close()

    def _get(self, path, token=None):
        import urllib.request
        req = urllib.request.Request(self.base + path)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def _post(self, path, body, token=None):
        import urllib.request
        data = json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def test_health_noauth(self):
        code, body = self._get("/health")
        self.assertEqual(code, 200)
        self.assertEqual(body["status"], "ok")

    def test_assess_noauth_401(self):
        code, _ = self._post("/api/assessments", {"metrics": {"concrete_strength_mpa": 10}})
        self.assertEqual(code, 401)

    def test_assess_with_demo_token(self):
        code, tok = self._post("/auth/demo-token", {"plan": "free"})
        self.assertEqual(code, 200)
        token = tok["token"]
        code, body = self._post(
            "/api/assessments",
            {"metrics": {"concrete_strength_mpa": 10, "rebar_cover_mm": 14, "crack_width_mm": 0.6}},
            token,
        )
        self.assertEqual(code, 201)
        self.assertIn("risk_level", body)
        self.assertIn("disclaimer", body)

    def test_billing_credit_with_token(self):
        code, tok = self._post("/auth/demo-token", {"plan": "free"})
        code, body = self._get("/billing/credit", tok["token"])
        self.assertEqual(code, 200)
        self.assertIn("credits", body)


class TestRiskEngineExtended(unittest.TestCase):
    """第二批原理层完善：RiskEngine 7 维度 + 权重可配 + breakdown 可解释。"""

    def test_score_explained_returns_7_dims(self):
        from store import RiskEngine
        eng = RiskEngine()
        m = {"concrete_strength_mpa": 12, "rebar_cover_mm": 14, "crack_width_mm": 0.6,
             "rebar_corrosion_pct": 3, "carbonation_depth_mm": 15, "settlement_mm": 40, "load_ratio": 0.8}
        score, breakdown = eng.score_explained(m)
        self.assertEqual(len(breakdown), 7)
        self.assertGreater(score, 50)  # 多维恶化 → 高风险
        for b in breakdown:
            self.assertIn(b["dimension"], [d[0] for d in eng.DIMENSIONS])
            self.assertGreaterEqual(b["item_risk"], 0)
            self.assertGreaterEqual(b["contribution"], 0)

    def test_building_type_preset_changes_weights(self):
        from store import RiskEngine
        bridge = RiskEngine(building_type="bridge")
        self.assertEqual(bridge.weights["load_ratio"], 0.25)
        res = RiskEngine(building_type="residential")
        self.assertEqual(res.weights["rebar_corrosion_pct"], 0.20)

    def test_backward_compat_score_returns_float(self):
        from store import RiskEngine
        eng = RiskEngine()
        s = eng.score({"concrete_strength_mpa": 10})
        self.assertIsInstance(s, float)

    def test_create_assessment_includes_breakdown(self):
        import store as S
        # 只评实际提供的维度（2 项），缺省维度不惩罚不拉分
        r = S.store.create_assessment("t1", {"metrics": {"concrete_strength_mpa": 10, "crack_width_mm": 0.6}})
        self.assertIn("breakdown", r)
        self.assertEqual(len(r["breakdown"]), 2)
        self.assertIn("disclaimer", r)
