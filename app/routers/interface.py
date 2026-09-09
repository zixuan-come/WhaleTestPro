from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.interface import CategoryRename, InterfaceCreate, InterfaceMigrate, InterfaceOut
from app.schemas.response import ApiResponse, success_response
from app.services import execution
from app.services import interface as api_service

router = APIRouter(prefix="/interfaces", tags=["interfaces"])


# /categories/... must be registered before /{interface_id}.
@router.patch("/categories/rename", response_model=ApiResponse[dict])
def rename_category(
    body: CategoryRename,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.INTERFACE, Action.WRITE)),
):
    count = api_service.s_rename_category(db, context.project_id, body.old_name, body.new_name)
    return success_response({"affected": count}, message="分类重命名成功")


@router.delete("/categories/{name}", response_model=ApiResponse[dict])
def delete_category(
    name: str,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.INTERFACE, Action.WRITE)),
):
    count = api_service.s_delete_category(db, context.project_id, name)
    return success_response({"affected": count}, message="分类清空成功")


@router.post("", response_model=ApiResponse[InterfaceOut], status_code=201)
def create_interface(
    interface: InterfaceCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.INTERFACE, Action.WRITE)),
):
    return success_response(
        api_service.s_create(db, interface, context.project_id),
        message="接口创建成功",
        status_code=201,
    )


@router.get("/{interface_id}/references", response_model=ApiResponse[dict])
def interface_references(
    interface_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.INTERFACE, Action.READ)),
):
    result = api_service.s_references(db, interface_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"接口 id={interface_id} 不存在")
    return success_response(result, message="查询接口引用成功")


@router.post("/{interface_id}/migrate", response_model=ApiResponse[dict])
def migrate_interface_cases(
    interface_id: int,
    body: InterfaceMigrate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.CASE, Action.WRITE)),
):
    if interface_id == body.target_interface_id:
        raise HTTPException(status_code=400, detail="目标接口不能与当前接口相同")
    count = api_service.s_migrate_cases(
        db, interface_id, body.target_interface_id, context.project_id
    )
    if count is None:
        raise HTTPException(status_code=404, detail="源接口或目标接口不存在")
    return success_response({"migrated_count": count}, message="用例迁移成功")


@router.post("/{interface_id}/run", response_model=ApiResponse[dict])
def run_interface(
    interface_id: int,
    env_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.INTERFACE, Action.EXECUTE)),
):
    try:
        result = execution.run_interface(db, interface_id, env_id, context.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"接口 id={interface_id} 不存在")
    return success_response(result, message="接口执行完成")


@router.get("/{interface_id}", response_model=ApiResponse[InterfaceOut])
def get_interface(
    interface_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.INTERFACE, Action.READ)),
):
    result = api_service.s_get(db, interface_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"接口 id={interface_id} 不存在")
    return success_response(result, message="查询成功")


@router.get("", response_model=ApiResponse[list[InterfaceOut]])
def list_interface(
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.INTERFACE, Action.READ)),
):
    return success_response(api_service.s_list(db, context.project_id), message="查询成功")


@router.delete("/{interface_id}", response_model=ApiResponse[None])
def delete_interface(
    interface_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.INTERFACE, Action.WRITE)),
):
    try:
        result = api_service.s_delete(db, interface_id, context.project_id)
    except IntegrityError:
        db.rollback()
        references = api_service.s_references(db, interface_id, context.project_id) or {
            "case_count": 0,
            "cases": [],
        }
        raise HTTPException(
            status_code=409,
            detail={
                "message": "接口仍被测试用例引用",
                "data": {
                    "interface_id": interface_id,
                    "case_count": references["case_count"],
                    "cases": [
                        {"id": item["id"], "name": item["name"]}
                        for item in references["cases"][:50]
                    ],
                    "truncated": references["case_count"] > 50,
                },
            },
        )
    if result is None:
        raise HTTPException(status_code=404, detail=f"接口 id={interface_id} 不存在")
    return success_response(data=None, message="接口删除成功")


@router.put("/{interface_id}", response_model=ApiResponse[InterfaceOut])
def update_interface(
    interface_id: int,
    patch: InterfaceCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.INTERFACE, Action.WRITE)),
):
    result = api_service.s_update(db, interface_id, context.project_id, patch)
    if result is None:
        raise HTTPException(status_code=404, detail=f"接口 id={interface_id} 不存在")
    return success_response(result, message="接口更新成功")
