-- 008_team_invitation_consistency.sql
-- 只约束 pending 邀请唯一；accepted/rejected 历史记录允许重复保留。

DELIMITER //

DROP PROCEDURE IF EXISTS migrate_008_team_invitation_consistency//

CREATE PROCEDURE migrate_008_team_invitation_consistency()
BEGIN
    DECLARE table_exists INT DEFAULT 0;
    DECLARE column_exists INT DEFAULT 0;
    DECLARE new_index_exists INT DEFAULT 0;
    DECLARE old_index_exists INT DEFAULT 0;
    DECLARE duplicate_pending INT DEFAULT 0;

    SELECT COUNT(*) INTO table_exists
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'team_invitation';

    IF table_exists > 0 THEN
        SELECT COUNT(*) INTO column_exists
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'team_invitation'
          AND COLUMN_NAME = 'pending_invitee_id';

        IF column_exists = 0 THEN
            ALTER TABLE team_invitation
                ADD COLUMN pending_invitee_id INT
                GENERATED ALWAYS AS (
                    CASE WHEN status = 'pending' THEN invitee_id ELSE NULL END
                ) STORED;
        END IF;

        SELECT COUNT(*) INTO duplicate_pending
        FROM (
            SELECT team_id, invitee_id
            FROM team_invitation
            WHERE status = 'pending'
            GROUP BY team_id, invitee_id
            HAVING COUNT(*) > 1
        ) duplicate_rows;

        IF duplicate_pending > 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = '存在重复待处理团队邀请，拒绝添加唯一索引';
        END IF;

        SELECT COUNT(*) INTO new_index_exists
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'team_invitation'
          AND INDEX_NAME = 'uq_team_invitation_pending';

        IF new_index_exists = 0 THEN
            CREATE UNIQUE INDEX uq_team_invitation_pending
                ON team_invitation (team_id, pending_invitee_id);
        END IF;

        SELECT COUNT(*) INTO old_index_exists
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'team_invitation'
          AND INDEX_NAME = 'uq_team_invite_active';

        IF old_index_exists > 0 THEN
            ALTER TABLE team_invitation DROP INDEX uq_team_invite_active;
        END IF;
    END IF;

    CREATE TABLE IF NOT EXISTS schema_migration (
        version VARCHAR(100) PRIMARY KEY,
        applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    INSERT IGNORE INTO schema_migration (version)
    VALUES ('008_team_invitation_consistency');
END//

CALL migrate_008_team_invitation_consistency()//
DROP PROCEDURE migrate_008_team_invitation_consistency//

DELIMITER ;
