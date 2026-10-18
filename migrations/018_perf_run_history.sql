-- 018: Reusable load definitions with an independent snapshot per execution.
-- Run on main and shadow. The app also applies/backfills this idempotently.
CREATE TABLE IF NOT EXISTS perf_runs (
 id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 task_id INT NOT NULL,
 project_id INT NOT NULL,
 execution_key VARCHAR(255) NOT NULL,
 status VARCHAR(50) NOT NULL,
 created_at DATETIME NOT NULL,
 snapshot JSON NOT NULL,
 CONSTRAINT uq_perf_run_execution UNIQUE(task_id, execution_key),
 INDEX ix_perf_runs_task_id(task_id),
 INDEX ix_perf_runs_project_id(project_id),
 FOREIGN KEY(task_id) REFERENCES perf_tasks(id) ON DELETE CASCADE,
 FOREIGN KEY(project_id) REFERENCES project(id)
);
INSERT INTO perf_runs(task_id,project_id,execution_key,status,created_at,snapshot)
SELECT t.id,t.project_id,COALESCE(t.celery_task_id,CONCAT('legacy:',t.id)),t.status,
 COALESCE(t.queued_at,t.started_at,UTC_TIMESTAMP()),
 JSON_OBJECT(
'id', t.id,
'name', t.name,
'target_host', t.target_host,
'target_path', t.target_path,
'users', t.users,
'spawn_rate', t.spawn_rate,
'duration', t.duration,
'load_config', t.load_config,
'iteration_stats', t.iteration_stats,
'status', t.status,
'celery_task_id', t.celery_task_id,
'queued_at', DATE_FORMAT(t.queued_at, '%Y-%m-%dT%H:%i:%s.%f'),
'started_at', DATE_FORMAT(t.started_at, '%Y-%m-%dT%H:%i:%s.%f'),
'heartbeat_at', DATE_FORMAT(t.heartbeat_at, '%Y-%m-%dT%H:%i:%s.%f'),
'finished_at', DATE_FORMAT(t.finished_at, '%Y-%m-%dT%H:%i:%s.%f'),
'failure_reason', t.failure_reason,
'rps', t.rps,
'avg_response_ms', t.avg_response_ms,
'p95_response_ms', t.p95_response_ms,
'p99_response_ms', t.p99_response_ms,
'request_stats', t.request_stats,
'error_summary', t.error_summary,
'history_samples', t.history_samples,
'fail_ratio', t.fail_ratio,
'project_id', t.project_id
) FROM perf_tasks t WHERE t.status <> 'pending' AND NOT EXISTS (
 SELECT 1 FROM perf_runs r WHERE r.task_id=t.id AND r.execution_key=COALESCE(t.celery_task_id,CONCAT('legacy:',t.id))
);
CREATE TABLE IF NOT EXISTS schema_migration(version VARCHAR(100) PRIMARY KEY, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT IGNORE INTO schema_migration(version) VALUES('018_perf_run_history');
