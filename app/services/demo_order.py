from app.repositories import demo_order as order_repo


def s_create(db, order):
    return order_repo.db_create(db, order)


def s_list(db):
    return order_repo.db_list(db)












