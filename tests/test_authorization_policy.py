from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.authorization import authorize, is_allowed, resolve_project_context
from app.core.permissions import Action, Resource
from app.database import Base
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.team_permission import TeamPermission
from app.models.user import User
from app.repositories import project as project_repo
import app.models.suite  # noqa: F401  注册 test_report.suite_id 的外键目标表


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _team_project(db):
    owner = User(username="auth-owner", hashed_password="x")
    admin = User(username="auth-admin", hashed_password="x")
    member = User(username="auth-member", hashed_password="x")
    outsider = User(username="auth-outsider", hashed_password="x")
    db.add_all([owner, admin, member, outsider])
    db.flush()
    team = Team(name="auth-team", owner_id=owner.id)
    db.add(team)
    db.flush()
    project = Project(name="auth-project", team_id=team.id)
    db.add(project)
    db.flush()
    db.add_all([
        TeamMember(team_id=team.id, user_id=owner.id, role="owner"),
        TeamMember(team_id=team.id, user_id=admin.id, role="admin"),
        TeamMember(team_id=team.id, user_id=member.id, role="member"),
    ])
    db.commit()
    return project, team, owner, admin, member, outsider


def test_role_matrix_uses_explicit_actions():
    db = _db()
    project, _, owner, admin, member, _ = _team_project(db)
    owner_context = resolve_project_context(db, project.id, owner)
    admin_context = resolve_project_context(db, project.id, admin)
    member_context = resolve_project_context(db, project.id, member)

    assert all(is_allowed(owner_context, Resource.PROJECT, action) for action in Action)
    assert is_allowed(admin_context, Resource.PROJECT_MEMBER, Action.MANAGE)
    assert is_allowed(admin_context, Resource.SUITE, Action.WRITE)
    assert not is_allowed(admin_context, Resource.PROJECT, Action.OWNER)
    assert is_allowed(member_context, Resource.SUITE, Action.READ)
    assert is_allowed(member_context, Resource.SUITE, Action.EXECUTE)
    assert not is_allowed(member_context, Resource.SUITE, Action.WRITE)
    assert not is_allowed(member_context, Resource.PROJECT_MEMBER, Action.MANAGE)


def test_member_write_permission_is_scoped_to_resource():
    db = _db()
    project, team, _, _, member, _ = _team_project(db)
    db.add(TeamPermission(team_id=team.id, role="member", permission="suite.write", enabled=True))
    db.commit()

    context = resolve_project_context(db, project.id, member)

    assert is_allowed(context, Resource.SUITE, Action.WRITE)
    assert not is_allowed(context, Resource.CASE, Action.WRITE)


def test_legacy_owner_cannot_elevate_team_member_role():
    db = _db()
    project, _, _, _, member, _ = _team_project(db)
    db.add(ProjectMember(project_id=project.id, user_id=member.id, role="owner"))
    db.commit()

    context = resolve_project_context(db, project.id, member)

    assert context.role == "member"
    assert context.legacy_membership.role == "owner"
    assert not is_allowed(context, Resource.PROJECT, Action.OWNER)
    assert not is_allowed(context, Resource.PROJECT_MEMBER, Action.MANAGE)


def test_legacy_membership_alone_cannot_access_team_project():
    db = _db()
    project, _, _, _, _, outsider = _team_project(db)
    db.add(ProjectMember(project_id=project.id, user_id=outsider.id, role="owner"))
    db.commit()

    assert resolve_project_context(db, project.id, outsider) is None
    assert project_repo.db_get_for_user(db, project.id, outsider.id) is None
    assert project_repo.db_list_for_user(db, outsider.id) == []


def test_team_membership_works_without_legacy_projection():
    db = _db()
    project, _, _, _, member, _ = _team_project(db)

    context = resolve_project_context(db, project.id, member)

    assert context is not None
    assert context.legacy_membership is None
    assert project_repo.db_get_for_user(db, project.id, member.id).id == project.id


def test_teamless_legacy_project_remains_compatible():
    db = _db()
    user = User(username="legacy-admin", hashed_password="x")
    db.add(user)
    db.flush()
    project = Project(name="legacy-project", team_id=None)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="admin"))
    db.commit()

    context = resolve_project_context(db, project.id, user)

    assert context.team_membership is None
    assert context.role == "admin"
    assert is_allowed(context, Resource.CASE, Action.WRITE)
    assert not is_allowed(context, Resource.PROJECT, Action.OWNER)


def test_authorize_dependency_rejects_denied_action():
    db = _db()
    project, _, _, _, member, _ = _team_project(db)
    context = resolve_project_context(db, project.id, member)
    dependency = authorize(Resource.SUITE, Action.WRITE)

    with pytest.raises(HTTPException) as exc_info:
        dependency(context)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "无权执行 suite.write 操作"
