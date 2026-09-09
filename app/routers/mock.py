import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.mock import MockCreate, MockOut
from app.schemas.response import ApiResponse, success_response
from app.services import mock as mock_service


router = APIRouter(prefix="/mocks", tags=["mocks"])


@router.post("", response_model=ApiResponse[MockOut], status_code=201)
def create_mock(
    mock: MockCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.MOCK, Action.WRITE)),
):
    return success_response(
        mock_service.s_create(db, mock, context.project_id),
        message="Mock 创建成功",
        status_code=201,
    )


@router.get("/{mock_id}", response_model=ApiResponse[MockOut])
def get_mock(
    mock_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.MOCK, Action.READ)),
):
    result = mock_service.s_get(db, mock_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"挡板规则 id={mock_id} 不存在")
    return success_response(result, message="查询成功")


@router.get("", response_model=ApiResponse[list[MockOut]])
def list_mock(
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.MOCK, Action.READ)),
):
    return success_response(mock_service.s_list(db, context.project_id), message="查询成功")


@router.put("/{mock_id}", response_model=ApiResponse[MockOut])
def update_mock(
    mock_id: int,
    mock: MockCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.MOCK, Action.WRITE)),
):
    result = mock_service.s_update(db, mock_id, mock, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"挡板规则 id={mock_id} 不存在")
    return success_response(result, message="Mock 更新成功")


@router.delete("/{mock_id}", response_model=ApiResponse[None])
def delete_mock(
    mock_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.MOCK, Action.WRITE)),
):
    result = mock_service.s_delete(db, mock_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"挡板规则 id={mock_id} 不存在")
    return success_response(data=None, message="Mock 删除成功")


# Public mock-hit route for external systems under test.
hit_router = APIRouter(prefix="/mock", tags=["mock-hit"])


@hit_router.api_route(
    "/{project_id}/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
def hit_mock(
    project_id: int,
    full_path: str,
    request: Request,
    db: Session = Depends(get_db),
):
    rule = mock_service.s_match(db, project_id, "/" + full_path, request.method)
    if rule is None:
        return JSONResponse(status_code=404, content={"detail": "未匹配到挡板规则"})
    if rule.delay_ms:
        time.sleep(rule.delay_ms / 1000)
    return JSONResponse(status_code=rule.status, content=rule.body)
