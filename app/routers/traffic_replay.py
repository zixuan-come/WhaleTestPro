from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.response import ApiResponse, success_response
from app.schemas.traffic_replay import ReplayRequest
from app.services import traffic_replay as traffic_replay_service


router = APIRouter(prefix="/traffic/replay", tags=["traffic"])


@router.post("/{record_id}", response_model=ApiResponse[dict])
def replay(
    record_id: int,
    req: ReplayRequest | None = None,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.TRAFFIC, Action.EXECUTE)),
):
    req = req or ReplayRequest()
    try:
        result = traffic_replay_service.s_replay(
            db, record_id, context.project_id, req.env_id, req.field_rules
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="录制记录不存在")
    return success_response(result, message="流量回放完成")
