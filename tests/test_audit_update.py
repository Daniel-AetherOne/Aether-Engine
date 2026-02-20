import sqlite3

con = sqlite3.connect("audit.db")
con.execute(
    "UPDATE audit_events SET actor='hacker' "
    "WHERE event_id=(SELECT event_id FROM audit_events LIMIT 1)"
)
con.commit()
print("UPDATE succeeded (THIS SHOULD NOT HAPPEN)")
