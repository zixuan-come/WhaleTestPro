-- Additive, repeatable MySQL 8 migration. No task data is backfilled/deleted.
DELIMITER //
DROP PROCEDURE IF EXISTS migrate_012_perf_load_plan//
CREATE PROCEDURE migrate_012_perf_load_plan()
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='perf_tasks') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
                       AND TABLE_NAME='perf_tasks' AND COLUMN_NAME='load_config') THEN
            ALTER TABLE perf_tasks ADD COLUMN load_config JSON NULL;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
                       AND TABLE_NAME='perf_tasks' AND COLUMN_NAME='iteration_stats') THEN
            ALTER TABLE perf_tasks ADD COLUMN iteration_stats JSON NULL;
        END IF;
        CREATE TABLE IF NOT EXISTS schema_migration (
            version VARCHAR(100) PRIMARY KEY,
            applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        INSERT IGNORE INTO schema_migration(version) VALUES ('012_perf_load_plan');
    END IF;
END//
CALL migrate_012_perf_load_plan()//
DROP PROCEDURE migrate_012_perf_load_plan//
DELIMITER ;
