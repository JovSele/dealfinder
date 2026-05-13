from storage import db
db.init()
n = db.backfill_neighbourhood()
print(f'Backfill hotový: {n} záznamov')
