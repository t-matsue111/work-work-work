#!/bin/bash
# マイグレーション: schedulesテーブル追加 + tasks/execution_logsテーブル拡張
# 冪等実行可能（既に適用済みなら何もしない）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TASKS_DB="$PROJECT_DIR/db/tasks.db"
LOGS_DB="$PROJECT_DIR/db/logs.db"

echo "=== マイグレーション 001: Schedules機能 ==="
echo ""

# --- tasks.db ---
if [ ! -f "$TASKS_DB" ]; then
  echo "[スキップ] tasks.db が存在しません（init-tasks-db.sh で初期化してください）"
else
  echo "[tasks.db] マイグレーション開始..."

  # 1. schedulesテーブル作成（IF NOT EXISTS で冪等）
  sqlite3 "$TASKS_DB" <<'SQL'
CREATE TABLE IF NOT EXISTS schedules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  task_type TEXT NOT NULL DEFAULT 'research',
  priority TEXT DEFAULT 'medium' CHECK (priority IN ('high', 'medium', 'low')),
  cron_expr TEXT NOT NULL,
  enabled INTEGER DEFAULT 1 CHECK (enabled IN (0, 1)),
  backend TEXT DEFAULT 'claude' CHECK (backend IN ('claude', 'ollama', 'codex')),
  model TEXT DEFAULT 'sonnet',
  work_dir TEXT,
  mcp_config TEXT,
  allowed_tools TEXT,
  prompt TEXT,
  prompt_file TEXT,
  timeout_seconds INTEGER DEFAULT 300,
  max_turns INTEGER DEFAULT 30,
  session_persistent INTEGER DEFAULT 0 CHECK (session_persistent IN (0, 1)),
  last_run_at TEXT,
  next_run_at TEXT,
  last_status TEXT,
  max_consecutive_failures INTEGER DEFAULT 3,
  consecutive_failures INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  updated_at TEXT DEFAULT (datetime('now','localtime'))
);
SQL
  echo "  [OK] schedulesテーブル作成/確認"

  # 2. schedulesのupdated_atトリガー
  sqlite3 "$TASKS_DB" <<'SQL'
CREATE TRIGGER IF NOT EXISTS trg_schedules_updated_at
AFTER UPDATE ON schedules
FOR EACH ROW
BEGIN
  UPDATE schedules SET updated_at = datetime('now','localtime') WHERE id = OLD.id;
END;
SQL
  echo "  [OK] schedulesトリガー作成/確認"

  # 3. tasksテーブルにschedule_idカラム追加（存在チェック付き）
  HAS_SCHEDULE_ID=$(sqlite3 "$TASKS_DB" "SELECT COUNT(*) FROM pragma_table_info('tasks') WHERE name='schedule_id';")
  if [ "$HAS_SCHEDULE_ID" = "0" ]; then
    sqlite3 "$TASKS_DB" "ALTER TABLE tasks ADD COLUMN schedule_id INTEGER REFERENCES schedules(id);"
    echo "  [OK] tasks.schedule_id カラム追加"
  else
    echo "  [スキップ] tasks.schedule_id は既に存在"
  fi

  # 4. task_typeのCHECK制約にemail_checkを追加
  # SQLiteではCHECK制約の変更にテーブル再作成が必要
  # 現在のtask_typeの値を確認して、必要であれば再作成
  CURRENT_SQL=$(sqlite3 "$TASKS_DB" "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks';")
  if echo "$CURRENT_SQL" | grep -q "email_check"; then
    echo "  [スキップ] task_type CHECK制約は既に email_check を含む"
  else
    echo "  [更新] task_type CHECK制約を更新中..."

    # バックアップ
    cp "$TASKS_DB" "${TASKS_DB}.bak-$(date +%Y%m%d%H%M%S)"
    echo "  [OK] バックアップ作成"

    sqlite3 "$TASKS_DB" <<'SQL'
BEGIN TRANSACTION;

-- 一時テーブルにデータ退避
CREATE TABLE tasks_backup AS SELECT * FROM tasks;

-- 古いテーブルとトリガーを削除
DROP TRIGGER IF EXISTS trg_tasks_updated_at;
DROP TABLE tasks;

-- 新しいスキーマで再作成
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_name TEXT NOT NULL,
  task_type TEXT NOT NULL CHECK (task_type IN ('research', 'sentry_analysis', 'planning', 'code_review', 'email_check')),
  priority TEXT DEFAULT 'medium' CHECK (priority IN ('high', 'medium', 'low')),
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'error', 'needs_clarification', 'needs_review')),
  input TEXT,
  result TEXT,
  assigned_session_id TEXT,
  started_at TEXT,
  completed_at TEXT,
  schedule_id INTEGER REFERENCES schedules(id),
  created_at TEXT DEFAULT (datetime('now','localtime')),
  updated_at TEXT DEFAULT (datetime('now','localtime'))
);

-- データ復元
INSERT INTO tasks (id, task_name, task_type, priority, status, input, result, assigned_session_id, started_at, completed_at, schedule_id, created_at, updated_at)
SELECT id, task_name, task_type, priority, status, input, result, assigned_session_id, started_at, completed_at, schedule_id, created_at, updated_at
FROM tasks_backup;

-- バックアップテーブル削除
DROP TABLE tasks_backup;

-- インデックス再作成
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_schedule_id ON tasks(schedule_id);

-- トリガー再作成
CREATE TRIGGER IF NOT EXISTS trg_tasks_updated_at
AFTER UPDATE ON tasks
FOR EACH ROW
BEGIN
  UPDATE tasks SET updated_at = datetime('now','localtime') WHERE id = OLD.id;
END;

COMMIT;
SQL
    echo "  [OK] tasksテーブルを再作成（email_check追加、schedule_id追加）"
  fi

  echo "[tasks.db] マイグレーション完了"
fi

echo ""

# --- logs.db ---
if [ ! -f "$LOGS_DB" ]; then
  echo "[スキップ] logs.db が存在しません（init-db.sh で初期化してください）"
else
  echo "[logs.db] マイグレーション開始..."

  HAS_SCHEDULE_ID=$(sqlite3 "$LOGS_DB" "SELECT COUNT(*) FROM pragma_table_info('execution_logs') WHERE name='schedule_id';")
  if [ "$HAS_SCHEDULE_ID" = "0" ]; then
    sqlite3 "$LOGS_DB" "ALTER TABLE execution_logs ADD COLUMN schedule_id INTEGER;"
    echo "  [OK] execution_logs.schedule_id カラム追加"
  else
    echo "  [スキップ] execution_logs.schedule_id は既に存在"
  fi

  echo "[logs.db] マイグレーション完了"
fi

echo ""
echo "=== マイグレーション 001 完了 ==="
