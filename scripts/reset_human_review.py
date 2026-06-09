"""Reset all human_review nodes to not_started for a fresh Phase B pass."""
import sqlite3

db_path = "/Users/ceres/Desktop/SignalCanvas/oxidant/flora_api_manifest.db"

conn = sqlite3.connect(db_path, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")

conn.execute("""
    UPDATE nodes
    SET status='not_started', attempt_count=0, last_error=NULL
    WHERE status='human_review'
""")
conn.commit()

rows = conn.execute("""
    SELECT node_id, status FROM nodes
    WHERE status='not_started'
    ORDER BY node_id
""").fetchall()

print(f"Reset {len(rows)} node(s) to not_started:")
for node_id, status in rows:
    print(f"  {node_id}")

conn.close()
