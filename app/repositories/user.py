from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate
from app.core.security import hash_password


def db_create(db: Session, user: UserCreate) -> User:
    hashed = hash_password(user.password)
    db_user = User(username=user.username, hashed_password=hashed)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def db_get_by_username(db: Session, username: str) -> User | None:
    # 大小写不敏感查找（BUG-021）：
    # schema 层已把新账号规范为小写，但历史数据可能存在大写用户名。
    # 用 lower(...) 比较可让大写老用户用小写登录，也能在注册时挡住
    # 仅大小写不同的重复账号（Alice / alice）。
    return (
        db.query(User)
        .filter(func.lower(User.username) == username.strip().lower())
        .first()
    )


def db_get_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()



