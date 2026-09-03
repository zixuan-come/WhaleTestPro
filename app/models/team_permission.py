from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint
from app.database import Base

class TeamPermission(Base):
    __tablename__ = 'team_permission'
    __table_args__ = (UniqueConstraint('team_id', 'role', 'permission', name='uq_team_permission'),)
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey('team.id', ondelete='CASCADE'), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    permission = Column(String(50), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False, server_default='0')
