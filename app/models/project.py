from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from app.database import Base


class Project(Base):
    __tablename__ = "project"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    team_id = Column(Integer, ForeignKey("team.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    members = relationship(
        "ProjectMember", back_populates="project", cascade="all, delete-orphan", passive_deletes=True,
    )
    team = relationship("Team", back_populates="projects")
