from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.case import CaseCreate, CaseOut
from app.services import case as case_service
from app.services import execution as execution_service
from app.core.deps import get_current_project
from app.models.project import Project


router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseOut, status_code=201)
def create_case(
    case: CaseCreate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    c = case_service.s_create(db, case, current_project.id)
    if c is None:
        # s_create 校验失败:关联的 interface 不属于当前项目
        raise HTTPException(
            status_code=400,
            detail=f"接口 id={case.interface_id} 不存在或不属于当前项目",
        )
    return c


@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    c = case_service.s_get(db, case_id, current_project.id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"用例 id={case_id} 不存在")
    return c


@router.get("", response_model=list[CaseOut])
def list_case(
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return case_service.s_list(db, current_project.id)


@router.delete("/{case_id}", response_model=CaseOut)
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    c = case_service.s_delete(db, case_id, current_project.id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"用例 id={case_id} 不存在")
    return c


@router.post("/{case_id}/run")
def run_case(
    case_id: int,
    env_id: int | None = None,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return execution_service.run_case(db, case_id, env_id, current_project.id)


@router.post("/chain")
def run_chain(
    case_ids: list[int],
    env_id: int | None = None,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return execution_service.run_chain(db, case_ids, env_id, current_project.id)
