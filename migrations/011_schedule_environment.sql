-- Run separately against the platform main and shadow databases.
-- Existing jobs keep NULL; edit them to select an environment. Never guess a URL.
DELIMITER //
DROP PROCEDURE IF EXISTS migrate_011_schedule_environment//
CREATE PROCEDURE migrate_011_schedule_environment()
BEGIN
    DECLARE table_exists INT DEFAULT 0;
    DECLARE column_exists INT DEFAULT 0;
    DECLARE foreign_key_exists INT DEFAULT 0;
    SELECT COUNT(*) INTO table_exists FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'schedule';
    IF table_exists > 0 THEN
        SELECT COUNT(*) INTO column_exists FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'schedule' AND COLUMN_NAME = 'env_id';
        IF column_exists = 0 THEN
            ALTER TABLE schedule ADD COLUMN env_id INTEGER NULL;
        END IF;
        SELECT COUNT(*) INTO foreign_key_exists FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'schedule'
          AND COLUMN_NAME = 'env_id' AND REFERENCED_TABLE_NAME = 'environment';
        IF foreign_key_exists = 0 THEN
            ALTER TABLE schedule ADD CONSTRAINT fk_schedule_environment
            FOREIGN KEY (env_id) REFERENCES environment(id) ON DELETE RESTRICT;
        END IF;
    END IF;
    CREATE TABLE IF NOT EXISTS schema_migration (
        version VARCHAR(100) PRIMARY KEY,
        applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    INSERT IGNORE INTO schema_migration(version) VALUES ('011_schedule_environment');
END//
CALL migrate_011_schedule_environment()//
DROP PROCEDURE migrate_011_schedule_environment//
DELIMITER ;
