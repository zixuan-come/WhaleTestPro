from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.case import CaseCreate, CaseOut
from app.services import case as case_service
from app.services import execution as execution_service


router = APIRouter(prefix="/cases", tags=["cases"])

@router.post("", response_model=CaseOut)
def create_case(case: CaseCreate, db: Session = Depends(get_db)):
    return case_service.s_create(db, case)


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db)):
    return case_service.s_get(db, case_id)


@router.get("", response_model=list[CaseOut])
def list_case(db: Session = Depends(get_db)):
    return case_service.s_list(db)


@router.delete("/{case_id}", response_model=CaseOut)
def delete_case(case_id: int, db: Session = Depends(get_db)):
    return case_service.s_delete(db, case_id)


@router.post("/{case_id}/run")
def run_case(case_id: int, db: Session = Depends(get_db)):
    return execution_service.run_case(db, case_id)

