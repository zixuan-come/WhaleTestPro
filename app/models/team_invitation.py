from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.database import Base

class TeamInvitation(Base):
    __tablename__ = 'team_invitation'
    __table_args__ = (UniqueConstraint('team_id', 'invitee_id', 'status', name='uq_team_invite_active'),)
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey('team.id', ondelete='CASCADE'), nullable=False, index=True)
    inviter_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    invitee_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role = Column(String(20), nullable=False, default='member', server_default='member')
    status = Column(String(20), nullable=False, default='pending', server_default='pending', index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    responded_at = Column(DateTime, nullable=True)
    team = relationship('Team', back_populates='invitations')
    invitee = relationship('User', foreign_keys=[invitee_id])
    inviter = relationship('User', foreign_keys=[inviter_id])
