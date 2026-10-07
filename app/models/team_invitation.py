from datetime import datetime
from sqlalchemy import (
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship
from app.database import Base

class TeamInvitation(Base):
    __tablename__ = 'team_invitation'
    __table_args__ = (
        UniqueConstraint(
            'team_id',
            'pending_invitee_id',
            name='uq_team_invitation_pending',
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey('team.id', ondelete='CASCADE'), nullable=False, index=True)
    inviter_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    invitee_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role = Column(String(20), nullable=False, default='member', server_default='member')
    status = Column(String(20), nullable=False, default='pending', server_default='pending', index=True)
    # 只有 pending 行会生成 invitee_id；已处理记录生成 NULL。唯一约束允许保留
    # 多条 accepted/rejected 历史，同时从数据库层阻止并发创建重复待处理邀请。
    pending_invitee_id = Column(
        Integer,
        Computed(
            "CASE WHEN status = 'pending' THEN invitee_id ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    responded_at = Column(DateTime, nullable=True)
    team = relationship('Team', back_populates='invitations')
    invitee = relationship('User', foreign_keys=[invitee_id])
    inviter = relationship('User', foreign_keys=[inviter_id])
