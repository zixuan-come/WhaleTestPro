from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.security import decode_access_token
from app.repositories import user as user_repo
from app.repositories import project as project_repo
from app.core.blacklist import is_blacklisted
from app.core.ratelimit import check_rate_limit
from app.models.project import Project

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = user_repo.db_get_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def login_rate_limit(request: Request):
    ip = request.client.host
    if not check_rate_limit(f"login:{ip}", limit=5, window_seconds=60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后再试",
        )


def get_current_project(
    x_project_id: int = Header(..., alias="X-Project-Id"),
    db: Session = Depends(get_db),
) -> Project:
    """
    多项目依赖:从 HTTP header X-Project-Id 读当前项目,校验存在后返回 Project 对象。
    router 里一句 Depends(get_current_project) 就能拿到当前 project,项目不存在自动 404。
    """
    project = project_repo.db_get(db, x_project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 id={x_project_id} 不存在",
        )
    return project



