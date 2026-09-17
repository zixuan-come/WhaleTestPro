from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.suite import TestSuite
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User


PERF_SCHEMA_COLUMNS = {
    "p95_response_ms": "FLOAT NULL",
    "p99_response_ms": "FLOAT NULL",
    "request_stats": "JSON NULL",
    "error_summary": "JSON NULL",
    "history_samples": "JSON NULL",
}

TEST_SUITE_SCHEMA_COLUMNS = {
    "schedule": {
        "suite_id": "INTEGER NULL",
    },
    "test_report": {
        "suite_id": "INTEGER NULL",
        "suite_name": "VARCHAR(100) NULL",
        "execution_type": "VARCHAR(20) NULL",
    },
}

TEST_SUITE_SCHEMA_INDEXES = {
    "schedule": ("idx_schedule_suite", "suite_id"),
    "test_report": ("idx_report_suite", "suite_id"),
}

TEST_SUITE_SCHEMA_FOREIGN_KEYS = {
    "schedule": ("fk_schedule_suite", "suite_id"),
    "test_report": ("fk_report_suite", "suite_id"),
}


def _has_single_column_index(inspector, table_name: str, column_name: str) -> bool:
    return any(index.get("column_names") == [column_name] for index in inspector.get_indexes(table_name))


def _has_test_suite_foreign_key(inspector, table_name: str, column_name: str) -> bool:
    return any(
        foreign_key.get("constrained_columns") == [column_name]
        and foreign_key.get("referred_table") == "test_suite"
        and foreign_key.get("referred_columns") == ["id"]
        for foreign_key in inspector.get_foreign_keys(table_name)
    )


def ensure_test_suite_schema(bind) -> None:
    """Idempotently upgrade legacy databases for test suites."""
    TestSuite.__table__.create(bind=bind, checkfirst=True)
    preparer = bind.dialect.identifier_preparer

    with bind.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in TEST_SUITE_SCHEMA_COLUMNS.items():
            if not inspector.has_table(table_name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            quoted_table = preparer.quote(table_name)
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    quoted_column = preparer.quote(column_name)
                    connection.execute(
                        text(f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {column_type}")
                    )

    with bind.begin() as connection:
        inspector = inspect(connection)
        for table_name, (index_name, column_name) in TEST_SUITE_SCHEMA_INDEXES.items():
            if not inspector.has_table(table_name):
                continue
            if not _has_single_column_index(inspector, table_name, column_name):
                connection.execute(
                    text(
                        f"CREATE INDEX {preparer.quote(index_name)} "
                        f"ON {preparer.quote(table_name)} ({preparer.quote(column_name)})"
                    )
                )

    if bind.dialect.name != "mysql":
        return

    with bind.begin() as connection:
        inspector = inspect(connection)
        for table_name, (constraint_name, column_name) in TEST_SUITE_SCHEMA_FOREIGN_KEYS.items():
            if not inspector.has_table(table_name):
                continue
            if not _has_test_suite_foreign_key(inspector, table_name, column_name):
                connection.execute(
                    text(
                        f"ALTER TABLE {preparer.quote(table_name)} "
                        f"ADD CONSTRAINT {preparer.quote(constraint_name)} "
                        f"FOREIGN KEY ({preparer.quote(column_name)}) "
                        "REFERENCES test_suite (id)"
                    )
                )


def ensure_perf_schema(db: Session) -> None:
    """为已有数据库补齐压测观测字段，避免 create_all 升级时漏列。"""
    bind = db.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("perf_tasks"):
        return
    existing = {column["name"] for column in inspector.get_columns("perf_tasks")}
    missing = [name for name in PERF_SCHEMA_COLUMNS if name not in existing]
    for name in missing:
        db.execute(text(f"ALTER TABLE perf_tasks ADD COLUMN {name} {PERF_SCHEMA_COLUMNS[name]}"))
    if missing:
        db.commit()


def ensure_team_schema(db: Session) -> None:
    """Create team tables via metadata and add team_id to legacy project tables."""
    bind = db.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("project")}
    if "team_id" not in columns:
        dialect = bind.dialect.name
        if dialect == "sqlite":
            db.execute(text("ALTER TABLE project ADD COLUMN team_id INTEGER"))
        else:
            db.execute(text("ALTER TABLE project ADD COLUMN team_id INT NULL"))
        db.commit()


def _highest_role(current: str | None, incoming: str) -> str:
    rank = {TeamRole.MEMBER.value: 1, TeamRole.ADMIN.value: 2, TeamRole.OWNER.value: 3}
    return incoming if current is None or rank[incoming] > rank[current] else current


def backfill_teams(db: Session) -> int:
    """Migrate old project memberships into one team per legacy project."""
    ensure_team_schema(db)
    fallback_owner = db.query(User).order_by(User.id.asc()).first()
    if fallback_owner is None:
        return 0

    migrated = 0
    projects = db.query(Project).all()
    for project in projects:
        owner_membership = (
            db.query(ProjectMember)
            .filter(ProjectMember.project_id == project.id, ProjectMember.role == ProjectRole.OWNER.value)
            .order_by(ProjectMember.id.asc())
            .first()
        )
        owner_id = owner_membership.user_id if owner_membership else fallback_owner.id
        if owner_membership is None:
            db.add(ProjectMember(project_id=project.id, user_id=owner_id, role=ProjectRole.OWNER.value))

        if project.team_id is None:
            team = db.query(Team).filter(Team.name == f"{project.name}团队").first()
            if team is None:
                team = Team(name=f"{project.name}团队", description=f"{project.name}的协作团队", owner_id=owner_id)
                db.add(team)
                db.flush()
            project.team_id = team.id
            migrated += 1
        else:
            team = db.query(Team).filter(Team.id == project.team_id).first()
            if team is None:
                continue

        memberships = db.query(ProjectMember).filter(ProjectMember.project_id == project.id).all()
        for membership in memberships:
            role = membership.role if membership.role in {"owner", "admin", "member"} else "member"
            tm = db.query(TeamMember).filter(TeamMember.team_id == team.id, TeamMember.user_id == membership.user_id).first()
            if tm is None:
                db.add(TeamMember(team_id=team.id, user_id=membership.user_id, role=role))
            else:
                tm.role = _highest_role(tm.role, role)
        db.flush()
        if not db.query(TeamMember).filter(TeamMember.team_id == team.id, TeamMember.user_id == owner_id).first():
            db.add(TeamMember(team_id=team.id, user_id=owner_id, role=TeamRole.OWNER.value))

    db.commit()
    return migrated


# Backward-compatible name used by the app bootstrap.
def backfill_legacy_project_owners(db: Session) -> int:
    ensure_perf_schema(db)
    return backfill_teams(db)
