from sqlalchemy.orm import Session
from app.repositories import scenario as scenario_repo
from app.services import execution as execution_service


def s_create(db: Session, sc, project_id: int):
    return scenario_repo.db_create(db, sc, project_id)


def s_get(db: Session, scenario_id: int, project_id: int):
    return scenario_repo.db_get(db, scenario_id, project_id)


def s_list(db: Session, project_id: int):
    return scenario_repo.db_list(db, project_id)


def s_update(db: Session, scenario_id: int, project_id: int, patch):
    return scenario_repo.db_update(db, scenario_id, project_id, patch)


def s_delete(db: Session, scenario_id: int, project_id: int):
    return scenario_repo.db_delete(db, scenario_id, project_id)


def s_run(db: Session, scenario_id: int, env_id, project_id: int):
    """跑场景 = 拿 case_ids 交给 execution.run_chain 执行,不重复实现"""
    sc = scenario_repo.db_get(db, scenario_id, project_id)
    if sc is None:
        return None
    return execution_service.run_chain(db, sc.case_ids or [], env_id, project_id)
