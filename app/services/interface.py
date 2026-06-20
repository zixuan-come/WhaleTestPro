from app.repositories import interface as api_repo



def s_create(db, interface):
    return api_repo.db_create(db, interface)


def s_get(db, interface_id):
    return api_repo.db_get(db, interface_id)


def s_list(db):
    return api_repo.db_list(db)


def s_delete(db, interface_id):
    return api_repo.db_delete(db, interface_id)




