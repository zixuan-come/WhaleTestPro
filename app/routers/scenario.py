from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.response import ApiResponse, success_response
from app.schemas.scenario import ScenarioCreate, ScenarioOut
from app.services import scenario as scenario_service


router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=ApiResponse[list[ScenarioOut]])
def list_scenarios(
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCENARIO, Action.READ)),
):
    return success_response(scenario_service.s_list(db, context.project_id), message="查询成功")


@router.post("", response_model=ApiResponse[ScenarioOut], status_code=201)
def create_scenario(
    sc: ScenarioCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCENARIO, Action.WRITE)),
):
    return success_response(
        scenario_service.s_create(db, sc, context.project_id),
        message="场景创建成功",
        status_code=201,
    )


@router.get("/{scenario_id}", response_model=ApiResponse[ScenarioOut])
def get_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCENARIO, Action.READ)),
):
    result = scenario_service.s_get(db, scenario_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"场景 id={scenario_id} 不存在")
    return success_response(result, message="查询成功")


@router.put("/{scenario_id}", response_model=ApiResponse[ScenarioOut])
def update_scenario(
    scenario_id: int,
    patch: ScenarioCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCENARIO, Action.WRITE)),
):
    result = scenario_service.s_update(db, scenario_id, context.project_id, patch)
    if result is None:
        raise HTTPException(status_code=404, detail=f"场景 id={scenario_id} 不存在")
    return success_response(result, message="场景更新成功")


@router.delete("/{scenario_id}", response_model=ApiResponse[None])
def delete_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCENARIO, Action.WRITE)),
):
    result = scenario_service.s_delete(db, scenario_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"场景 id={scenario_id} 不存在")
    return success_response(data=None, message="场景删除成功")


@router.post("/{scenario_id}/run", response_model=ApiResponse[list])
def run_scenario(
    scenario_id: int,
    env_id: int | None = None,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCENARIO, Action.EXECUTE)),
):
    try:
        result = scenario_service.s_run(db, scenario_id, env_id, context.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"场景 id={scenario_id} 不存在")
    return success_response(result, message="场景执行完成")
