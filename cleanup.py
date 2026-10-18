import os, sys
sys.stdout.reconfigure(encoding='utf-8')

# 完善（红剑 P0）：原硬编码 D:\ 绝对路径跨机不可移植，改为基于 __file__ 解析仓根
base = os.path.dirname(os.path.abspath(__file__))
temp_files = [
    "src\\backend\\fix.py",
    "src\\backend\\fix2.py",
    "src\\backend\\fix3.py",
    "src\\backend\\debug_fix.py",
    "src\\backend\\dump_line.py",
    "src\\backend\\fix_get.py",
    "src\\backend\\fix_get2.py",
    "src\\backend\\check_routes.py",
    "src\\backend\\update_backend.py",
    "src\\backend\\expand_data.py",
    "src\\frontend\\update_dashboard.py",
    "src\\frontend\\update_finance.py",
    "src\\frontend\\update_agents.py",
    "src\\frontend\\update_compliance.py",
    "src\\frontend\\check_apis.py",
    "src\\frontend\\check_app.py",
    "analyze.py",
]

for f in temp_files:
    fp = os.path.join(base, f)
    if os.path.exists(fp):
        os.remove(fp)
        print(f"  Removed: {f}")

print("Cleanup complete!")
