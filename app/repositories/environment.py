from app.models.environment import Environment


def db_create(db, env):
    db_env = Environment(**env.model_dump())
    db.add(db_env)
    db.commit()
    db.refresh(db_env)
    return db_env


def db_get(db, env_id):
    return db.query(Environment).filter(Environment.id == env_id).first()


def db_list(db):
    return db.query(Environment).all()


def db_update(db, env_id, env):
    db_env = db.query(Environment).filter(Environment.id == env_id).first()
    if db_env is None:
        return None
    for key, value in env.model_dump().items():
        setattr(db_env, key, value)
    db.commit()
    db.refresh(db_env)
    return db_env


def db_delete(db, env_id):
    db_env = db.query(Environment).filter(Environment.id == env_id).first()
    if db_env is None:
        return None
    db.delete(db_env)
    db.commit()
    return db_env