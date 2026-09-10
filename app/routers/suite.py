from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_project
from app.models.project import Project
from app.schemas.suite import SuiteCreate, SuiteUpdate, SuiteOut
from app.services import suite as suite_service


router = APIRouter(prefix="/suites", tags=["suites"])


@router.post("", response_model=SuiteOut, status_code=201)
def create_suite(
    suite: SuiteCreate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    """创建测试套件"""
    return suite_service.s_create(db, suite, current_project.id)


@router.get("", response_model=list[SuiteOut])
def list_suites(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    """获取测试套件列表"""
    return suite_service.s_list(db, current_project.id, skip, limit)


@router.get("/{suite_id}", response_model=SuiteOut)
def get_suite(
    suite_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    """获取测试套件详情"""
    return suite_service.s_get(db, suite_id, current_project.id)


@router.put("/{suite_id}", response_model=SuiteOut)
def update_suite(
    suite_id: int,
    suite: SuiteUpdate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    """更新测试套件"""
    return suite_service.s_update(db, suite_id, current_project.id, suite)


@router.delete("/{suite_id}")
def delete_suite(
    suite_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    """删除测试套件"""
    return suite_service.s_delete(db, suite_id, current_project.id)


@router.post("/{suite_id}/run")
def run_suite(
    suite_id: int,
    env_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    """运行测试套件"""
    return suite_service.run_suite(db, suite_id, current_project.id, env_id)
