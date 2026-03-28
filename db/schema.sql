-- Claude Task Runner: SQLite Schema

CREATE TABLE IF NOT EXISTS execution_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  runner_type TEXT NOT NULL,        -- 'task_runner' | 'email_checker'
  task_source TEXT,                 -- 'notion' | 'github'
  session_id TEXT,
  task_type TEXT,                   -- 'research' | 'sentry_analysis' | 'planning' | 'code_review' | 'email_check'
  task_name TEXT,
  task_external_id TEXT,            -- Notion page ID or GitHub issue/project item ID
  status TEXT NOT NULL DEFAULT 'unknown',  -- 'success' | 'error' | 'skipped' | 'timeout'
  result_summary TEXT,
  result_detail TEXT,
  duration_seconds INTEGER,
  cost_usd REAL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  model TEXT,
  error_message TEXT,
  raw_response TEXT,
  schedule_id INTEGER,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON execution_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_runner_type ON execution_logs(runner_type);
CREATE INDEX IF NOT EXISTS idx_logs_status ON execution_logs(status);
CREATE INDEX IF NOT EXISTS idx_logs_task_type ON execution_logs(task_type);

-- 日別コストサマリー
CREATE VIEW IF NOT EXISTS daily_cost_summary AS
SELECT date(timestamp) as date, runner_type,
  COUNT(*) as executions, SUM(cost_usd) as total_cost,
  SUM(input_tokens) as total_input_tokens, SUM(output_tokens) as total_output_tokens,
  AVG(duration_seconds) as avg_duration,
  SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success_count,
  SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as error_count
FROM execution_logs GROUP BY date(timestamp), runner_type;

-- 月別コストサマリー
CREATE VIEW IF NOT EXISTS monthly_cost_summary AS
SELECT strftime('%Y-%m',timestamp) as month,
  COUNT(*) as executions, SUM(cost_usd) as total_cost,
  SUM(input_tokens) as total_input_tokens, SUM(output_tokens) as total_output_tokens
FROM execution_logs GROUP BY strftime('%Y-%m',timestamp);
