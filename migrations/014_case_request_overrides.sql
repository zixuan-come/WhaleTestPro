-- Additive, repeatable migration. Old cases retain inherited request settings.
DELIMITER //
DROP PROCEDURE IF EXISTS migrate_014_case_request_overrides//
CREATE PROCEDURE migrate_014_case_request_overrides()
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='test_case') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
                       AND TABLE_NAME='test_case' AND COLUMN_NAME='request_overrides') THEN
            ALTER TABLE test_case ADD COLUMN request_overrides JSON NULL;
        END IF;
        CREATE TABLE IF NOT EXISTS schema_migration (
            version VARCHAR(100) PRIMARY KEY,
            applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        INSERT IGNORE INTO schema_migration(version) VALUES ('014_case_request_overrides');
    END IF;
END//
CALL migrate_014_case_request_overrides()//
DROP PROCEDURE migrate_014_case_request_overrides//
DELIMITER ;
