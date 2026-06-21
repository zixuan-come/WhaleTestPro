from fastapi import HTTPException
from app.repositories import user as user_repo
from app.core.security import verify_password, create_access_token

def s_register(db, user):
    existing = user_repo.db_get_by_username(db, user.username)
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    return user_repo.db_create(db, user)


def s_login(db, user):
    existing = user_repo.db_get_by_username(db, user.username)
    if existing is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(user.password, existing.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(existing.id)
    return {"access_token": token}

