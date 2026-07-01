import time
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.mock import MockCreate, MockOut
from app.services import mock as mock_service

router = APIRouter(prefix="/mocks", tags=["mocks"])


@router.post("", response_model=MockOut)
def create_mock(mock: MockCreate, db: Session = Depends(get_db)):
    return mock_service.s_create(db, mock)


@router.get("/{mock_id}", response_model=MockOut)
def get_mock(mock_id: int, db: Session = Depends(get_db)):
    return mock_service.s_get(db, mock_id)


@router.get("", response_model=list[MockOut])
def list_mock(db: Session = Depends(get_db)):
    return mock_service.s_list(db)


@router.put("/{mock_id}", response_model=MockOut)
def update_mock(mock_id: int, mock: MockCreate, db: Session = Depends(get_db)):
    return mock_service.s_update(db, mock_id, mock)


@router.delete("/{mock_id}", response_model=MockOut)
def delete_mock(mock_id: int, db: Session = Depends(get_db)):
    return mock_service.s_delete(db, mock_id)


hit_router = APIRouter(prefix="/mock", tags=["mock-hit"])


@hit_router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def hit_mock(full_path: str, request: Request, db: Session = Depends(get_db)):
    rule = mock_service.s_match(db, "/" + full_path, request.method)
    if rule is None:
        return JSONResponse(status_code=404, content={"detail": "未匹配到挡板规则"})
    if rule.delay_ms:
        time.sleep(rule.delay_ms / 1000)
    return JSONResponse(status_code=rule.status, content=rule.body)



