-- ========================================================================
-- 001_add_test_suite.sql
-- 测试套件结构迁移（MySQL 8）
--
-- 幂等保证：
--   1. 表使用 CREATE TABLE IF NOT EXISTS。
--   2. 字段、索引、外键在执行前查询 information_schema。
--   3. 不写死 USE 数据库名；连接到主库或影子库均可执行同一脚本。
--
-- 应分别对 DATABASE_URL 和 SHADOW_DATABASE_URL 指向的数据库执行。
-- 应用启动时 app.core.bootstrap.ensure_test_suite_schema 也会对两套库补齐
-- 同样的结构，避免旧数据卷只升级主库。
-- ========================================================================

SET @schema_name = DATABASE();

CREATE TABLE IF NOT EXISTS test_suite (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    project_id INT NOT NULL,
    type VARCHAR(20) NOT NULL COMMENT 'scenario/case/mixed',
    scenario_ids JSON COMMENT '场景ID列表',
    case_ids JSON COMMENT '用例ID列表',
    tags JSON COMMENT '标签列表',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_test_suite_project FOREIGN KEY (project_id) REFERENCES project(id),
    INDEX idx_test_suite_project (project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- schedule.suite_id
SET @ddl = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = @schema_name
          AND TABLE_NAME = 'schedule'
          AND COLUMN_NAME = 'suite_id'
    ),
    'SELECT 1',
    'ALTER TABLE `schedule` ADD COLUMN `suite_id` INT NULL COMMENT ''关联测试套件ID'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = @schema_name
          AND TABLE_NAME = 'schedule'
          AND COLUMN_NAME = 'suite_id'
          AND SEQ_IN_INDEX = 1
    ),
    'SELECT 1',
    'CREATE INDEX `idx_schedule_suite` ON `schedule` (`suite_id`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE CONSTRAINT_SCHEMA = @schema_name
          AND TABLE_NAME = 'schedule'
          AND COLUMN_NAME = 'suite_id'
          AND REFERENCED_TABLE_NAME = 'test_suite'
          AND REFERENCED_COLUMN_NAME = 'id'
    ),
    'SELECT 1',
    'ALTER TABLE `schedule` ADD CONSTRAINT `fk_schedule_suite` FOREIGN KEY (`suite_id`) REFERENCES `test_suite` (`id`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- test_report.suite_id / suite_name / execution_type
SET @ddl = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = @schema_name
          AND TABLE_NAME = 'test_report'
          AND COLUMN_NAME = 'suite_id'
    ),
    'SELECT 1',
    'ALTER TABLE `test_report` ADD COLUMN `suite_id` INT NULL COMMENT ''关联测试套件ID'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = @schema_name
          AND TABLE_NAME = 'test_report'
          AND COLUMN_NAME = 'suite_name'
    ),
    'SELECT 1',
    'ALTER TABLE `test_report` ADD COLUMN `suite_name` VARCHAR(100) NULL COMMENT ''套件名称快照'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = @schema_name
          AND TABLE_NAME = 'test_report'
          AND COLUMN_NAME = 'execution_type'
    ),
    'SELECT 1',
    'ALTER TABLE `test_report` ADD COLUMN `execution_type` VARCHAR(20) NULL COMMENT ''suite/scenario/case/regression'''
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = @schema_name
          AND TABLE_NAME = 'test_report'
          AND COLUMN_NAME = 'suite_id'
          AND SEQ_IN_INDEX = 1
    ),
    'SELECT 1',
    'CREATE INDEX `idx_report_suite` ON `test_report` (`suite_id`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE CONSTRAINT_SCHEMA = @schema_name
          AND TABLE_NAME = 'test_report'
          AND COLUMN_NAME = 'suite_id'
          AND REFERENCED_TABLE_NAME = 'test_suite'
          AND REFERENCED_COLUMN_NAME = 'id'
    ),
    'SELECT 1',
    'ALTER TABLE `test_report` ADD CONSTRAINT `fk_report_suite` FOREIGN KEY (`suite_id`) REFERENCES `test_suite` (`id`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
