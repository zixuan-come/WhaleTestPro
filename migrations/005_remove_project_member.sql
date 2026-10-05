-- ========================================================================
-- 005_remove_project_member.sql
-- 团队权限统一收尾迁移（MySQL 8，可重复执行）
--
-- 安全顺序：先校验数据，再补索引、外键和 NOT NULL，最后归档旧表。
-- 应分别对主库和影子库执行。生产部署由 scripts/run_migrations.py 完成；
-- 本文件保留给人工审阅与手动迁移。
-- ========================================================================

DELIMITER //

DROP PROCEDURE IF EXISTS migrate_005_remove_project_member//

CREATE PROCEDURE migrate_005_remove_project_member()
migration: BEGIN
    DECLARE project_exists INT DEFAULT 0;
    DECLARE project_member_exists INT DEFAULT 0;
    DECLARE legacy_archive_exists INT DEFAULT 0;
    DECLARE blocker_count INT DEFAULT 0;

    SELECT COUNT(*) INTO project_exists
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'project';

    -- 全新数据库尚未建表时无需执行；模型建表会直接创建正确结构。
    IF project_exists = 0 THEN
        LEAVE migration;
    END IF;

    IF NOT EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'project'
          AND COLUMN_NAME = 'team_id'
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'project.team_id 不存在，请先执行团队数据回填';
    END IF;

    IF NOT EXISTS(
        SELECT 1 FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'team'
    ) OR NOT EXISTS(
        SELECT 1 FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'team_member'
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'team 或 team_member 表不存在，请先执行团队数据回填';
    END IF;

    SELECT COUNT(*) INTO blocker_count FROM project WHERE team_id IS NULL;
    IF blocker_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = '仍有项目未关联团队，迁移已安全终止';
    END IF;

    SELECT COUNT(*) INTO blocker_count
    FROM project p
    LEFT JOIN team t ON t.id = p.team_id
    WHERE t.id IS NULL;
    IF blocker_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = '仍有项目关联了不存在的团队，迁移已安全终止';
    END IF;

    SELECT COUNT(*) INTO blocker_count
    FROM team t
    LEFT JOIN team_member tm
      ON tm.team_id = t.id
     AND tm.user_id = t.owner_id
     AND tm.role = 'owner'
    WHERE tm.id IS NULL;
    IF blocker_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = '仍有团队缺少 owner 成员关系，迁移已安全终止';
    END IF;

    SELECT COUNT(*) INTO blocker_count
    FROM (
        SELECT team_id
        FROM team_member
        WHERE role = 'owner'
        GROUP BY team_id
        HAVING COUNT(*) > 1
    ) owner_conflicts;
    IF blocker_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = '仍有团队存在多个 owner，迁移已安全终止';
    END IF;

    SELECT COUNT(*) INTO project_member_exists
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'project_member';

    SELECT COUNT(*) INTO legacy_archive_exists
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'project_member_legacy';

    IF project_member_exists > 0 AND legacy_archive_exists > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = '旧表与归档表同时存在，请人工确认后重试';
    END IF;

    IF project_member_exists > 0 THEN
        SELECT COUNT(*) INTO blocker_count
        FROM project_member pm
        JOIN project p ON p.id = pm.project_id
        LEFT JOIN team_member tm
          ON tm.team_id = p.team_id
         AND tm.user_id = pm.user_id
        WHERE tm.id IS NULL;

        IF blocker_count > 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = '仍有项目成员关系未迁移，迁移已安全终止';
        END IF;
    END IF;

    IF NOT EXISTS(
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'project'
          AND COLUMN_NAME = 'team_id'
          AND SEQ_IN_INDEX = 1
    ) THEN
        CREATE INDEX idx_project_team_id ON project(team_id);
    END IF;

    IF NOT EXISTS(
        SELECT 1 FROM information_schema.KEY_COLUMN_USAGE
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'project'
          AND COLUMN_NAME = 'team_id'
          AND REFERENCED_TABLE_NAME = 'team'
          AND REFERENCED_COLUMN_NAME = 'id'
    ) THEN
        ALTER TABLE project
            ADD CONSTRAINT fk_project_team
            FOREIGN KEY (team_id) REFERENCES team(id)
            ON DELETE RESTRICT;
    END IF;

    IF EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'project'
          AND COLUMN_NAME = 'team_id'
          AND IS_NULLABLE = 'YES'
    ) THEN
        ALTER TABLE project MODIFY COLUMN team_id INT NOT NULL;
    END IF;

    -- 所有可能失败的数据校验和结构变更均已完成，最后才归档旧表。
    IF project_member_exists > 0 THEN
        RENAME TABLE project_member TO project_member_legacy;
    END IF;

    CREATE TABLE IF NOT EXISTS schema_migration (
        version VARCHAR(100) PRIMARY KEY,
        applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    INSERT IGNORE INTO schema_migration(version)
    VALUES ('005_remove_project_member');
END//

CALL migrate_005_remove_project_member()//
DROP PROCEDURE migrate_005_remove_project_member//

DELIMITER ;
