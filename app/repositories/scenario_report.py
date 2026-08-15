from sqlalchemy.orm import Session, selectinload

from app.models.scenario_report import ScenarioReport, ScenarioReportStep


def db_create(
    db: Session,
    *,
    scenario_id: int,
    scenario_name: str,
    project_id: int,
    created_at,
    duration_ms: int,
    steps: list[dict],
):
    passed_steps = sum(1 for step in steps if step["passed"])
    report = ScenarioReport(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        passed=bool(steps) and passed_steps == len(steps),
        total_steps=len(steps),
        passed_steps=passed_steps,
        failed_steps=len(steps) - passed_steps,
        duration_ms=duration_ms,
        created_at=created_at,
        project_id=project_id,
    )
    db.add(report)
    db.flush()

    for step in steps:
        db.add(ScenarioReportStep(report_id=report.id, **step))

    db.commit()
    db.refresh(report)
    return report


def db_get(db: Session, report_id: int, project_id: int):
    return (
        db.query(ScenarioReport)
        .options(selectinload(ScenarioReport.steps))
        .filter(
            ScenarioReport.id == report_id,
            ScenarioReport.project_id == project_id,
        )
        .first()
    )


def db_page(db: Session, project_id: int, offset: int, limit: int):
    base_query = db.query(ScenarioReport).filter(
        ScenarioReport.project_id == project_id,
    )
    items = (
        base_query.order_by(ScenarioReport.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = base_query.count()
    passed_count = base_query.filter(ScenarioReport.passed.is_(True)).count()
    return {
        "items": items,
        "total": total,
        "passed_count": passed_count,
        "failed_count": total - passed_count,
    }
