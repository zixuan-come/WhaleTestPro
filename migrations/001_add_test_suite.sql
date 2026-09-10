-- 测试套件表
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
    FOREIGN KEY (project_id) REFERENCES project(id),
    INDEX idx_project (project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 扩展 schedule 表：支持套件
ALTER TABLE schedule ADD COLUMN suite_id INT NULL COMMENT '关联测试套件ID';
ALTER TABLE schedule ADD CONSTRAINT fk_schedule_suite FOREIGN KEY (suite_id) REFERENCES test_suite(id);
ALTER TABLE schedule ADD INDEX idx_suite (suite_id);

-- 扩展 test_report 表：支持套件报告
ALTER TABLE test_report ADD COLUMN suite_id INT NULL COMMENT '关联测试套件ID';
ALTER TABLE test_report ADD COLUMN suite_name VARCHAR(100) COMMENT '套件名称快照';
ALTER TABLE test_report ADD COLUMN execution_type VARCHAR(20) COMMENT 'suite/scenario/case/regression';
ALTER TABLE test_report ADD CONSTRAINT fk_report_suite FOREIGN KEY (suite_id) REFERENCES test_suite(id);
ALTER TABLE test_report ADD INDEX idx_suite (suite_id);
