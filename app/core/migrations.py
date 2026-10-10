from sqlalchemy import inspect, text

from app.models.schedule_sync_outbox import ScheduleSyncOutbox


PROJECT_TEAM_MIGRATION = "005_remove_project_member"
OPERATIONAL_CONSISTENCY_MIGRATION = "006_operational_consistency"
LEGACY_PROJECT_MEMBER_CLEANUP_MIGRATION = "007_drop_legacy_project_member"
TEAM_INVITATION_CONSISTENCY_MIGRATION = "008_team_invitation_consistency"
EXPLICIT_PROJECT_TEAM_MIGRATION = "009_require_explicit_project_team"
PERF_TASK_LIFECYCLE_MIGRATION = "010_perf_task_lifecycle"

PERF_TASK_LIFECYCLE_COLUMNS = {
    "celery_task_id": "VARCHAR(255) NULL",
    "queued_at": "DATETIME NULL",
    "started_at": "DATETIME NULL",
    "heartbeat_at": "DATETIME NULL",
    "finished_at": "DATETIME NULL",
    "failure_reason": "VARCHAR(500) NULL",
}

PERF_TASK_LIFECYCLE_INDEXES = {
    "ix_perf_tasks_celery_task_id": "celery_task_id",
    "ix_perf_tasks_heartbeat_at": "heartbeat_at",
}


def _has_project_team_foreign_key(inspector) -> bool:
    return any(
        foreign_key.get("constrained_columns") == ["team_id"]
        and foreign_key.get("referred_table") == "team"
        and foreign_key.get("referred_columns") == ["id"]
        for foreign_key in inspector.get_foreign_keys("project")
    )


def _has_team_id_index(inspector) -> bool:
    return any(
        index.get("column_names")
        and index["column_names"][0] == "team_id"
        for index in inspector.get_indexes("project")
    )


def _validate_project_team_data(connection) -> None:
    inspector = inspect(connection)
    if not inspector.has_table("project"):
        return

    columns = {column["name"] for column in inspector.get_columns("project")}
    if "team_id" not in columns:
        raise RuntimeError("project.team_id 不存在，请先执行团队数据回填")
    if not inspector.has_table("team") or not inspector.has_table("team_member"):
        raise RuntimeError("team 或 team_member 表不存在，请先执行团队数据回填")

    null_projects = connection.execute(
        text("SELECT COUNT(*) FROM project WHERE team_id IS NULL")
    ).scalar_one()
    if null_projects:
        raise RuntimeError(
            f"仍有 {null_projects} 个项目未关联团队，拒绝归档 project_member"
        )

    orphan_projects = connection.execute(
        text(
            "SELECT COUNT(*) FROM project p "
            "LEFT JOIN team t ON t.id = p.team_id "
            "WHERE t.id IS NULL"
        )
    ).scalar_one()
    if orphan_projects:
        raise RuntimeError(
            f"仍有 {orphan_projects} 个项目关联了不存在的团队，拒绝继续迁移"
        )

    invalid_owners = connection.execute(
        text(
            "SELECT COUNT(*) FROM team t "
            "LEFT JOIN team_member tm "
            "ON tm.team_id = t.id AND tm.user_id = t.owner_id AND tm.role = 'owner' "
            "WHERE tm.id IS NULL"
        )
    ).scalar_one()
    if invalid_owners:
        raise RuntimeError(
            f"仍有 {invalid_owners} 个团队缺少与 owner_id 对应的 owner 成员，拒绝继续迁移"
        )

    multiple_owners = connection.execute(
        text(
            "SELECT COUNT(*) FROM ("
            "SELECT team_id FROM team_member WHERE role = 'owner' "
            "GROUP BY team_id HAVING COUNT(*) > 1"
            ") owner_conflicts"
        )
    ).scalar_one()
    if multiple_owners:
        raise RuntimeError(
            f"仍有 {multiple_owners} 个团队存在多个 owner，拒绝继续迁移"
        )

    if inspector.has_table("project_member"):
        missing_memberships = connection.execute(
            text(
                "SELECT COUNT(*) FROM project_member pm "
                "JOIN project p ON p.id = pm.project_id "
                "LEFT JOIN team_member tm "
                "ON tm.team_id = p.team_id AND tm.user_id = pm.user_id "
                "WHERE tm.id IS NULL"
            )
        ).scalar_one()
        if missing_memberships:
            raise RuntimeError(
                f"仍有 {missing_memberships} 条项目成员关系未迁移到 team_member，"
                "拒绝归档 project_member"
            )


def ensure_project_team_schema(bind) -> None:
    """Safely finish migration 005 for one MySQL database.

    The legacy membership table is archived only after all data checks and
    schema changes have succeeded. Repeated execution is safe.
    """
    if bind.dialect.name != "mysql":
        return

    with bind.connect() as connection:
        _validate_project_team_data(connection)
        inspector = inspect(connection)
        if not inspector.has_table("project"):
            return
        if inspector.has_table("project_member") and inspector.has_table(
            "project_member_legacy"
        ):
            raise RuntimeError(
                "project_member 与 project_member_legacy 同时存在，"
                "请人工确认后再继续迁移"
            )

    preparer = bind.dialect.identifier_preparer

    with bind.begin() as connection:
        inspector = inspect(connection)
        if not _has_team_id_index(inspector):
            connection.execute(
                text("CREATE INDEX `idx_project_team_id` ON `project` (`team_id`)")
            )

    with bind.begin() as connection:
        inspector = inspect(connection)
        if not _has_project_team_foreign_key(inspector):
            connection.execute(
                text(
                    "ALTER TABLE `project` "
                    "ADD CONSTRAINT `fk_project_team` "
                    "FOREIGN KEY (`team_id`) REFERENCES `team` (`id`) "
                    "ON DELETE RESTRICT"
                )
            )

    with bind.begin() as connection:
        inspector = inspect(connection)
        team_id_column = next(
            column
            for column in inspector.get_columns("project")
            if column["name"] == "team_id"
        )
        if team_id_column.get("nullable", True):
            connection.execute(
                text("ALTER TABLE `project` MODIFY COLUMN `team_id` INT NOT NULL")
            )

    with bind.begin() as connection:
        inspector = inspect(connection)
        if inspector.has_table("project_member"):
            connection.execute(
                text(
                    f"RENAME TABLE {preparer.quote('project_member')} "
                    f"TO {preparer.quote('project_member_legacy')}"
                )
            )

        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS `schema_migration` ("
                "`version` VARCHAR(100) PRIMARY KEY, "
                "`applied_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
        )
        connection.execute(
            text(
                "INSERT IGNORE INTO `schema_migration` (`version`) "
                "VALUES (:version)"
            ),
            {"version": PROJECT_TEAM_MIGRATION},
        )


def _record_migration(connection, version: str) -> None:
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS `schema_migration` ("
            "`version` VARCHAR(100) PRIMARY KEY, "
            "`applied_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
    )
    connection.execute(
        text(
            "INSERT IGNORE INTO `schema_migration` (`version`) "
            "VALUES (:version)"
        ),
        {"version": version},
    )


def ensure_operational_consistency_schema(bind) -> None:
    """Add persistent schedule synchronization."""
    if bind.dialect.name != "mysql":
        return

    outbox_existed = inspect(bind).has_table("schedule_sync_outbox")
    ScheduleSyncOutbox.__table__.create(bind=bind, checkfirst=True)
    schedule_needs_backfill = not outbox_existed
    schedule_table_exists = False

    with bind.begin() as connection:
        inspector = inspect(connection)
        if inspector.has_table("schedule"):
            schedule_table_exists = True
            columns = {
                column["name"]
                for column in inspector.get_columns("schedule")
            }
            if "sync_status" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE `schedule` ADD COLUMN `sync_status` "
                        "VARCHAR(20) NOT NULL DEFAULT 'pending'"
                    )
                )
                schedule_needs_backfill = True
            if "sync_error" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE `schedule` ADD COLUMN `sync_error` "
                        "VARCHAR(500) NULL"
                    )
                )

    if schedule_needs_backfill and schedule_table_exists:
        with bind.begin() as connection:
            schedule_columns = {
                column["name"]
                for column in inspect(connection).get_columns("schedule")
            }
            suite_value = "`suite_id`" if "suite_id" in schedule_columns else "NULL"
            connection.execute(
                text(
                    "INSERT INTO `schedule_sync_outbox` "
                    "(`schedule_id`, `action`, `payload`, `attempts`) "
                    "SELECT `id`, 'sync', JSON_OBJECT("
                    "'id', `id`, 'project_id', `project_id`, "
                    "'cron', `cron`, 'tag', `tag`, "
                    f"'suite_id', {suite_value}, 'enabled', `enabled`"
                    "), 0 FROM `schedule` "
                    "ON DUPLICATE KEY UPDATE "
                    "`action` = VALUES(`action`), "
                    "`payload` = VALUES(`payload`), "
                    "`attempts` = 0, `last_error` = NULL"
                )
            )

    with bind.begin() as connection:
        _record_migration(connection, OPERATIONAL_CONSISTENCY_MIGRATION)


def ensure_legacy_project_member_removed(bind) -> None:
    """Permanently remove the archived project membership table after 005."""
    if bind.dialect.name != "mysql":
        return

    with bind.begin() as connection:
        inspector = inspect(connection)
        if inspector.has_table("project_member"):
            raise RuntimeError(
                "project_member 尚未通过 005 安全迁移，请勿直接执行最终清理"
            )
        if inspector.has_table("project_member_legacy"):
            connection.execute(text("DROP TABLE `project_member_legacy`"))
        _record_migration(connection, LEGACY_PROJECT_MEMBER_CLEANUP_MIGRATION)


def _has_named_index(inspector, table_name: str, index_name: str) -> bool:
    indexes = {
        item.get("name")
        for item in inspector.get_indexes(table_name)
    }
    unique_constraints = {
        item.get("name")
        for item in inspector.get_unique_constraints(table_name)
    }
    return index_name in indexes or index_name in unique_constraints


def ensure_team_invitation_consistency_schema(bind) -> None:
    """Keep only pending invitations unique while preserving status history."""
    if bind.dialect.name != "mysql":
        return

    with bind.begin() as connection:
        inspector = inspect(connection)
        if not inspector.has_table("team_invitation"):
            _record_migration(connection, TEAM_INVITATION_CONSISTENCY_MIGRATION)
            return

        columns = {
            column["name"]
            for column in inspector.get_columns("team_invitation")
        }
        if "pending_invitee_id" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE `team_invitation` ADD COLUMN "
                    "`pending_invitee_id` INT GENERATED ALWAYS AS ("
                    "CASE WHEN `status` = 'pending' THEN `invitee_id` ELSE NULL END"
                    ") STORED"
                )
            )

    with bind.begin() as connection:
        duplicate_pending = connection.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "SELECT `team_id`, `invitee_id` FROM `team_invitation` "
                "WHERE `status` = 'pending' GROUP BY `team_id`, `invitee_id` "
                "HAVING COUNT(*) > 1"
                ") duplicate_pending"
            )
        ).scalar_one()
        if duplicate_pending:
            raise RuntimeError(
                f"存在 {duplicate_pending} 组重复待处理团队邀请，拒绝添加唯一索引"
            )

        inspector = inspect(connection)
        if not _has_named_index(
            inspector,
            "team_invitation",
            "uq_team_invitation_pending",
        ):
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX `uq_team_invitation_pending` "
                    "ON `team_invitation` (`team_id`, `pending_invitee_id`)"
                )
            )

    with bind.begin() as connection:
        inspector = inspect(connection)
        if _has_named_index(
            inspector,
            "team_invitation",
            "uq_team_invite_active",
        ):
            connection.execute(
                text(
                    "ALTER TABLE `team_invitation` "
                    "DROP INDEX `uq_team_invite_active`"
                )
            )
        _record_migration(connection, TEAM_INVITATION_CONSISTENCY_MIGRATION)


def ensure_explicit_project_team_schema(bind) -> None:
    """Remove the obsolete auto-team marker after project team becomes required."""
    if bind.dialect.name != "mysql":
        return

    with bind.begin() as connection:
        inspector = inspect(connection)
        if inspector.has_table("team"):
            team_columns = {
                column["name"]
                for column in inspector.get_columns("team")
            }
            if "is_auto_created" in team_columns:
                connection.execute(
                    text("ALTER TABLE `team` DROP COLUMN `is_auto_created`")
                )
        _record_migration(connection, EXPLICIT_PROJECT_TEAM_MIGRATION)


def ensure_perf_task_lifecycle_schema(bind) -> None:
    """Add durable Celery correlation and Worker heartbeat fields."""
    preparer = bind.dialect.identifier_preparer
    with bind.begin() as connection:
        inspector = inspect(connection)
        if not inspector.has_table("perf_tasks"):
            if bind.dialect.name == "mysql":
                _record_migration(connection, PERF_TASK_LIFECYCLE_MIGRATION)
            return

        existing_columns = {
            column["name"]
            for column in inspector.get_columns("perf_tasks")
        }
        for column_name, column_type in PERF_TASK_LIFECYCLE_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE {preparer.quote('perf_tasks')} "
                        f"ADD COLUMN {preparer.quote(column_name)} {column_type}"
                    )
                )

    with bind.begin() as connection:
        inspector = inspect(connection)
        existing_indexes = {
            index.get("name")
            for index in inspector.get_indexes("perf_tasks")
        }
        for index_name, column_name in PERF_TASK_LIFECYCLE_INDEXES.items():
            if index_name not in existing_indexes:
                connection.execute(
                    text(
                        f"CREATE INDEX {preparer.quote(index_name)} "
                        f"ON {preparer.quote('perf_tasks')} "
                        f"({preparer.quote(column_name)})"
                    )
                )
        if bind.dialect.name == "mysql":
            _record_migration(connection, PERF_TASK_LIFECYCLE_MIGRATION)


def run_all_migrations(*binds) -> None:
    for bind in binds:
        ensure_project_team_schema(bind)
        ensure_operational_consistency_schema(bind)
        ensure_legacy_project_member_removed(bind)
        ensure_team_invitation_consistency_schema(bind)
        ensure_explicit_project_team_schema(bind)
        ensure_perf_task_lifecycle_schema(bind)
        ensure_schedule_environment_schema(bind)


def ensure_schedule_environment_schema(bind) -> None:
    """Add nullable environment linkage without inventing a target for old jobs."""
    with bind.begin() as connection:
        inspector = inspect(connection)
        if not inspector.has_table("schedule"):
            return
        columns = {column["name"] for column in inspector.get_columns("schedule")}
        if "env_id" not in columns:
            connection.execute(text("ALTER TABLE schedule ADD COLUMN env_id INTEGER NULL"))
        if bind.dialect.name == "mysql":
            inspector = inspect(connection)
            if not any(fk.get("constrained_columns") == ["env_id"] for fk in inspector.get_foreign_keys("schedule")):
                connection.execute(text(
                    "ALTER TABLE schedule ADD CONSTRAINT fk_schedule_environment "
                    "FOREIGN KEY (env_id) REFERENCES environment(id) ON DELETE RESTRICT"
                ))
            _record_migration(connection, "011_schedule_environment")
