from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from app.database import Base


class ReportFolder(Base):
    __tablename__ = "report_folder"
    __table_args__ = (UniqueConstraint("project_id", "name_key", name="uq_report_folder_project_name"),)
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    name_key = Column(String(300), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class ReportFolderItem(Base):
    """One optional folder for each top-level report, including legacy storage."""
    __tablename__ = "report_folder_item"
    __table_args__ = (UniqueConstraint("project_id", "storage", "report_id", name="uq_report_folder_item_report"),)
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id = Column(Integer, ForeignKey("report_folder.id", ondelete="CASCADE"), nullable=False, index=True)
    storage = Column(String(20), nullable=False)
    report_id = Column(Integer, nullable=False)
