from app.repositories import traffic_record as traffic_record_repo


def s_create(db, record):
    return traffic_record_repo.db_create(db, record)


def s_get(db, record_id):
    return traffic_record_repo.db_get(db, record_id)


def s_list(db, limit=100):
    return traffic_record_repo.db_list(db, limit)
