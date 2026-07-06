from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.interface import InterfaceCreate, InterfaceOut, CategoryRename
from app.services import interface as api_service
from app.core.deps import get_current_user, get_current_project
from app.models.user import User
from app.models.project import Project

router = APIRouter(prefix="/interfaces", tags=["interfaces"])


# ⚠️ 顺序重要:/categories/... 必须在 /{interface_id} 之前注册,
# 否则 FastAPI 会尝试把 "categories" 当 int 解析报 422。

@router.patch("/categories/rename")
def rename_category(
    body: CategoryRename,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    count = api_service.s_rename_category(db, current_project.id, body.old_name, body.new_name)
    return {"affected": count}


@router.delete("/categories/{name}")
def delete_category(
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    count = api_service.s_delete_category(db, current_project.id, name)
    return {"affected": count}


@router.post("", response_model=InterfaceOut, status_code=201)
def create_interface(
    interface: InterfaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),   # ← 从 X-Project-Id header 注入
):
    return api_service.s_create(db, interface, current_project.id)


@router.get("/{interface_id}", response_model=InterfaceOut)
def get_interface(
    interface_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    # 加 404 处理(期三顺带补的期一坑):不存在别返 500
    p = api_service.s_get(db, interface_id, current_project.id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"接口 id={interface_id} 不存在")
    return p


@router.get("", response_model=list[InterfaceOut])
def list_interface(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    return api_service.s_list(db, current_project.id)


@router.delete("/{interface_id}", response_model=InterfaceOut)
def delete_interface(
    interface_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    p = api_service.s_delete(db, interface_id, current_project.id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"接口 id={interface_id} 不存在")
    return p


@router.put("/{interface_id}", response_model=InterfaceOut)
def update_interface(
    interface_id: int,
    patch: InterfaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    p = api_service.s_update(db, interface_id, current_project.id, patch)
    if p is None:
        raise HTTPException(status_code=404, detail=f"接口 id={interface_id} 不存在")
    return p



