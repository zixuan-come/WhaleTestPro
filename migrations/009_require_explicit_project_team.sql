-- Project creation now requires an explicit team_id.
-- Existing teams and projects are preserved; only the obsolete provenance flag is removed.

SET @team_auto_column_exists = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'team'
      AND COLUMN_NAME = 'is_auto_created'
);

SET @drop_team_auto_column_sql = IF(
    @team_auto_column_exists > 0,
    'ALTER TABLE `team` DROP COLUMN `is_auto_created`',
    'SELECT 1'
);

PREPARE drop_team_auto_column_stmt FROM @drop_team_auto_column_sql;
EXECUTE drop_team_auto_column_stmt;
DEALLOCATE PREPARE drop_team_auto_column_stmt;

CREATE TABLE IF NOT EXISTS `schema_migration` (
    `version` VARCHAR(100) PRIMARY KEY,
    `applied_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO `schema_migration` (`version`)
VALUES ('009_require_explicit_project_team');
