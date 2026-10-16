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
