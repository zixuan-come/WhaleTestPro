-- 002_add_interface_category.sql
-- 新增:interface 加一层"分类"字段(单层扁平,Swagger tag 风格)
-- 用途:接口一多,前端列表需要按业务模块分组展示(订单/用户/公共…)
-- 策略:可空。老数据 category=NULL,前端归到"未分类"分组。零停机、零迁移。

ALTER TABLE interface
    ADD COLUMN category VARCHAR(50) NULL COMMENT '接口分类,前端分组用';

-- 备选:如果将来需要按 category 高频筛选,可以加索引
-- ALTER TABLE interface ADD INDEX idx_project_category (project_id, category);
