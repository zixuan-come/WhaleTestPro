from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.response import ApiResponse, success_response
from app.services import execution as execution_service


router = APIRouter(prefix="/regression", tags=["regression"])


@router.post("", response_model=ApiResponse[dict])
def run_regression(
    case_ids: list[int] | None = None,
    env_id: int | None = None,
    tag: str | None = None,
    notify: bool = False,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.REGRESSION, Action.EXECUTE)),
):
    return success_response(
        execution_service.run_regression(
            db,
            case_ids,
            env_id,
            tag,
            notify,
            context.project_id,
        ),
        message="回归执行完成",
    )
