-- 003_add_scenario.sql
-- 新增:场景编排 —— 有序的用例链,支持保存/加载/复用/重跑
-- 存 case_ids 为 JSON 数组(不做 FK 约束),原因:允许用例删除时场景保留(前端渲染时优雅跳过孤立引用),
-- 且更方便前端拖拽重排。

CREATE TABLE IF NOT EXISTS scenario (
    id           INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(100)  NOT NULL COMMENT '场景名(如"下单主流程")',
    description  VARCHAR(500)  NULL     COMMENT '场景描述',
    case_ids     JSON          NOT NULL COMMENT '有序用例 id 数组',
    project_id   INT           NOT NULL,
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY idx_project (project_id),
    CONSTRAINT fk_scenario_project FOREIGN KEY (project_id) REFERENCES project(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
