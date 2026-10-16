import os, sys, tempfile, unittest
_TMPDB = os.path.join(tempfile.mkdtemp(), "test_b.db")
os.environ["JZ_SAAS_DB"] = _TMPDB
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import billing

class TestGateways(unittest.TestCase):
    def test_registry_has_3(self):
        for n in ["noop", "wepay", "aishouqian"]:
            self.assertIn(n, billing.BUILTIN_REGISTRY)

    def test_noop_ok(self):
        billing.get_gateway("noop")
        o = billing.create_order_for_tenant("t1", "pro", 9900)
        self.assertEqual(o["status"], "created")

    def test_wepay_pending_key_lists_secrets(self):
        o = billing.get_gateway("wepay").create_order("t1", 9900, "jianzhu-saas-sub", "pro")
        self.assertEqual(o["status"], "created_pending_key")
        self.assertIn("mchid", o["needs_secret"])

    def test_aishouqian_pending_key(self):
        o = billing.get_gateway("aishouqian").create_order("t1", 9900, "p", "pro")
        self.assertEqual(o["status"], "created_pending_key")
        self.assertIn("mch_no", o["needs_secret"])

    def test_unknown_falls_back_noop(self):
        self.assertEqual(billing.get_gateway("nope").name, "noop")

if __name__ == "__main__":
    unittest.main()
