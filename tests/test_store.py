

def test_pro_rights_mapping_persisted():
    """Pro 权益映射表落库：set_plan('pro') 后 tenant_rights 有 1000 次/月 + full 报告 + 3 席位。"""
    import store
    from store import tsvc, PRO_RIGHTS
    tid = store.new_id()
    tsvc.ensure_tenant(tid, plan="free")
    assert tsvc.get_rights(tid)["monthly_quota"] == PRO_RIGHTS["free"]["monthly_quota"]
    tsvc.set_plan(tid, "pro")
    r = tsvc.get_rights(tid)
    assert r["monthly_quota"] == 1000 and r["report_level"] == "full" and r["seats"] == 3, r
    # 配额 + 报告级判断
    ok, remain, quota = tsvc.check_quota(tid, monthly_used=999)
    assert ok and remain == 1 and quota == 1000
    assert tsvc.can_use_report_level(tid, "full") is True
    tsvc.set_plan(tid, "free")
    r2 = tsvc.get_rights(tid)
    assert r2["monthly_quota"] == 100 and r2["report_level"] == "basic" and r2["seats"] == 1


def test_afdian_gateway_pending_key():
    """爱发电网关：token 未配时返回 created_pending_key 且标注需要注入的 secret。"""
    import os
    os.environ.pop("JZ_SAAS_AFDIAN_TOKEN", None)
    os.environ.pop("JZ_SAAS_AFDIAN_USER", None)
    from billing import AfdianGateway
    g = AfdianGateway()
    o = g.create_order("t1", 9900, "jianzhu-saas-sub", "pro")
    assert o["status"] == "created_pending_key", o
    assert o["gateway"] == "afdian"
    assert any("AFDIAN_TOKEN" in s for s in o["needs_secret"]), o["needs_secret"]
