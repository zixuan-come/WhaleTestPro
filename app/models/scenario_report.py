from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class ScenarioReport(Base):
    __tablename__ = "scenario_report"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, nullable=False, index=True)
    scenario_name = Column(String(100), nullable=False)
    passed = Column(Boolean, nullable=False)
    total_steps = Column(Integer, nullable=False)
    passed_steps = Column(Integer, nullable=False)
    failed_steps = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False, index=True)

    steps = relationship(
        "ScenarioReportStep",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ScenarioReportStep.sequence",
    )


class ScenarioReportStep(Base):
    __tablename__ = "scenario_report_step"
    __table_args__ = (
        UniqueConstraint("report_id", "sequence", name="uq_scenario_report_step_sequence"),
    )

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(
        Integer,
        ForeignKey("scenario_report.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence = Column(Integer, nullable=False)
    case_id = Column(Integer, nullable=False)
    case_name = Column(String(100), nullable=True)
    passed = Column(Boolean, nullable=False)
    request_detail = Column(JSON, nullable=True)
    response_detail = Column(JSON, nullable=True)
    assertions = Column(JSON, nullable=True)
    extracted_variables = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=False)

    report = relationship("ScenarioReport", back_populates="steps")
