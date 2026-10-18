from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.response import ApiResponse, success_response
from app.services import execution as execution_service
from app.services import regression as selection_service
from app.schemas.regression import RegressionSelection, RegressionRun


router = APIRouter(prefix="/regression", tags=["regression"])


@router.get("/options", response_model=ApiResponse[dict])
def regression_options(db: Session = Depends(get_db), context: ProjectContext = Depends(authorize(Resource.REGRESSION, Action.READ))):
    return success_response(selection_service.options(db, context.project_id))


@router.post("/preview", response_model=ApiResponse[dict])
def preview_regression(selection: RegressionSelection, db: Session = Depends(get_db),
                       context: ProjectContext = Depends(authorize(Resource.REGRESSION, Action.EXECUTE))):
    return success_response(selection_service.preview(db, context.project_id, selection))


@router.post("/run", response_model=ApiResponse[dict])
def run_selected_regression(selection: RegressionRun, db: Session = Depends(get_db),
                            context: ProjectContext = Depends(authorize(Resource.REGRESSION, Action.EXECUTE))):
    return success_response(selection_service.run(db, context.project_id, selection), message="回归执行完成")


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
