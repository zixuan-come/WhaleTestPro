-- ========================================================================
-- 004_limit_username_length.sql
-- 将 users.username 从 VARCHAR(50) 收紧为 VARCHAR(20)，与注册规则保持一致。
--
-- 使用方式：分别连接主库和影子库执行本脚本。
-- 执行前先检查历史数据；若查询结果不为 0，必须先处理超长用户名，
-- 不允许依赖数据库自动截断。
-- 应用启动时 app.core.bootstrap.ensure_user_schema 也会对两套库执行同等检查。
-- ========================================================================

DROP PROCEDURE IF EXISTS migrate_username_length;

DELIMITER //
CREATE PROCEDURE migrate_username_length()
BEGIN
    DECLARE over_limit_count BIGINT DEFAULT 0;
    DECLARE current_length BIGINT DEFAULT NULL;
    DECLARE current_nullable VARCHAR(3) DEFAULT NULL;
    DECLARE error_message VARCHAR(128);

    SELECT COUNT(*)
    INTO over_limit_count
    FROM `users`
    WHERE CHAR_LENGTH(`username`) > 20;

    IF over_limit_count > 0 THEN
        SET error_message = CONCAT(
            'username migration blocked: ',
            over_limit_count,
            ' rows exceed 20 characters'
        );
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = error_message;
    END IF;

    SELECT CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
    INTO current_length, current_nullable
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'users'
      AND COLUMN_NAME = 'username';

    IF current_length <> 20 OR current_nullable <> 'NO' THEN
        ALTER TABLE `users`
            MODIFY COLUMN `username` VARCHAR(20) NOT NULL;
    END IF;
END//
DELIMITER ;

CALL migrate_username_length();
DROP PROCEDURE migrate_username_length;
