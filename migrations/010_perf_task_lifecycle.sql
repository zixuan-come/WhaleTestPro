-- 010_perf_task_lifecycle.sql
-- 为压测任务增加 queued/running 生命周期、Worker 心跳和 Celery task id 关联。

DELIMITER //

DROP PROCEDURE IF EXISTS migrate_010_perf_task_lifecycle//

CREATE PROCEDURE migrate_010_perf_task_lifecycle()
BEGIN
    DECLARE table_exists INT DEFAULT 0;
    DECLARE column_exists INT DEFAULT 0;
    DECLARE index_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO table_exists
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_tasks';

    IF table_exists > 0 THEN
        SELECT COUNT(*) INTO column_exists FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_tasks'
          AND COLUMN_NAME = 'celery_task_id';
        IF column_exists = 0 THEN
            ALTER TABLE perf_tasks ADD COLUMN celery_task_id VARCHAR(255) NULL;
        END IF;

        SELECT COUNT(*) INTO column_exists FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_tasks'
          AND COLUMN_NAME = 'queued_at';
        IF column_exists = 0 THEN
            ALTER TABLE perf_tasks ADD COLUMN queued_at DATETIME NULL;
        END IF;

        SELECT COUNT(*) INTO column_exists FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_tasks'
          AND COLUMN_NAME = 'started_at';
        IF column_exists = 0 THEN
            ALTER TABLE perf_tasks ADD COLUMN started_at DATETIME NULL;
        END IF;

        SELECT COUNT(*) INTO column_exists FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_tasks'
          AND COLUMN_NAME = 'heartbeat_at';
        IF column_exists = 0 THEN
            ALTER TABLE perf_tasks ADD COLUMN heartbeat_at DATETIME NULL;
        END IF;

        SELECT COUNT(*) INTO column_exists FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_tasks'
          AND COLUMN_NAME = 'finished_at';
        IF column_exists = 0 THEN
            ALTER TABLE perf_tasks ADD COLUMN finished_at DATETIME NULL;
        END IF;

        SELECT COUNT(*) INTO column_exists FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_tasks'
          AND COLUMN_NAME = 'failure_reason';
        IF column_exists = 0 THEN
            ALTER TABLE perf_tasks ADD COLUMN failure_reason VARCHAR(500) NULL;
        END IF;

        SELECT COUNT(*) INTO index_exists FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_tasks'
          AND INDEX_NAME = 'ix_perf_tasks_celery_task_id';
        IF index_exists = 0 THEN
            CREATE INDEX ix_perf_tasks_celery_task_id
                ON perf_tasks (celery_task_id);
        END IF;

        SELECT COUNT(*) INTO index_exists FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'perf_tasks'
          AND INDEX_NAME = 'ix_perf_tasks_heartbeat_at';
        IF index_exists = 0 THEN
            CREATE INDEX ix_perf_tasks_heartbeat_at
                ON perf_tasks (heartbeat_at);
        END IF;
    END IF;

    CREATE TABLE IF NOT EXISTS schema_migration (
        version VARCHAR(100) PRIMARY KEY,
        applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    INSERT IGNORE INTO schema_migration (version)
    VALUES ('010_perf_task_lifecycle');
END//

CALL migrate_010_perf_task_lifecycle()//
DROP PROCEDURE migrate_010_perf_task_lifecycle//

DELIMITER ;
