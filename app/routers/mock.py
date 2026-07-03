import time
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.mock import MockCreate, MockOut
from app.services import mock as mock_service
from app.core.deps import get_current_project
from app.models.project import Project


router = APIRouter(prefix="/mocks", tags=["mocks"])


@router.post("", response_model=MockOut, status_code=201)
def create_mock(
    mock: MockCreate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return mock_service.s_create(db, mock, current_project.id)


@router.get("/{mock_id}", response_model=MockOut)
def get_mock(
    mock_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    m = mock_service.s_get(db, mock_id, current_project.id)
    if m is None:
        raise HTTPException(status_code=404, detail=f"挡板规则 id={mock_id} 不存在")
    return m


@router.get("", response_model=list[MockOut])
def list_mock(
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return mock_service.s_list(db, current_project.id)


@router.put("/{mock_id}", response_model=MockOut)
def update_mock(
    mock_id: int,
    mock: MockCreate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    m = mock_service.s_update(db, mock_id, mock, current_project.id)
    if m is None:
        raise HTTPException(status_code=404, detail=f"挡板规则 id={mock_id} 不存在")
    return m


@router.delete("/{mock_id}", response_model=MockOut)
def delete_mock(
    mock_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    m = mock_service.s_delete(db, mock_id, current_project.id)
    if m is None:
        raise HTTPException(status_code=404, detail=f"挡板规则 id={mock_id} 不存在")
    return m


# ========================================================================
# 挡板命中路由:被测系统/测试脚本调用,不需要认证。
# URL 前缀 /mock/{project_id}/xxx 是业界标准(Apifox / Postman Mock 同款),
# project_id 从路径参数取,不从 header 拿 —— 分工:业务 API 用 header,
# 挡板命中用 URL 前缀,面向不同调用者用不同风格是正常的。
# ========================================================================
hit_router = APIRouter(prefix="/mock", tags=["mock-hit"])


@hit_router.api_route("/{project_id}/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def hit_mock(project_id: int, full_path: str, request: Request, db: Session = Depends(get_db)):
    rule = mock_service.s_match(db, project_id, "/" + full_path, request.method)
    if rule is None:
        return JSONResponse(status_code=404, content={"detail": "未匹配到挡板规则"})
    if rule.delay_ms:
        time.sleep(rule.delay_ms / 1000)
    return JSONResponse(status_code=rule.status, content=rule.body)
