from app.repositories import case as case_repo


def s_create(db, case):
    return case_repo.db_create(db, case)


def s_get(db, case_id):
    return case_repo.db_get(db, case_id)


def s_list(db):
    return case_repo.db_list(db)


def s_delete(db, case_id):
    return case_repo.db_delete(db, case_id)




