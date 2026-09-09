from fastapi import HTTPException
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.permissions import TEAM_PERMISSION_KEYS, WRITE_PERMISSION_BY_RESOURCE, Resource
from app.database import Base
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.models.team_permission import TeamPermission
from app.models.user import User
from app.routers.team import create_team
from app.schemas.team import TeamCreate, TeamPermissionUpdate
from app.services import project as project_service
from app.services import team as team_service
import app.models.suite  # noqa: F401  注册 test_report.suite_id 的外键目标表


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_invitation_accept_adds_team_and_project_membership():
    db = _db()
    owner = User(username="owner", hashed_password="x")
    invitee = User(username="invitee", hashed_password="x")
    db.add_all([owner, invitee])
    db.flush()
    team = Team(name="team", owner_id=owner.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=owner.id, role=TeamRole.OWNER.value))
    project = Project(name="project", team_id=team.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    db.commit()

    invite = team_service.s_invite(db, team.id, owner.id, invitee.id, "member")
    result = team_service.s_respond_invitation(db, invite.id, invitee.id, True)

    assert result.status == "accepted"
    assert db.query(TeamMember).filter_by(team_id=team.id, user_id=invitee.id).one().role == "member"
    assert db.query(ProjectMember).filter_by(project_id=project.id, user_id=invitee.id).one().role == "member"


def test_move_project_to_target_owner_team_syncs_members():
    db = _db()
    owner = User(username="owner2", hashed_password="x")
    target_owner = User(username="target", hashed_password="x")
    db.add_all([owner, target_owner])
    db.flush()
    source = Team(name="source", owner_id=owner.id)
    target = Team(name="target-team", owner_id=target_owner.id)
    db.add_all([source, target])
    db.flush()
    db.add_all([
        TeamMember(team_id=source.id, user_id=owner.id, role="owner"),
        TeamMember(team_id=target.id, user_id=target_owner.id, role="owner"),
    ])
    project = Project(name="movable", team_id=source.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    db.commit()

    moved = project_service.s_move_team(db, project.id, target.id, target_owner.id)

    assert moved.team_id == target.id
    assert db.query(ProjectMember).filter_by(project_id=project.id, user_id=target_owner.id).one().role == "owner"
    assert db.query(ProjectMember).filter_by(project_id=project.id, user_id=owner.id).first() is None


def test_member_content_write_permission_can_be_enabled():
    db = _db()
    owner = User(username="owner3", hashed_password="x")
    db.add(owner)
    db.flush()
    team = Team(name="permission-team", owner_id=owner.id)
    db.add(team)
    db.flush()

    item = team_service.s_set_permission(db, team.id, "member", "suite.write", True)

    assert item.enabled is True
    assert db.query(TeamPermission).filter_by(team_id=team.id, permission="suite.write").one().enabled is True


def test_create_team_sets_owner_and_owner_membership():
    db = _db()
    owner = User(username="create-owner", hashed_password="x")
    db.add(owner)
    db.flush()

    team = team_service.s_create(db, TeamCreate(name="created-team"), owner.id)

    assert team.owner_id == owner.id
    assert db.query(TeamMember).filter_by(team_id=team.id, user_id=owner.id, role="owner").one()


def test_duplicate_team_name_returns_conflict():
    db = _db()
    owner = User(username="duplicate-owner", hashed_password="x")
    db.add(owner)
    db.flush()
    data = TeamCreate(name="duplicate-team")

    create_team(data, db, owner)
    with pytest.raises(HTTPException) as exc_info:
        create_team(data, db, owner)

    assert exc_info.value.status_code == 409
    assert "duplicate-team" in exc_info.value.detail


def test_permission_keys_are_canonical_and_include_suite():
    assert "suite.write" in TEAM_PERMISSION_KEYS
    assert WRITE_PERMISSION_BY_RESOURCE[Resource.SUITE] == "suite.write"
    assert TeamPermissionUpdate(permission="suite.write", enabled=True).permission == "suite.write"
    with pytest.raises(ValidationError):
        TeamPermissionUpdate(permission="content.write", enabled=True)
    with pytest.raises(ValidationError):
        TeamPermissionUpdate(role="admin", permission="suite.write", enabled=True)
