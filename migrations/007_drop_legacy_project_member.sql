-- 007_drop_legacy_project_member.sql
-- 最终移除旧 ProjectMember 数据。必须先成功执行 005，避免绕过数据校验。

DELIMITER //

DROP PROCEDURE IF EXISTS migrate_007_drop_legacy_project_member//

CREATE PROCEDURE migrate_007_drop_legacy_project_member()
BEGIN
    DECLARE current_table_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO current_table_exists
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'project_member';

    IF current_table_exists > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'project_member 尚未通过 005 安全迁移，拒绝直接清理';
    END IF;

    DROP TABLE IF EXISTS project_member_legacy;

    CREATE TABLE IF NOT EXISTS schema_migration (
        version VARCHAR(100) PRIMARY KEY,
        applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    INSERT IGNORE INTO schema_migration (version)
    VALUES ('007_drop_legacy_project_member');
END//

CALL migrate_007_drop_legacy_project_member()//
DROP PROCEDURE migrate_007_drop_legacy_project_member//

DELIMITER ;
