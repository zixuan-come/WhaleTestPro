-- ========================================================================
-- 001_add_project_id.sql
-- 全平台加多项目支持:所有业务资源挂 project_id 外键
-- ------------------------------------------------------------------------
-- 策略:零停机三步(ADD COLUMN NULL → UPDATE 塞默认 → MODIFY NOT NULL + FK)
-- 生产上加字段都是这个套路:服务不停、数据不丢、老代码不崩。
-- ========================================================================

USE whale_test_pro;

-- ========================================================================
-- Step 0: 保证 project 表存在
-- ------------------------------------------------------------------------
-- 期一 SQLAlchemy 已经会自动建这张表,这里 IF NOT EXISTS 幂等兜底,
-- 允许"没起过 app 就跑脚本"的情况。
-- ========================================================================

CREATE TABLE IF NOT EXISTS project (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(500) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================================================================
-- Step 1: 建默认项目(id=1)
-- ------------------------------------------------------------------------
-- INSERT IGNORE 让脚本可重跑(重复主键会被忽略,不报错)。
-- id=1 硬编码,方便下面 UPDATE 全塞 1;以后 M6 权限层再改成"每个用户
-- 首次登录自动建自己的默认项目"。
-- ========================================================================

INSERT IGNORE INTO project (id, name, description)
VALUES (1, '默认项目', '首次上线收纳所有历史数据的默认项目');

-- ========================================================================
-- Step 2: 8 张业务表分别走"零停机三步"
-- ------------------------------------------------------------------------
-- 每张表三步:
--   ① ADD COLUMN project_id INT NULL     ← 允许空,不违反旧行
--   ② UPDATE ... SET project_id = 1      ← 塞默认项目
--   ③ MODIFY NOT NULL + ADD FK           ← 加强约束
--
-- MySQL 8 里 ADD COLUMN 默认走 INSTANT DDL(不锁表、几乎零耗时),
-- 就算 traffic_records 有 5 万行也没压力。
-- ========================================================================

-- ---- interface ----
ALTER TABLE interface ADD COLUMN project_id INT NULL;
UPDATE interface SET project_id = 1 WHERE project_id IS NULL;
ALTER TABLE interface
  MODIFY COLUMN project_id INT NOT NULL,
  ADD CONSTRAINT fk_interface_project FOREIGN KEY (project_id) REFERENCES project(id);

-- ---- test_case ----
ALTER TABLE test_case ADD COLUMN project_id INT NULL;
UPDATE test_case SET project_id = 1 WHERE project_id IS NULL;
ALTER TABLE test_case
  MODIFY COLUMN project_id INT NOT NULL,
  ADD CONSTRAINT fk_test_case_project FOREIGN KEY (project_id) REFERENCES project(id);

-- ---- environment ----
ALTER TABLE environment ADD COLUMN project_id INT NULL;
UPDATE environment SET project_id = 1 WHERE project_id IS NULL;
ALTER TABLE environment
  MODIFY COLUMN project_id INT NOT NULL,
  ADD CONSTRAINT fk_environment_project FOREIGN KEY (project_id) REFERENCES project(id);

-- ---- mock ----
ALTER TABLE mock ADD COLUMN project_id INT NULL;
UPDATE mock SET project_id = 1 WHERE project_id IS NULL;
ALTER TABLE mock
  MODIFY COLUMN project_id INT NOT NULL,
  ADD CONSTRAINT fk_mock_project FOREIGN KEY (project_id) REFERENCES project(id);

-- ---- perf_tasks ----
ALTER TABLE perf_tasks ADD COLUMN project_id INT NULL;
UPDATE perf_tasks SET project_id = 1 WHERE project_id IS NULL;
ALTER TABLE perf_tasks
  MODIFY COLUMN project_id INT NOT NULL,
  ADD CONSTRAINT fk_perf_tasks_project FOREIGN KEY (project_id) REFERENCES project(id);

-- ---- schedule ----
ALTER TABLE schedule ADD COLUMN project_id INT NULL;
UPDATE schedule SET project_id = 1 WHERE project_id IS NULL;
ALTER TABLE schedule
  MODIFY COLUMN project_id INT NOT NULL,
  ADD CONSTRAINT fk_schedule_project FOREIGN KEY (project_id) REFERENCES project(id);

-- ---- test_report ----
ALTER TABLE test_report ADD COLUMN project_id INT NULL;
UPDATE test_report SET project_id = 1 WHERE project_id IS NULL;
ALTER TABLE test_report
  MODIFY COLUMN project_id INT NOT NULL,
  ADD CONSTRAINT fk_test_report_project FOREIGN KEY (project_id) REFERENCES project(id);

-- ---- traffic_records ----
ALTER TABLE traffic_records ADD COLUMN project_id INT NULL;
UPDATE traffic_records SET project_id = 1 WHERE project_id IS NULL;
ALTER TABLE traffic_records
  MODIFY COLUMN project_id INT NOT NULL,
  ADD CONSTRAINT fk_traffic_records_project FOREIGN KEY (project_id) REFERENCES project(id);

-- ========================================================================
-- 说明:外键 FK 会自动为 project_id 创建索引,不用额外 ADD INDEX。
-- 前端最常见的查询 WHERE project_id = X 会走这个索引,type=ref(参考
-- 7.2 学习记录索引那章),不会全表扫。
-- ========================================================================
