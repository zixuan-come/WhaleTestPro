from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.migrations import _validate_project_team_data


ROOT = Path(__file__).resolve().parents[1]


def _legacy_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE team (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL)"))
        connection.execute(
            text(
                "CREATE TABLE team_member ("
                "id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, role VARCHAR(20) NOT NULL)"
            )
        )
        connection.execute(
            text("CREATE TABLE project (id INTEGER PRIMARY KEY, team_id INTEGER NULL)")
        )
        connection.execute(
            text(
                "CREATE TABLE project_member ("
                "id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, role VARCHAR(20) NOT NULL)"
            )
        )
    return engine


def test_project_team_migration_rejects_unassigned_project_before_archive():
    engine = _legacy_engine()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO team VALUES (1, 10)"))
        connection.execute(text("INSERT INTO team_member VALUES (1, 1, 10, 'owner')"))
        connection.execute(text("INSERT INTO project VALUES (1, NULL)"))

    with engine.connect() as connection, pytest.raises(RuntimeError, match="未关联团队"):
        _validate_project_team_data(connection)


def test_project_team_migration_rejects_unmigrated_membership():
    engine = _legacy_engine()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO team VALUES (1, 10)"))
        connection.execute(text("INSERT INTO team_member VALUES (1, 1, 10, 'owner')"))
        connection.execute(text("INSERT INTO project VALUES (1, 1)"))
        connection.execute(text("INSERT INTO project_member VALUES (1, 1, 20, 'member')"))

    with engine.connect() as connection, pytest.raises(RuntimeError, match="未迁移"):
        _validate_project_team_data(connection)


def test_project_team_migration_rejects_multiple_owners():
    engine = _legacy_engine()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO team VALUES (1, 10)"))
        connection.execute(text("INSERT INTO team_member VALUES (1, 1, 10, 'owner')"))
        connection.execute(text("INSERT INTO team_member VALUES (2, 1, 20, 'owner')"))
        connection.execute(text("INSERT INTO project VALUES (1, 1)"))

    with engine.connect() as connection, pytest.raises(RuntimeError, match="多个 owner"):
        _validate_project_team_data(connection)


def test_migration_and_deploy_keep_safe_order():
    migration = (ROOT / "migrations" / "005_remove_project_member.sql").read_text(
        encoding="utf-8"
    )
    deploy = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS `project_member`" not in migration
    assert migration.index("WHERE team_id IS NULL") < migration.index(
        "RENAME TABLE project_member TO project_member_legacy"
    )
    assert deploy.index("python -m scripts.run_migrations") < deploy.index(
        "docker compose up -d --remove-orphans"
    )


def test_final_cleanup_only_drops_the_validated_legacy_table():
    migration = (
        ROOT / "migrations" / "007_drop_legacy_project_member.sql"
    ).read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS project_member_legacy" in migration
    assert "DROP TABLE IF EXISTS project_member;" not in migration
    assert migration.index("SIGNAL SQLSTATE") < migration.index(
        "DROP TABLE IF EXISTS project_member_legacy"
    )


def test_team_invitation_migration_replaces_history_blocking_constraint():
    migration = (
        ROOT / "migrations" / "008_team_invitation_consistency.sql"
    ).read_text(encoding="utf-8")

    assert "GENERATED ALWAYS AS" in migration
    assert "CASE WHEN status = 'pending' THEN invitee_id ELSE NULL END" in migration
    assert "CREATE UNIQUE INDEX uq_team_invitation_pending" in migration
    assert migration.index("CREATE UNIQUE INDEX uq_team_invitation_pending") < migration.index(
        "ALTER TABLE team_invitation DROP INDEX uq_team_invite_active"
    )


def test_explicit_project_team_migration_only_drops_obsolete_marker():
    migration = (
        ROOT / "migrations" / "009_require_explicit_project_team.sql"
    ).read_text(encoding="utf-8")

    assert "information_schema.COLUMNS" in migration
    assert "DROP COLUMN `is_auto_created`" in migration
    assert "DROP TABLE" not in migration
    assert "DELETE FROM" not in migration


def test_runtime_migrations_run_in_order(monkeypatch):
    from app.core import migrations

    calls = []
    monkeypatch.setattr(
        migrations,
        "ensure_project_team_schema",
        lambda bind: calls.append((bind, "005")),
    )
    monkeypatch.setattr(
        migrations,
        "ensure_operational_consistency_schema",
        lambda bind: calls.append((bind, "006")),
    )
    monkeypatch.setattr(
        migrations,
        "ensure_legacy_project_member_removed",
        lambda bind: calls.append((bind, "007")),
    )
    monkeypatch.setattr(
        migrations,
        "ensure_team_invitation_consistency_schema",
        lambda bind: calls.append((bind, "008")),
    )
    monkeypatch.setattr(
        migrations,
        "ensure_explicit_project_team_schema",
        lambda bind: calls.append((bind, "009")),
    )
    monkeypatch.setattr(
        migrations,
        "ensure_perf_task_lifecycle_schema",
        lambda bind: calls.append((bind, "010")),
    )

    migrations.run_all_migrations("main", "shadow")

    assert calls == [
        ("main", "005"),
        ("main", "006"),
        ("main", "007"),
        ("main", "008"),
        ("main", "009"),
        ("main", "010"),
        ("shadow", "005"),
        ("shadow", "006"),
        ("shadow", "007"),
        ("shadow", "008"),
        ("shadow", "009"),
        ("shadow", "010"),
    ]
