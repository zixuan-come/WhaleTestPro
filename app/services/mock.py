from app.repositories import mock as mock_repo


def s_create(db, mock):
    return mock_repo.db_create(db, mock)


def s_get(db, mock_id):
    return mock_repo.db_get(db, mock_id)


def s_list(db):
    return mock_repo.db_list(db)


def s_update(db, mock_id, mock):
    return mock_repo.db_update(db, mock_id, mock)


def s_delete(db, mock_id):
    return mock_repo.db_delete(db, mock_id)


def s_match(db, path, method):
    return mock_repo.db_match(db, path, method)



