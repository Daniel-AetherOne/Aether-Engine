import sqlite3

con = sqlite3.connect("audit.db")
con.execute(
    "DELETE FROM audit_events "
    "WHERE event_id=(SELECT event_id FROM audit_events LIMIT 1)"
)
con.commit()
print("DELETE succeeded (THIS SHOULD NOT HAPPEN)")
