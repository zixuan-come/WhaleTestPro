from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.schemas.project import ProjectCreate, ProjectOut
from app.services import project as project_service
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # unique=True 冲突时数据库抛 IntegrityError,catch 后转成 409 Conflict
    # 不 catch 的话前端拿到 500,看不出是"重名"还是"服务真挂了"
    try:
        return project_service.s_create(db, project)
    except IntegrityError:
        db.rollback()  # 失败事务必须回滚,否则同一 session 后续查询都会报错
        raise HTTPException(status_code=409, detail=f"项目名 '{project.name}' 已存在")


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.s_list(db)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = project_service.s_get(db, project_id)
    # Repository 查不到返 None,Router 层转成 404
    # 不转的话 response_model 会拿 None 去校验 → Pydantic 失败 → 崩 500
    if p is None:
        raise HTTPException(status_code=404, detail=f"项目 id={project_id} 不存在")
    return p


@router.delete("/{project_id}", response_model=ProjectOut)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = project_service.s_delete(db, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"项目 id={project_id} 不存在")
    return p



