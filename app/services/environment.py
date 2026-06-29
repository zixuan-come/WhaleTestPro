from app.repositories import environment as env_repo


def s_create(db, env):
    return env_repo.db_create(db, env)


def s_get(db, env_id):
    return env_repo.db_get(db, env_id)


def s_list(db):
    return env_repo.db_list(db)


def s_update(db, env_id, env):
    return env_repo.db_update(db, env_id, env)


def s_delete(db, env_id):
    return env_repo.db_delete(db, env_id)
