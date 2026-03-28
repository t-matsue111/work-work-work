-- SQLiteタスクソース: タスクテーブルスキーマ

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_name TEXT NOT NULL,
  task_type TEXT NOT NULL DEFAULT 'research',
  priority TEXT DEFAULT 'medium' CHECK (priority IN ('high', 'medium', 'low')),
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'error', 'needs_clarification', 'needs_review')),
  input TEXT,
  result TEXT,
  assigned_session_id TEXT,
  started_at TEXT,
  completed_at TEXT,
  schedule_id INTEGER REFERENCES schedules(id),
  model TEXT,
  timeout_seconds INTEGER,
  max_turns INTEGER,
  allowed_tools TEXT,
  mcp_config TEXT,
  work_dir TEXT,
  archived INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  updated_at TEXT DEFAULT (datetime('now','localtime'))
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_schedule_id ON tasks(schedule_id);

-- updated_at 自動更新トリガー
CREATE TRIGGER IF NOT EXISTS trg_tasks_updated_at
AFTER UPDATE ON tasks
FOR EACH ROW
BEGIN
  UPDATE tasks SET updated_at = datetime('now','localtime') WHERE id = OLD.id;
END;

-- スケジュールテーブル
CREATE TABLE IF NOT EXISTS schedules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  task_type TEXT NOT NULL DEFAULT 'research',
  priority TEXT DEFAULT 'medium' CHECK (priority IN ('high', 'medium', 'low')),
  cron_expr TEXT NOT NULL,
  enabled INTEGER DEFAULT 1 CHECK (enabled IN (0, 1)),
  -- 実行バックエンド
  backend TEXT DEFAULT 'claude' CHECK (backend IN ('claude', 'ollama', 'codex')),
  model TEXT DEFAULT 'sonnet',
  -- 実行設定
  work_dir TEXT,
  mcp_config TEXT,
  allowed_tools TEXT,
  prompt TEXT,
  prompt_file TEXT,
  timeout_seconds INTEGER DEFAULT 300,
  max_turns INTEGER DEFAULT 30,
  session_persistent INTEGER DEFAULT 0 CHECK (session_persistent IN (0, 1)),
  -- スケジュール状態
  last_run_at TEXT,
  next_run_at TEXT,
  last_status TEXT,
  -- 自動無効化
  max_consecutive_failures INTEGER DEFAULT 3,
  consecutive_failures INTEGER DEFAULT 0,
  -- メタデータ
  created_at TEXT DEFAULT (datetime('now','localtime')),
  updated_at TEXT DEFAULT (datetime('now','localtime'))
);

-- schedules updated_at 自動更新トリガー
CREATE TRIGGER IF NOT EXISTS trg_schedules_updated_at
AFTER UPDATE ON schedules
FOR EACH ROW
BEGIN
  UPDATE schedules SET updated_at = datetime('now','localtime') WHERE id = OLD.id;
END;
