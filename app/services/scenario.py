from sqlalchemy.orm import Session
from app.repositories import scenario as scenario_repo
from app.services import execution as execution_service
from app.repositories import case as case_repo, interface as interface_repo
from app.core.scenario_steps import case_snapshot
from fastapi import HTTPException
from copy import deepcopy
from pydantic import ValidationError


def s_create(db: Session, sc, project_id: int):
    sc = _with_steps(db, sc, project_id)
    return scenario_repo.db_create(db, sc, project_id)


def s_get(db: Session, scenario_id: int, project_id: int):
    return scenario_repo.db_get(db, scenario_id, project_id)


def s_list(db: Session, project_id: int):
    return scenario_repo.db_list(db, project_id)


def s_update(db: Session, scenario_id: int, project_id: int, patch):
    existing = scenario_repo.db_get(db, scenario_id, project_id)
    if existing is None:
        return None
    patch = _with_steps(db, patch, project_id, existing)
    return scenario_repo.db_update(db, scenario_id, project_id, patch)


def _with_steps(db, data, project_id, existing=None):
    supplied = data.model_fields_set
    old_steps = getattr(existing, 'steps', None)
    if 'steps' in supplied and data.steps is not None:
        steps = [step.model_dump() for step in data.steps]
        old = {step['step_id']: step for step in old_steps or []}
        for step in steps:
            previous = old.get(step['step_id'], {})
            if step.get('missing_reason'):
                if step != previous:
                    raise HTTPException(400, '失效步骤只能保留或移除，请重新选择来源用例')
                continue
            if interface_repo.db_get(db, step['interface_id'], project_id) is None and previous.get('interface_id') != step['interface_id']:
                raise HTTPException(400, '步骤关联接口不存在或不属于当前项目')
            source = step.get('source_case_id')
            if source and case_repo.db_get(db, source, project_id) is None and previous.get('source_case_id') != source:
                raise HTTPException(400, '步骤来源用例不存在或不属于当前项目')
        ids = [step['source_case_id'] for step in steps if step.get('source_case_id') is not None]
        if 'case_ids' in supplied and data.case_ids != ids:
            raise HTTPException(400, 'case_ids 与步骤来源不一致，请使用 steps 保存场景')
    elif existing is not None and 'case_ids' not in supplied and old_steps is not None:
        steps = deepcopy(old_steps)
        ids = list(existing.case_ids or [])
    else:
        ids = list(data.case_ids or [])
        # Old clients can reorder references without erasing edited snapshots.
        available = {}
        for step in old_steps or []:
            available.setdefault(step.get('source_case_id'), []).append(step)
        steps = []
        for number in ids:
            previous = available.get(number, [])
            if previous:
                steps.append(deepcopy(previous.pop(0)))
                continue
            case = case_repo.db_get(db, number, project_id)
            interface = interface_repo.db_get(db, case.interface_id, project_id) if case is not None else None
            steps.append(case_snapshot(case, interface, source_id=number))
    payload = data.model_dump()
    payload.update(case_ids=ids, steps=steps)
    # Validate the resolved snapshot, including all legacy-client additions.
    try:
        return type(data).model_validate(payload)
    except ValidationError:
        raise HTTPException(400, '来源用例配置不能转换为场景步骤，请检查请求方法、路径和期望状态码') from None


def s_delete(db: Session, scenario_id: int, project_id: int):
    return scenario_repo.db_delete(db, scenario_id, project_id)


def s_run(db: Session, scenario_id: int, env_id, project_id: int):
    """跑场景 = 拿 case_ids 交给 execution.run_chain 执行,不重复实现"""
    sc = scenario_repo.db_get(db, scenario_id, project_id)
    if sc is None:
        return None
    return execution_service.run_chain(
        db,
        sc.case_ids or [],
        env_id,
        project_id,
        scenario_id=sc.id,
        scenario_name=sc.name,
        **({'steps': sc.steps} if getattr(sc, 'steps', None) is not None else {}),
    )
