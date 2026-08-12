from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from app.models.project_member import ProjectMember
from app.models.user import User


def db_get(db: Session, project_id: int, user_id: int) -> ProjectMember | None:
    return (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        .first()
    )


def db_create(
    db: Session,
    project_id: int,
    user_id: int,
    role: str,
) -> ProjectMember:
    membership = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role=role,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def db_get_by_id_for_project(
    db: Session,
    project_id: int,
    member_id: int,
) -> ProjectMember | None:
    return (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .filter(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
        )
        .first()
    )


def db_update_role(
    db: Session,
    membership: ProjectMember,
    role: str,
) -> ProjectMember:
    membership.role = role
    db.commit()
    db.refresh(membership)
    return membership


def db_delete(
    db: Session,
    membership: ProjectMember,
) -> None:
    db.delete(membership)
    db.commit()


def db_list_candidates(
    db: Session,
    project_id: int,
    keyword: str,
    limit: int,
) -> list[User]:
    return (
        db.query(User)
        .outerjoin(
            ProjectMember,
            and_(
                ProjectMember.user_id == User.id,
                ProjectMember.project_id == project_id,
            ),
        )
        .filter(
            ProjectMember.id.is_(None),
            User.username.ilike(f"%{keyword}%"),
        )
        .order_by(User.username.asc(), User.id.asc())
        .limit(limit)
        .all()
    )


def db_list_by_project(
    db: Session,
    project_id: int,
) -> list[ProjectMember]:
    return (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .filter(ProjectMember.project_id == project_id)
        .order_by(
            ProjectMember.created_at.asc(),
            ProjectMember.id.asc(),
        )
        .all()
    )
