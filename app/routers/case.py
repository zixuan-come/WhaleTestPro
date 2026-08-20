from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.case import CaseCreate, CaseOut, CaseUpdate
from app.schemas.response import ApiResponse, success_response
from app.services import case as case_service
from app.services import execution as execution_service
from app.core.deps import get_current_project
from app.models.project import Project


router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=ApiResponse[CaseOut], status_code=201)
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
    return success_response(c, message="用例创建成功", status_code=201)


@router.get("/{case_id}", response_model=ApiResponse[CaseOut])
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    c = case_service.s_get(db, case_id, current_project.id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"用例 id={case_id} 不存在")
    return success_response(c, message="查询成功")


@router.get("", response_model=ApiResponse[list[CaseOut]])
def list_case(
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return success_response(case_service.s_list(db, current_project.id), message="查询成功")


@router.put("/{case_id}", response_model=ApiResponse[CaseOut])
def update_case(
    case_id: int,
    case: CaseUpdate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    existing = case_service.s_get(db, case_id, current_project.id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"用例 id={case_id} 不存在")

    updated = case_service.s_update(db, case_id, case, current_project.id)
    if updated is None:
        raise HTTPException(
            status_code=400,
            detail=f"接口 id={case.interface_id} 不存在或不属于当前项目",
        )
    return success_response(updated, message="用例更新成功")


@router.delete("/{case_id}", response_model=ApiResponse[None])
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    c = case_service.s_delete(db, case_id, current_project.id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"用例 id={case_id} 不存在")
    return success_response(data=None, message="用例删除成功")


@router.post("/{case_id}/run", response_model=ApiResponse[dict | list])
def run_case(
    case_id: int,
    env_id: int | None = None,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return success_response(
        execution_service.run_case(db, case_id, env_id, current_project.id),
        message="用例执行完成",
    )


@router.post("/chain", response_model=ApiResponse[list])
def run_chain(
    case_ids: list[int],
    env_id: int | None = None,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return success_response(
        execution_service.run_chain(db, case_ids, env_id, current_project.id),
        message="链路执行完成",
    )
