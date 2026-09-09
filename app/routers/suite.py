from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.suite import SuiteCreate, SuiteOut, SuiteUpdate
from app.services import suite as suite_service


router = APIRouter(prefix="/suites", tags=["suites"])


@router.post("", response_model=SuiteOut, status_code=201)
def create_suite(
    suite: SuiteCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SUITE, Action.WRITE)),
):
    return suite_service.s_create(db, suite, context.project_id)


@router.get("", response_model=list[SuiteOut])
def list_suites(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SUITE, Action.READ)),
):
    return suite_service.s_list(db, context.project_id, skip, limit)


@router.get("/{suite_id}", response_model=SuiteOut)
def get_suite(
    suite_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SUITE, Action.READ)),
):
    return suite_service.s_get(db, suite_id, context.project_id)


@router.put("/{suite_id}", response_model=SuiteOut)
def update_suite(
    suite_id: int,
    suite: SuiteUpdate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SUITE, Action.WRITE)),
):
    return suite_service.s_update(db, suite_id, context.project_id, suite)


@router.delete("/{suite_id}")
def delete_suite(
    suite_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SUITE, Action.WRITE)),
):
    return suite_service.s_delete(db, suite_id, context.project_id)


@router.post("/{suite_id}/run")
def run_suite(
    suite_id: int,
    env_id: int | None = Query(None),
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SUITE, Action.EXECUTE)),
):
    return suite_service.run_suite(db, suite_id, context.project_id, env_id)
