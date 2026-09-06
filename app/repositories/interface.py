from sqlalchemy.orm import Session
from app.models.interface import Interface


# 每个方法都多带一个 project_id 参数,SQL 里全部 WHERE 加 project_id 过滤。
# 这是"多租户安全铁律":每次查询都在最底层锁租户 id,不指望上层记得校验。
# get/delete 不加过滤就是越权漏洞(你在 A 项目却读到 B 项目的接口)。

def db_create(db: Session, interface, project_id: int):
    # 建接口时,把当前项目 id 塞进 model 一起 add
    db_interface = Interface(**interface.model_dump(), project_id=project_id)
    db.add(db_interface)
    db.commit()
    db.refresh(db_interface)
    return db_interface


def db_get(db: Session, interface_id: int, project_id: int):
    # 双条件过滤:id + project_id 都匹配才返回,防越权
    return db.query(Interface).filter(
        Interface.id == interface_id,
        Interface.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int):
    # 列表只返回当前项目的接口
    return db.query(Interface).filter(Interface.project_id == project_id).all()


def db_delete(db: Session, interface_id: int, project_id: int):
    # 删除也要双条件,别项目的接口对当前用户表现为"不存在"
    db_interface = db.query(Interface).filter(
        Interface.id == interface_id,
        Interface.project_id == project_id,
    ).first()
    if db_interface is None:
        return None
    db.delete(db_interface)
    db.commit()
    return db_interface


def db_update(db:Session, interface_id: int, project_id: int, patch):
    db_interface = db.query(Interface).filter(
        Interface.id == interface_id,
        Interface.project_id == project_id,
    ).first()
    if db_interface is None:
        return None
    for k, v in patch.model_dump().items():
        setattr(db_interface, k, v)
    db.commit()
    db.refresh(db_interface)
    return db_interface


def db_rename_category(db: Session, project_id: int, old_name: str, new_name: str):
    # bulk UPDATE:一次 SQL 改所有匹配的接口,不循环查改
    count = db.query(Interface).filter(
        Interface.project_id == project_id,
        Interface.category == old_name,
    ).update({Interface.category: new_name})
    db.commit()
    return count


def db_delete_category(db: Session, project_id: int, name: str):
    # 删除分类 = 把所有引用的接口 category 置 NULL(接口本身不删)
    count = db.query(Interface).filter(
        Interface.project_id == project_id,
        Interface.category == name,
    ).update({Interface.category: None})
    db.commit()
    return count
def db_references(db: Session, interface_id: int, project_id: int):
    interface = db.query(Interface).filter(
        Interface.id == interface_id,
        Interface.project_id == project_id,
    ).first()
    if interface is None:
        return None

    from app.models.case import Case
    from app.models.report import TestReport
    from app.models.scenario import Scenario

    cases = db.query(Case).filter(
        Case.interface_id == interface_id,
        Case.project_id == project_id,
    ).all()
    case_ids = [case.id for case in cases]

    # 批量取报告：按时间倒序，首次出现的 case_id 就是该用例的最新报告。
    latest_passed = {}
    if case_ids:
        reports = db.query(TestReport).filter(
            TestReport.project_id == project_id,
            TestReport.case_id.in_(case_ids),
        ).all()
        latest_reports = {}
        for report in reports:
            previous = latest_reports.get(report.case_id)
            current_key = (report.created_at or 0, report.id)
            previous_key = ((previous.created_at or 0), previous.id) if previous else None
            if previous is None or current_key > previous_key:
                latest_reports[report.case_id] = report
        latest_passed = {case_id: report.passed for case_id, report in latest_reports.items()}

    # 场景只查一次，并建立 case_id -> scenario_ids 索引，避免逐 case 扫描全部场景。
    scenario_ids_by_case = {}
    scenarios = db.query(Scenario).filter(Scenario.project_id == project_id).all()
    for scenario in scenarios:
        for case_id in scenario.case_ids or []:
            scenario_ids_by_case.setdefault(case_id, []).append(scenario.id)

    result = [
        {
            "id": case.id,
            "name": case.name,
            "scenario_ids": scenario_ids_by_case.get(case.id, []),
            "last_passed": latest_passed.get(case.id),
        }
        for case in cases
    ]
    return {"interface": interface, "case_count": len(result), "cases": result}

def db_migrate_cases(db: Session, source_id: int, target_id: int, project_id: int):
    from app.models.case import Case
    source = db.query(Interface).filter(Interface.id == source_id, Interface.project_id == project_id).first()
    target = db.query(Interface).filter(Interface.id == target_id, Interface.project_id == project_id).first()
    if source is None or target is None:
        return None
    cases = db.query(Case).filter(Case.interface_id == source_id, Case.project_id == project_id).all()
    for case in cases:
        case.interface_id = target_id
    db.commit()
    return len(cases)
