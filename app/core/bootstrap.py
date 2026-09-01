from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User


def ensure_team_schema(db: Session) -> None:
    """Create team tables via metadata and add team_id to legacy project tables."""
    bind = db.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("project")}
    if "team_id" not in columns:
        dialect = bind.dialect.name
        if dialect == "sqlite":
            db.execute(text("ALTER TABLE project ADD COLUMN team_id INTEGER"))
        else:
            db.execute(text("ALTER TABLE project ADD COLUMN team_id INT NULL"))
        db.commit()


def _highest_role(current: str | None, incoming: str) -> str:
    rank = {TeamRole.MEMBER.value: 1, TeamRole.ADMIN.value: 2, TeamRole.OWNER.value: 3}
    return incoming if current is None or rank[incoming] > rank[current] else current


def backfill_teams(db: Session) -> int:
    """Migrate old project memberships into one team per legacy project."""
    ensure_team_schema(db)
    fallback_owner = db.query(User).order_by(User.id.asc()).first()
    if fallback_owner is None:
        return 0

    migrated = 0
    projects = db.query(Project).all()
    for project in projects:
        owner_membership = (
            db.query(ProjectMember)
            .filter(ProjectMember.project_id == project.id, ProjectMember.role == ProjectRole.OWNER.value)
            .order_by(ProjectMember.id.asc())
            .first()
        )
        owner_id = owner_membership.user_id if owner_membership else fallback_owner.id
        if owner_membership is None:
            db.add(ProjectMember(project_id=project.id, user_id=owner_id, role=ProjectRole.OWNER.value))

        if project.team_id is None:
            team = db.query(Team).filter(Team.name == f"{project.name}团队").first()
            if team is None:
                team = Team(name=f"{project.name}团队", description=f"{project.name}的协作团队", owner_id=owner_id)
                db.add(team)
                db.flush()
            project.team_id = team.id
            migrated += 1
        else:
            team = db.query(Team).filter(Team.id == project.team_id).first()
            if team is None:
                continue

        memberships = db.query(ProjectMember).filter(ProjectMember.project_id == project.id).all()
        for membership in memberships:
            role = membership.role if membership.role in {"owner", "admin", "member"} else "member"
            tm = db.query(TeamMember).filter(TeamMember.team_id == team.id, TeamMember.user_id == membership.user_id).first()
            if tm is None:
                db.add(TeamMember(team_id=team.id, user_id=membership.user_id, role=role))
            else:
                tm.role = _highest_role(tm.role, role)
        db.flush()
        if not db.query(TeamMember).filter(TeamMember.team_id == team.id, TeamMember.user_id == owner_id).first():
            db.add(TeamMember(team_id=team.id, user_id=owner_id, role=TeamRole.OWNER.value))

    db.commit()
    return migrated


# Backward-compatible name used by the app bootstrap.
def backfill_legacy_project_owners(db: Session) -> int:
    return backfill_teams(db)
