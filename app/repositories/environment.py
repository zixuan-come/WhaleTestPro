from sqlalchemy.orm import Session
from app.models.environment import Environment


def db_create(db: Session, env, project_id: int):
    db_env = Environment(**env.model_dump(), project_id=project_id)
    db.add(db_env)
    db.commit()
    db.refresh(db_env)
    return db_env


def db_get(db: Session, env_id: int, project_id: int):
    return db.query(Environment).filter(
        Environment.id == env_id,
        Environment.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int):
    return db.query(Environment).filter(Environment.project_id == project_id).all()


def db_update(db: Session, env_id: int, env, project_id: int):
    db_env = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.project_id == project_id,
    ).first()
    if db_env is None:
        return None
    # env.model_dump() 只 dump EnvironmentCreate 声明的字段,不含 project_id → 不会误改归属
    for key, value in env.model_dump().items():
        setattr(db_env, key, value)
    db.commit()
    db.refresh(db_env)
    return db_env


def db_delete(db: Session, env_id: int, project_id: int):
    db_env = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.project_id == project_id,
    ).first()
    if db_env is None:
        return None
    db.delete(db_env)
    db.commit()
    return db_env
