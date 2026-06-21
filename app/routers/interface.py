from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.interface import InterfaceCreate, InterfaceOut
from app.services import interface as api_service
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/interfaces", tags=["interfaces"])

@router.post("", response_model=InterfaceOut)
def create_interface(interface: InterfaceCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),):
    return api_service.s_create(db, interface)


@router.get("/{interface_id}", response_model=InterfaceOut)
def get_interface(interface_id: int, db: Session = Depends(get_db)):
    return api_service.s_get(db, interface_id)


@router.get("", response_model=list[InterfaceOut])
def list_interface(db: Session = Depends(get_db)):
    return api_service.s_list(db)


@router.delete("/{interface_id}", response_model=InterfaceOut)
def delete_interface(interface_id: int, db: Session = Depends(get_db)):
    return api_service.s_delete(db, interface_id)



