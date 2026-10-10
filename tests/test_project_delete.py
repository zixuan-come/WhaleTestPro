from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.case import Case
from app.models.environment import Environment
from app.models.interface import Interface
from app.models.mock import Mock
from app.models.perf import PerfTask
from app.models.project import Project
from app.models.report import TestReport as ReportModel
from app.models.scenario import Scenario
from app.models.scenario_report import ScenarioReport, ScenarioReportStep
from app.models.schedule import Schedule
from app.models.traffic_record import TrafficRecord
from app.models.suite import TestSuite
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User
from app.repositories.project import db_delete


def _new_session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_delete_project_removes_all_project_resources():
    db = _new_session()
    try:
        user = User(username="owner", hashed_password="hashed")
        db.add(user)
        db.flush()
        team = Team(name="delete-team", owner_id=user.id)
        db.add(team)
        db.flush()
        member = TeamMember(
            team_id=team.id,
            user_id=user.id,
            role=TeamRole.OWNER.value,
        )
        project = Project(name="project-to-delete", team_id=team.id)
        db.add_all([member, project])
        db.flush()
        suite = TestSuite(
            name="full regression",
            project_id=project.id,
            type="mixed",
        )
        db.add(suite)
        db.flush()
        interface = Interface(
            name="health",
            method="GET",
            url="/health",
            project_id=project.id,
        )
        db.add_all([member, interface])
        db.flush()

        environment = Environment(name="local", base_url="http://app", project_id=project.id)
        db.add(environment)
        db.flush()

        case = Case(
            name="health case",
            interface_id=interface.id,
            expected_status=200,
            project_id=project.id,
        )
        scenario_report = ScenarioReport(
            scenario_id=1,
            scenario_name="health scenario",
            passed=True,
            total_steps=1,
            passed_steps=1,
            failed_steps=0,
            duration_ms=1,
            created_at=datetime.now(),
            project_id=project.id,
        )
        db.add_all(
            [
                case,
                Mock(name="health mock", path="/health", method="GET", status=200, project_id=project.id),
                PerfTask(
                    name="health perf",
                    target_host="http://app",
                    target_path="/health",
                    users=1,
                    spawn_rate=1,
                    duration=1,
                    status="pending",
                    project_id=project.id,
                ),
                ReportModel(
                    case_id=1,
                    passed=True,
                    suite_id=suite.id,
                    project_id=project.id,
                ),
                Scenario(name="health scenario", case_ids=[], project_id=project.id),
                scenario_report,
                Schedule(
                    name="daily",
                    cron="0 0 * * *",
                    suite_id=suite.id,
                    env_id=environment.id,
                    enabled=True,
                    project_id=project.id,
                ),
                TrafficRecord(method="GET", path="/health", project_id=project.id),
            ]
        )
        db.flush()
        db.add(
            ScenarioReportStep(
                report_id=scenario_report.id,
                sequence=1,
                case_id=case.id,
                case_name=case.name,
                passed=True,
                duration_ms=1,
            )
        )
        db.commit()
        project_id = project.id

        deleted = db_delete(db, project_id)

        assert deleted is not None
        assert deleted.id == project_id
        assert db.query(Project).filter(Project.id == project_id).first() is None
        for model in (
            Case,
            Interface,
            Environment,
            Mock,
            PerfTask,
            ReportModel,
            ScenarioReportStep,
            ScenarioReport,
            Scenario,
            Schedule,
            TrafficRecord,
            TestSuite,
        ):
            assert db.query(model).count() == 0
        assert db.query(User).count() == 1
        assert db.query(Team).count() == 1
        assert db.query(TeamMember).count() == 1
    finally:
        db.close()
