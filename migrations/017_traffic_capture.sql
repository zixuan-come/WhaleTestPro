-- Repeatable MySQL 8 migration; preserve all existing recordings.
CREATE TABLE IF NOT EXISTS traffic_capture (
  project_id INT NOT NULL, user_id INT NOT NULL, capture_id VARCHAR(36) NOT NULL,
  started_at DATETIME NOT NULL, expires_at DATETIME NOT NULL, stopped_at DATETIME NULL,
  PRIMARY KEY(project_id,user_id),
  FOREIGN KEY(project_id) REFERENCES project(id) ON DELETE CASCADE,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
DELIMITER //
DROP PROCEDURE IF EXISTS migrate_017_traffic_capture//
CREATE PROCEDURE migrate_017_traffic_capture()
BEGIN
 IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='traffic_records' AND COLUMN_NAME='source') THEN
  ALTER TABLE traffic_records ADD COLUMN source VARCHAR(20) NULL;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='traffic_records' AND COLUMN_NAME='capture_id') THEN
  ALTER TABLE traffic_records ADD COLUMN capture_id VARCHAR(36) NULL;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='traffic_records' AND COLUMN_NAME='interface_name') THEN
  ALTER TABLE traffic_records ADD COLUMN interface_name VARCHAR(200) NULL;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='traffic_records' AND COLUMN_NAME='request_params') THEN
  ALTER TABLE traffic_records ADD COLUMN request_params JSON NULL;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='traffic_records' AND COLUMN_NAME='target_host') THEN
  ALTER TABLE traffic_records ADD COLUMN target_host VARCHAR(500) NULL;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='traffic_records' AND COLUMN_NAME='duration_ms') THEN
  ALTER TABLE traffic_records ADD COLUMN duration_ms INTEGER NULL;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='traffic_records' AND INDEX_NAME='ix_traffic_records_capture_id') THEN
  CREATE INDEX ix_traffic_records_capture_id ON traffic_records(capture_id);
 END IF;
 CREATE TABLE IF NOT EXISTS schema_migration(version VARCHAR(100) PRIMARY KEY,applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP);
 INSERT IGNORE INTO schema_migration(version) VALUES('017_traffic_capture');
END//
CALL migrate_017_traffic_capture()//
DROP PROCEDURE migrate_017_traffic_capture//
DELIMITER ;
