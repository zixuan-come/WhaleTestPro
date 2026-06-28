from sqlalchemy import text

def run_sql(db, statements):
    for sql in statements or []:
        db.execute(text(sql))
    db.commit()





