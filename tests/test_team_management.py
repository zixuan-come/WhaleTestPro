from fastapi import HTTPException
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.permissions import TEAM_PERMISSION_KEYS, WRITE_PERMISSION_BY_RESOURCE, Resource
from app.database import Base
from app.models.project import Project
from app.models.team import Team
from app.models.team_invitation import TeamInvitation
from app.models.team_member import TeamMember, TeamRole
from app.models.team_permission import TeamPermission
from app.models.user import User
from app.routers.team import create_team
from app.repositories import project as project_repo
from app.schemas.project import ProjectCreate
from app.schemas.team import TeamCreate, TeamPermissionUpdate
from app.services import project as project_service
from app.services import team as team_service
import app.models.suite  # noqa: F401  注册 test_report.suite_id 的外键目标表


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_invitation_accept_adds_team_membership():
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
    db.commit()

    invite = team_service.s_invite(db, team.id, owner.id, invitee.id, "member")
    result = team_service.s_respond_invitation(db, invite.id, invitee.id, True)

    assert result.status == "accepted"
    assert db.query(TeamMember).filter_by(team_id=team.id, user_id=invitee.id).one().role == "member"
    assert project_repo.db_get_for_user(db, project.id, invitee.id).id == project.id


def test_invitation_can_be_accepted_again_after_member_leaves():
    db = _db()
    owner = User(username="repeat-owner", hashed_password="x")
    invitee = User(username="repeat-invitee", hashed_password="x")
    db.add_all([owner, invitee])
    db.flush()
    team = Team(name="repeat-team", owner_id=owner.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=owner.id, role="owner"))
    db.commit()

    first = team_service.s_invite(db, team.id, owner.id, invitee.id, "member")
    team_service.s_respond_invitation(db, first.id, invitee.id, True)
    team_service.s_leave(db, team.id, invitee.id)

    second = team_service.s_invite(db, team.id, owner.id, invitee.id, "member")
    result = team_service.s_respond_invitation(db, second.id, invitee.id, True)

    assert result.status == "accepted"
    assert db.query(TeamInvitation).filter_by(
        team_id=team.id,
        invitee_id=invitee.id,
        status="accepted",
    ).count() == 2


def test_processed_invitation_returns_conflict():
    db = _db()
    owner = User(username="processed-owner", hashed_password="x")
    invitee = User(username="processed-invitee", hashed_password="x")
    db.add_all([owner, invitee])
    db.flush()
    team = Team(name="processed-team", owner_id=owner.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=owner.id, role="owner"))
    db.commit()

    invite = team_service.s_invite(db, team.id, owner.id, invitee.id, "member")
    team_service.s_respond_invitation(db, invite.id, invitee.id, False)

    with pytest.raises(HTTPException) as exc_info:
        team_service.s_respond_invitation(db, invite.id, invitee.id, False)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "邀请已经处理"


def test_concurrent_invitation_insert_returns_conflict_and_rolls_back(monkeypatch):
    class EmptyQuery:
        def filter(self, *_args):
            return self

        def first(self):
            return None

    class FailingDb:
        rolled_back = False

        def query(self, _model):
            return EmptyQuery()

        def add(self, _value):
            pass

        def commit(self):
            raise IntegrityError("insert", {}, Exception("duplicate"))

        def rollback(self):
            self.rolled_back = True

    db = FailingDb()
    monkeypatch.setattr(team_service.user_repo, "db_get_by_id", lambda *_: object())
    monkeypatch.setattr(team_service.team_repo, "db_get", lambda *_: None)

    with pytest.raises(HTTPException) as exc_info:
        team_service.s_invite(db, 1, 10, 20, "member")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "该用户已有待处理邀请"
    assert db.rolled_back is True


def test_invitation_response_integrity_conflict_is_409(monkeypatch):
    db = _db()
    owner = User(username="respond-owner", hashed_password="x")
    invitee = User(username="respond-invitee", hashed_password="x")
    db.add_all([owner, invitee])
    db.flush()
    team = Team(name="respond-team", owner_id=owner.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=owner.id, role="owner"))
    db.commit()
    invite = team_service.s_invite(db, team.id, owner.id, invitee.id, "member")

    def fail_commit():
        raise IntegrityError("update", {}, Exception("duplicate"))

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(HTTPException) as exc_info:
        team_service.s_respond_invitation(db, invite.id, invitee.id, True)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "邀请处理发生冲突，请重试"


def test_move_project_to_target_team_uses_team_membership():
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
    db.commit()

    moved = project_service.s_move_team(db, project.id, target.id, target_owner.id)

    assert moved.team_id == target.id
    assert project_repo.db_get_for_user(db, project.id, target_owner.id).id == project.id
    assert project_repo.db_get_for_user(db, project.id, owner.id) is None


def test_create_project_without_team_creates_owned_team():
    db = _db()
    owner = User(username="auto-team-owner", hashed_password="x")
    db.add(owner)
    db.commit()

    project = project_service.s_create(
        db,
        ProjectCreate(name="auto-team-project"),
        owner.id,
    )

    assert project.team_id is not None
    team = db.query(Team).filter(Team.id == project.team_id).one()
    assert team.owner_id == owner.id
    assert db.query(TeamMember).filter_by(
        team_id=team.id,
        user_id=owner.id,
        role=TeamRole.OWNER.value,
    ).one()


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


def test_transfer_owner_keeps_exactly_one_owner():
    db = _db()
    owner = User(username="transfer-owner", hashed_password="x")
    target = User(username="transfer-target", hashed_password="x")
    stale_owner = User(username="stale-owner", hashed_password="x")
    db.add_all([owner, target, stale_owner])
    db.flush()
    team = Team(name="transfer-team", owner_id=owner.id)
    db.add(team)
    db.flush()
    db.add_all(
        [
            TeamMember(team_id=team.id, user_id=owner.id, role="owner"),
            TeamMember(team_id=team.id, user_id=target.id, role="member"),
            TeamMember(team_id=team.id, user_id=stale_owner.id, role="owner"),
        ]
    )
    db.commit()

    result = team_service.s_transfer_owner(
        db,
        team.id,
        owner.id,
        target.id,
    )

    assert result.owner_id == target.id
    owners = db.query(TeamMember).filter_by(team_id=team.id, role="owner").all()
    assert [membership.user_id for membership in owners] == [target.id]
    assert db.query(TeamMember).filter_by(
        team_id=team.id,
        user_id=owner.id,
    ).one().role == "admin"


def test_transfer_owner_rejects_self_transfer():
    db = _db()
    owner = User(username="self-transfer-owner", hashed_password="x")
    db.add(owner)
    db.flush()
    team = Team(name="self-transfer-team", owner_id=owner.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=owner.id, role="owner"))
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        team_service.s_transfer_owner(db, team.id, owner.id, owner.id)

    assert exc_info.value.status_code == 409
    assert db.query(TeamMember).filter_by(team_id=team.id, role="owner").count() == 1


@pytest.mark.parametrize("operation", ["update", "remove", "leave"])
def test_owner_identity_cannot_be_changed_even_when_role_data_is_stale(operation):
    db = _db()
    owner = User(username=f"stale-{operation}-owner", hashed_password="x")
    db.add(owner)
    db.flush()
    team = Team(name=f"stale-{operation}-team", owner_id=owner.id)
    db.add(team)
    db.flush()
    membership = TeamMember(team_id=team.id, user_id=owner.id, role="member")
    db.add(membership)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        if operation == "update":
            team_service.s_update_role(db, team.id, membership.id, "admin")
        elif operation == "remove":
            team_service.s_remove(db, team.id, membership.id)
        else:
            team_service.s_leave(db, team.id, owner.id)

    assert exc_info.value.status_code == 409
    assert db.query(TeamMember).filter_by(team_id=team.id, user_id=owner.id).one()


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


def test_concurrent_member_insert_returns_conflict_and_rolls_back(monkeypatch):
    from types import SimpleNamespace

    class FailingDb:
        rolled_back = False

        def add(self, _value):
            pass

        def commit(self):
            raise IntegrityError("insert", {}, Exception("duplicate"))

        def rollback(self):
            self.rolled_back = True

    db = FailingDb()
    monkeypatch.setattr(team_service.user_repo, "db_get_by_id", lambda *_: object())
    monkeypatch.setattr(team_service.team_repo, "db_get", lambda *_: None)

    with pytest.raises(HTTPException) as exc_info:
        team_service.s_add(
            db,
            1,
            SimpleNamespace(user_id=2, role="member"),
        )

    assert exc_info.value.status_code == 409
    assert db.rolled_back is True


def test_permission_keys_are_canonical_and_include_suite():
    assert "suite.write" in TEAM_PERMISSION_KEYS
    assert WRITE_PERMISSION_BY_RESOURCE[Resource.SUITE] == "suite.write"
    assert TeamPermissionUpdate(permission="suite.write", enabled=True).permission == "suite.write"
    with pytest.raises(ValidationError):
        TeamPermissionUpdate(permission="content.write", enabled=True)
    with pytest.raises(ValidationError):
        TeamPermissionUpdate(role="admin", permission="suite.write", enabled=True)
