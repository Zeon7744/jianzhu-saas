# -*- coding: utf-8 -*-
"""可演示的端到端自动化闭环（红剑 P0：选一条链路做透）。

演示时真实库常为空、跑不出内容 → 收不到钱。本脚本把 jianzhu-agent 的核心
自动化闭环串成一条命令可跑通的 demo：

    1) 向 SQLite 播种一批演示数据（资质/制度/设备证书/项目，含故意到期/超期）
    2) 复用 src/backend/tasks.py 的完整检查链（4 类到期检查 + 优先级排序 + 摘要）
    3) 把告警落库（agent_logs）
    4) 打印一份可读的“自动巡检日报”

运行：
    python3 demo_pipeline.py
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import tempfile
import os

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src" / "backend"))

# demo 用独立的临时库，避免污染真实 jianjian.db
_TEMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TEMP.close()
DB_PATH = Path(_TEMP.name)

# 复用的表结构（与 app.py 一致，最小集）
_TABLES = [
    ("qualifications",
     "id TEXT PRIMARY KEY, name TEXT, type TEXT, cert_no TEXT, issuer TEXT, "
     "issue_date TEXT, expiry_date TEXT, status TEXT DEFAULT 'active', "
     "scope TEXT, renewal_note TEXT, created_at TEXT"),
    ("policies",
     "id TEXT PRIMARY KEY, title TEXT, version TEXT, department TEXT, "
     "status TEXT DEFAULT 'active', expiry_date TEXT, created_at TEXT"),
    ("equipment",
     "id TEXT PRIMARY KEY, name TEXT, model TEXT, status TEXT DEFAULT 'normal', "
     "location TEXT, cert_status TEXT, cert_due TEXT, last_maint TEXT, "
     "next_maint TEXT, value REAL DEFAULT 0, created_at TEXT"),
    ("projects",
     "id TEXT PRIMARY KEY, name TEXT, client TEXT, type TEXT, status TEXT "
     "DEFAULT 'active', budget REAL DEFAULT 0, start_date TEXT, end_date TEXT, "
     "created_at TEXT"),
    ("agent_logs",
     "id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, action TEXT, "
     "content TEXT, result TEXT, created_at TEXT"),
]

_DEMO_ROWS = {
    "qualifications": [
        ("Q001", "建筑业企业资质证书", "资质", "JZ-2026-001", "住建局",
         "2026-01-01", None, "active", "房建", "", "2026-01-01"),
        ("Q002", "安全生产许可证", "资质", "AQ-2026-014", "安监局",
         "2025-03-01", None, "active", "安全", "", "2025-03-01"),
    ],
    "policies": [
        ("P001", "质量管理制度", "v3", "质量部", "active", None, "2026-01-01"),
        ("P002", "安全生产操作规程", "v2", "安全部", "active", None, "2026-02-01"),
    ],
    "equipment": [
        ("E001", "全站仪", "TS06", "normal", "3 号仓", "valid",
         None, "2026-05-01", "2027-05-01", 50000.0, "2024-01-01"),
        ("E002", "经纬仪", "DT-400", "normal", "3 号仓", "warning",
         None, "2025-01-01", "2026-01-01", 30000.0, "2023-01-01"),
    ],
    "projects": [
        ("XM1", "市政道路检测", "市交通局", "桥梁检测", "active",
         120000, "2026-07-01", None, "2026-07-01"),
        ("XM2", "老旧小区改造", "住建局", "结构检测", "active",
         80000, "2026-06-01", None, "2026-06-01"),
    ],
}


def _d(offset_days: int) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


def _patch_expiry():
    """把演示数据的到期/截止日期设为可控相对日期（-30 已过期，+5 即将到期）。"""
    rows = _DEMO_ROWS
    rows["qualifications"][1] = (
        "Q002", "安全生产许可证", "资质", "AQ-2026-014", "安监局",
        "2025-03-01", _d(-30), "active", "安全", "已过期需立即续办", "2025-03-01",
    )
    rows["policies"][0] = ("P001", "质量管理制度", "v3", "质量部", "active", _d(5), "2026-01-01")
    rows["equipment"][1] = (
        "E002", "经纬仪", "DT-400", "normal", "3 号仓", "warning",
        _d(3), "2025-01-01", "2026-01-01", 30000.0, "2023-01-01",
    )
    rows["projects"][0] = (
        "XM1", "市政道路检测", "市交通局", "桥梁检测", "active",
        120000, "2026-07-01", _d(-10), "2026-07-01",
    )
    return rows


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    for name, schema in _TABLES:
        conn.execute(f"CREATE TABLE IF NOT EXISTS {name} ({schema})")
    conn.commit()


def _seed(conn: sqlite3.Connection, rows: dict) -> None:
    # 建立 表名 -> 建表 schema 的映射
    schema_of = dict(_TABLES)
    for table, data in rows.items():
        cols = schema_of[table]
        names = [c.split()[0] for c in cols.split(",")]
        qmarks = ",".join("?" for _ in names)
        for row in data:
            conn.execute(
                f"INSERT OR REPLACE INTO {table} ({','.join(names)}) VALUES ({qmarks})",
                row,
            )
    conn.commit()


def build_demo_report() -> dict:
    """核心演示闭环：播种 → 复用 tasks 检查链 → 返回可读日报。"""
    rows = _patch_expiry()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    _ensure_tables(conn)
    _seed(conn, rows)
    conn.close()

    import tasks as _tasks
    _tasks.DB_PATH = str(DB_PATH)
    report = _tasks.generate_daily_report()
    _tasks.save_alert_to_log(report["alerts"])
    return report


def _render(report: dict) -> str:
    lines = [
        "=" * 46,
        f"  jianzhu-agent 自动巡检日报  {report['date']}",
        "=" * 46,
        report["summary"],
        "",
        f"  告警统计：严重 {report['critical']} / 高危 {report['high']} / "
        f"中危 {report['medium']} / 低危 {report['low']}（共 {report['total_alerts']} 项）",
        "-" * 46,
    ]
    for a in report["alerts"]:
        lines.append(f"  [{a['priority']:>8}] {a['message']}")
    lines.append("=" * 46)
    lines.append("  （本日报由 jianzhu-agent 自动巡检闭环生成，可作为演示/交付物）")
    return "\n".join(lines)


def main() -> None:
    argparse.ArgumentParser(description="jianzhu-agent 可演示自动化巡检闭环").parse_args()
    report = build_demo_report()
    print(_render(report))
    print("\n✅ demo 闭环完成：播种 → 4 类到期检查 → 告警落库 → 日报输出")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


if __name__ == "__main__":
    main()
