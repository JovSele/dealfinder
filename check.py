import psycopg2
import os

con = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = con.cursor()
cur.execute("""
    SELECT COUNT(*), MIN(sent_at), MAX(sent_at)
    FROM free_sent 
    WHERE sent_at::date = CURRENT_DATE
""")
print(cur.fetchone())

cur.execute("""
    SELECT sent_at FROM free_sent 
    WHERE sent_at::date = CURRENT_DATE
    LIMIT 5
""")
for r in cur.fetchall():
    print(r)
con.close()