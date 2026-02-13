import sqlite3

DB_PATH = "dev.db"

stmts = [
    "ALTER TABLE leads ADD COLUMN public_token VARCHAR(64);",
    "ALTER TABLE leads ADD COLUMN sent_at DATETIME;",
    "ALTER TABLE leads ADD COLUMN viewed_at DATETIME;",
    "ALTER TABLE leads ADD COLUMN accepted_at DATETIME;",
    # index op public_token (sqlite kan index apart)
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_leads_public_token ON leads (public_token);",
]

con = sqlite3.connect(DB_PATH)
cur = con.cursor()
for s in stmts:
    try:
        cur.execute(s)
        print("OK:", s)
    except Exception as e:
        print("SKIP/ERR:", s, e)
con.commit()
con.close()
print("done")
