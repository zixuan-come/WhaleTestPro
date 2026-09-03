from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.repositories import user as user_repo
from app.core.security import verify_password, create_access_token, get_token_remaining_seconds
from app.core.blacklist import add_to_blacklist


def s_register(db, user):
    existing = user_repo.db_get_by_username(db, user.username)
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    try:
        return user_repo.db_create(db, user)
    except IntegrityError:
        # The pre-check above is not atomic with INSERT; another request may
        # create the same username between those two operations.
        db.rollback()
        raise HTTPException(status_code=400, detail="用户名已存在")


def s_login(db, user):
    existing = user_repo.db_get_by_username(db, user.username)
    if existing is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(user.password, existing.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(existing.id)
    return {"access_token": token, "token_type": "bearer"}


def s_logout(token: str):
    remaining = get_token_remaining_seconds(token)
    add_to_blacklist(token, remaining)
    return {"detail": "已登出"}