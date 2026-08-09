from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.user import User


def backfill_legacy_project_owners(db: Session) -> int:
    fallback_owner = db.query(User).order_by(User.id.asc()).first()
    if fallback_owner is None:
        return 0

    orphan_projects = (
        db.query(Project)
        .outerjoin(
            ProjectMember,
            ProjectMember.project_id == Project.id,
        )
        .filter(ProjectMember.id.is_(None))
        .all()
    )

    for project in orphan_projects:
        db.add(
            ProjectMember(
                project_id=project.id,
                user_id=fallback_owner.id,
                role=ProjectRole.OWNER.value,
            )
        )

    db.commit()
    return len(orphan_projects)