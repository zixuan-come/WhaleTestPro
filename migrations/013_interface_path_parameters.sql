-- Additive and repeatable; existing interface data remains unchanged.
DELIMITER //
DROP PROCEDURE IF EXISTS migrate_013_interface_path_parameters//
CREATE PROCEDURE migrate_013_interface_path_parameters()
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='interface') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
                       AND TABLE_NAME='interface' AND COLUMN_NAME='path_params') THEN
            ALTER TABLE interface ADD COLUMN path_params JSON NULL;
        END IF;
        CREATE TABLE IF NOT EXISTS schema_migration (
            version VARCHAR(100) PRIMARY KEY,
            applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        INSERT IGNORE INTO schema_migration(version) VALUES ('013_interface_path_parameters');
    END IF;
END//
CALL migrate_013_interface_path_parameters()//
DROP PROCEDURE migrate_013_interface_path_parameters//
DELIMITER ;
