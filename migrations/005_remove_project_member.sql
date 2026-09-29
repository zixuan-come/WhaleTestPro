-- 团队权限统一：项目必须归属团队，TeamMember 成为唯一成员与权限来源。
-- 执行前请先确认历史 project.team_id 已补齐；本项目当前数据库已清空重建。

DROP TABLE IF EXISTS `project_member`;

ALTER TABLE `project`
    MODIFY COLUMN `team_id` INT NOT NULL;
