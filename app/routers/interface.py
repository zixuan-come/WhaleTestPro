from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.schemas.interface import InterfaceCreate, InterfaceOut, CategoryRename, InterfaceMigrate
from app.schemas.response import ApiResponse, success_response
from app.services import interface as api_service
from app.core.deps import get_current_user, get_current_project
from app.models.user import User
from app.models.project import Project

router = APIRouter(prefix="/interfaces", tags=["interfaces"])


# ⚠️ 顺序重要:/categories/... 必须在 /{interface_id} 之前注册,
# 否则 FastAPI 会尝试把 "categories" 当 int 解析报 422。

@router.patch("/categories/rename", response_model=ApiResponse[dict])
def rename_category(
    body: CategoryRename,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    count = api_service.s_rename_category(db, current_project.id, body.old_name, body.new_name)
    return success_response({"affected": count}, message="分类重命名成功")


@router.delete("/categories/{name}", response_model=ApiResponse[dict])
def delete_category(
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    count = api_service.s_delete_category(db, current_project.id, name)
    return success_response({"affected": count}, message="分类清空成功")


@router.post("", response_model=ApiResponse[InterfaceOut], status_code=201)
def create_interface(
    interface: InterfaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),   # ← 从 X-Project-Id header 注入
):
    return success_response(
        api_service.s_create(db, interface, current_project.id),
        message="接口创建成功",
        status_code=201,
    )



@router.get("/{interface_id}/references", response_model=ApiResponse[dict])
def interface_references(interface_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user), current_project: Project = Depends(get_current_project)):
    result = api_service.s_references(db, interface_id, current_project.id)
    if result is None: raise HTTPException(status_code=404, detail=f"接口 id={interface_id} 不存在")
    return success_response(result, message="查询接口引用成功")

@router.post("/{interface_id}/migrate", response_model=ApiResponse[dict])
def migrate_interface_cases(interface_id: int, body: InterfaceMigrate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user), current_project: Project = Depends(get_current_project)):
    if interface_id == body.target_interface_id: raise HTTPException(status_code=400, detail="目标接口不能与当前接口相同")
    count = api_service.s_migrate_cases(db, interface_id, body.target_interface_id, current_project.id)
    if count is None: raise HTTPException(status_code=404, detail="源接口或目标接口不存在")
    return success_response({"migrated_count": count}, message="用例迁移成功")
@router.get("/{interface_id}", response_model=ApiResponse[InterfaceOut])
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
    return success_response(p, message="查询成功")


@router.get("", response_model=ApiResponse[list[InterfaceOut]])
def list_interface(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    return success_response(api_service.s_list(db, current_project.id), message="查询成功")


@router.delete("/{interface_id}", response_model=ApiResponse[None])
def delete_interface(
    interface_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_project: Project = Depends(get_current_project),
):
    try:
        p = api_service.s_delete(db, interface_id, current_project.id)
    except IntegrityError:
        db.rollback()
        references = api_service.s_references(db, interface_id, current_project.id) or {"case_count": 0, "cases": []}
        raise HTTPException(status_code=409, detail={"message": "接口仍被测试用例引用", "data": {"interface_id": interface_id, "case_count": references["case_count"], "cases": [{"id": c["id"], "name": c["name"]} for c in references["cases"][:50]], "truncated": references["case_count"] > 50}})
    if p is None:
        raise HTTPException(status_code=404, detail=f"接口 id={interface_id} 不存在")
    return success_response(data=None, message="接口删除成功")


@router.put("/{interface_id}", response_model=ApiResponse[InterfaceOut])
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
    return success_response(p, message="接口更新成功")


