from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.case import CaseCreate, CaseOut, CaseUpdate
from app.schemas.response import ApiResponse, success_response
from app.services import case as case_service
from app.services import execution as execution_service


router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=ApiResponse[CaseOut], status_code=201)
def create_case(
    case: CaseCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.CASE, Action.WRITE)),
):
    result = case_service.s_create(db, case, context.project_id)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail=f"接口 id={case.interface_id} 不存在或不属于当前项目",
        )
    return success_response(result, message="用例创建成功", status_code=201)


@router.get("/{case_id}", response_model=ApiResponse[CaseOut])
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.CASE, Action.READ)),
):
    result = case_service.s_get(db, case_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"用例 id={case_id} 不存在")
    return success_response(result, message="查询成功")


@router.get("", response_model=ApiResponse[list[CaseOut]])
def list_case(
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.CASE, Action.READ)),
):
    return success_response(case_service.s_list(db, context.project_id), message="查询成功")


@router.put("/{case_id}", response_model=ApiResponse[CaseOut])
def update_case(
    case_id: int,
    case: CaseUpdate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.CASE, Action.WRITE)),
):
    existing = case_service.s_get(db, case_id, context.project_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"用例 id={case_id} 不存在")
    updated = case_service.s_update(db, case_id, case, context.project_id)
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
    context: ProjectContext = Depends(authorize(Resource.CASE, Action.WRITE)),
):
    result = case_service.s_delete(db, case_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"用例 id={case_id} 不存在")
    return success_response(data=None, message="用例删除成功")


@router.post("/{case_id}/run", response_model=ApiResponse[dict | list])
def run_case(
    case_id: int,
    env_id: int | None = None,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.CASE, Action.EXECUTE)),
):
    try:
        result = execution_service.run_case(db, case_id, env_id, context.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(result, message="用例执行完成")


@router.post("/chain", response_model=ApiResponse[list])
def run_chain(
    case_ids: list[int],
    env_id: int | None = None,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.CASE, Action.EXECUTE)),
):
    try:
        result = execution_service.run_chain(db, case_ids, env_id, context.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(result, message="链路执行完成")
