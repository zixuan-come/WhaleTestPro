from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False, unique=True)
    hashed_password = Column(String(200), nullable=False)
    project_memberships = relationship(
        "ProjectMember", back_populates="user", cascade="all, delete-orphan", passive_deletes=True,
    )
    team_memberships = relationship(
        "TeamMember", back_populates="user", cascade="all, delete-orphan", passive_deletes=True,
        foreign_keys="TeamMember.user_id",
    )
