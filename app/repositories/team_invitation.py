from sqlalchemy.orm import Session, joinedload

from app.models.team_invitation import TeamInvitation


def db_page_for_invitee(
    db: Session,
    invitee_id: int,
    *,
    invitation_status: str | None,
    offset: int,
    limit: int,
) -> tuple[list[TeamInvitation], int]:
    query = db.query(TeamInvitation).filter(
        TeamInvitation.invitee_id == invitee_id
    )
    if invitation_status is not None:
        query = query.filter(TeamInvitation.status == invitation_status)

    total = query.count()
    items = (
        query.options(
            joinedload(TeamInvitation.inviter),
            joinedload(TeamInvitation.invitee),
        )
        .order_by(TeamInvitation.created_at.desc(), TeamInvitation.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items, total
