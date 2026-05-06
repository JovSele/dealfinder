import psycopg2
import os

con = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = con.cursor()
cur.execute("""
    SELECT COUNT(*) FROM listings 
    WHERE source = 'sreality/byty' AND new_building = TRUE
""")
print('new_building True:', cur.fetchone()[0])

cur.execute("""
    SELECT COUNT(*) FROM listings 
    WHERE source = 'sreality/byty' AND new_building = FALSE
""")
print('new_building False:', cur.fetchone()[0])

cur.execute("""
    SELECT COUNT(*) FROM listings 
    WHERE source = 'sreality/byty' AND new_building IS NULL
""")
print('new_building NULL:', cur.fetchone()[0])
con.close()