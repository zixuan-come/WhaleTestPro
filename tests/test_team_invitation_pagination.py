from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.team import Team
from app.models.team_invitation import TeamInvitation
from app.models.user import User
from app.services import team as team_service
import app.models.suite  # noqa: F401  注册所有外键目标表


def test_invitation_page_is_filtered_paginated_and_preloads_users():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    owner = User(username="invite-owner", hashed_password="x")
    invitee = User(username="invite-target", hashed_password="x")
    db.add_all([owner, invitee])
    db.flush()
    teams = [Team(name=f"invite-team-{index}", owner_id=owner.id) for index in range(4)]
    db.add_all(teams)
    db.flush()
    db.add_all(
        [
            TeamInvitation(
                team_id=team.id,
                inviter_id=owner.id,
                invitee_id=invitee.id,
                status="pending" if index < 3 else "accepted",
            )
            for index, team in enumerate(teams)
        ]
    )
    db.commit()
    invitee_id = invitee.id
    db.expunge_all()

    selects = []

    def record_select(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", record_select)
    result = team_service.s_list_invitations(
        db,
        invitee_id,
        page=1,
        page_size=2,
        invitation_status="pending",
    )

    assert result["total"] == 3
    assert result["total_pages"] == 2
    assert len(result["items"]) == 2
    assert len(selects) == 2  # 一次 count + 一次带 inviter/invitee 的分页查询

    before_relationship_access = len(selects)
    assert all(item.inviter.username == "invite-owner" for item in result["items"])
    assert all(item.invitee.username == "invite-target" for item in result["items"])
    assert len(selects) == before_relationship_access
