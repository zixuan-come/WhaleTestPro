from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.user import UserCreate, UserOut, TokenOut
from app.services import user as user_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    return user_service.s_register(db, user)


@router.post("/login", response_model=TokenOut)
def login(user: UserCreate, db: Session = Depends(get_db)):
    return user_service.s_login(db, user)









