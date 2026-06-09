"""Fix 4 stuck in_progress nodes:
- is_matched and display_name: todo! markers added to skeleton, reset to not_started
- check_auth and logout_view: already implemented in auth/mod.rs, mark converted
"""
import sqlite3

db_path = "/Users/ceres/Desktop/SignalCanvas/oxidant/flora_api_manifest.db"

conn = sqlite3.connect(db_path, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")

conn.execute("""
    UPDATE nodes SET status='not_started', attempt_count=0, last_error=NULL
    WHERE node_id IN (
        'models__commerce__NurseryPricing__is_matched',
        'models__plant__Plant__display_name'
    )
""")

conn.execute("""
    UPDATE nodes
    SET status='converted',
        summary_text='Already implemented in auth/mod.rs (as check() and logout() respectively)'
    WHERE node_id IN (
        'views__auth__check_auth',
        'views__auth__logout_view'
    )
""")

conn.commit()

rows = conn.execute("""
    SELECT node_id, status FROM nodes
    WHERE node_id IN (
        'models__commerce__NurseryPricing__is_matched',
        'models__plant__Plant__display_name',
        'views__auth__check_auth',
        'views__auth__logout_view'
    )
""").fetchall()

for node_id, status in rows:
    print(f"{status:12} {node_id}")

conn.close()
