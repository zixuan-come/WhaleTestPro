-- Additive only: global FEISHU_WEBHOOK is never copied to projects.
CREATE TABLE IF NOT EXISTS project_notification (
    project_id INTEGER NOT NULL PRIMARY KEY,
    feishu_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    webhook_ciphertext TEXT NULL,
    signing_secret_ciphertext TEXT NULL,
    FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE
);
INSERT IGNORE INTO schema_migration (version) VALUES ('016_project_notification');
