from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import execution as execution_service
from app.core.deps import get_current_project
from app.models.project import Project

router = APIRouter(prefix="/regression", tags=["regression"])

@router.post("")
def run_regression(
    case_ids: list[int] | None = None,
    env_id: int | None = None,
    tag: str | None = None,
    notify: bool = False,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return execution_service.run_regression(db, case_ids, env_id, tag, notify, current_project.id)
