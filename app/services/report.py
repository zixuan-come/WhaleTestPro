from sqlalchemy.orm import Session
from app.repositories import report as report_repo


def s_get(db: Session, report_id: int, project_id: int):
    return report_repo.db_get(db, report_id, project_id)


def s_page(db: Session, project_id: int, page: int, page_size: int):
    result = report_repo.db_page(
        db,
        project_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    total = result["total"]
    result.update(
        {
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
            "pass_rate": result["passed_count"] / total if total else 0,
        }
    )
    return result
