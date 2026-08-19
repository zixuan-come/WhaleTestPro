from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, login_rate_limit, oauth2_scheme
from app.database import get_db
from app.models.user import User
from app.schemas.response import ApiResponse, success_response
from app.schemas.user import TokenOut, UserCreate, UserOut
from app.services import user as user_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse[UserOut], status_code=201)
def register(user: UserCreate, db: Session = Depends(get_db)):
    return success_response(
        user_service.s_register(db, user),
        message="\u6ce8\u518c\u6210\u529f",
        status_code=201,
    )


@router.post("/login", response_model=ApiResponse[TokenOut])
def login(
    user: UserCreate,
    db: Session = Depends(get_db),
    _: None = Depends(login_rate_limit),
):
    return success_response(
        user_service.s_login(db, user),
        message="\u767b\u5f55\u6210\u529f",
    )


@router.post("/logout", response_model=ApiResponse[None])
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
):
    user_service.s_logout(token)
    return success_response(data=None, message="\u767b\u51fa\u6210\u529f")
