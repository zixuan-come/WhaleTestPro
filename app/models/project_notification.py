from sqlalchemy import Boolean, Column, ForeignKey, Integer, Text
from app.database import Base


class ProjectNotification(Base):
    __tablename__ = "project_notification"
    project_id = Column(Integer, ForeignKey("project.id", ondelete="CASCADE"), primary_key=True)
    feishu_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    webhook_ciphertext = Column(Text, nullable=True)
    signing_secret_ciphertext = Column(Text, nullable=True)
