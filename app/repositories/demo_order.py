from app.models.demo_order import DemoOrder

def db_create(db, order):
    db_order = DemoOrder(**order.model_dump())
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order


def db_list(db):
    return db.query(DemoOrder).all()









