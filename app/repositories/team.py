from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload
from app.models.team import Team
from app.models.project import Project
from app.models.team_member import TeamMember
from app.models.user import User


def db_get(db: Session, team_id: int, user_id: int) -> TeamMember | None:
    return db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()


def db_list_for_user(db: Session, user_id: int) -> list[Team]:
    rows = db.query(Team, TeamMember.role).join(TeamMember, TeamMember.team_id == Team.id).filter(TeamMember.user_id == user_id).order_by(Team.created_at.desc()).all()
    teams = []
    for team, role in rows:
        team.role = role
        teams.append(team)
    return teams


def db_create(db: Session, team: Team, owner_id: int) -> Team:
    db.add(team); db.flush(); db.add(TeamMember(team_id=team.id, user_id=owner_id, role="owner")); db.commit(); db.refresh(team); return team


def db_list_members(db: Session, team_id: int) -> list[TeamMember]:
    return db.query(TeamMember).options(joinedload(TeamMember.user)).filter(TeamMember.team_id == team_id).order_by(TeamMember.created_at.asc(), TeamMember.id.asc()).all()


def db_get_member_by_id(db: Session, team_id: int, member_id: int) -> TeamMember | None:
    return db.query(TeamMember).options(joinedload(TeamMember.user)).filter(TeamMember.team_id == team_id, TeamMember.id == member_id).first()


def db_candidates(db: Session, team_id: int, keyword: str, limit: int) -> list[User]:
    return db.query(User).outerjoin(TeamMember, and_(TeamMember.user_id == User.id, TeamMember.team_id == team_id)).filter(TeamMember.id.is_(None), User.username.ilike(f"%{keyword}%")).order_by(User.username.asc(), User.id.asc()).limit(limit).all()

def db_get_team(db: Session, team_id: int) -> Team | None:
    return db.query(Team).filter(Team.id == team_id).first()

def db_project_count(db: Session, team_id: int) -> int:
    return db.query(Project).filter(Project.team_id == team_id).count()
