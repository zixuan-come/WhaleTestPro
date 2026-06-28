from app.repositories import report as report_repo


def s_get(db, report_id):
    return report_repo.db_get(db, report_id)


def s_list(db):
    return report_repo.db_list(db)



