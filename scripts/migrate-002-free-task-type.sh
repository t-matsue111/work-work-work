#!/bin/bash
# マイグレーション: task_type のCHECK制約を削除し、自由入力（ラベル）にする
# 冪等実行可能
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TASKS_DB="$PROJECT_DIR/db/tasks.db"

echo "=== マイグレーション 002: task_type 自由入力化 ==="
echo ""

if [ ! -f "$TASKS_DB" ]; then
  echo "[スキップ] tasks.db が存在しません"
  exit 0
fi

# CHECK制約の有無を確認
CURRENT_SQL=$(sqlite3 "$TASKS_DB" "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks';")
if ! echo "$CURRENT_SQL" | grep -q "CHECK.*task_type.*IN"; then
  echo "[スキップ] task_type のCHECK制約は既に存在しません"
  exit 0
fi

echo "[更新] task_type CHECK制約を削除中..."

# バックアップ
cp "$TASKS_DB" "${TASKS_DB}.bak-$(date +%Y%m%d%H%M%S)"
echo "  [OK] バックアップ作成"

sqlite3 "$TASKS_DB" <<'SQL'
BEGIN TRANSACTION;

CREATE TABLE tasks_backup AS SELECT * FROM tasks;

DROP TRIGGER IF EXISTS trg_tasks_updated_at;
DROP TABLE tasks;

CREATE TABLE tasks (
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
  created_at TEXT DEFAULT (datetime('now','localtime')),
  updated_at TEXT DEFAULT (datetime('now','localtime'))
);

INSERT INTO tasks (id, task_name, task_type, priority, status, input, result, assigned_session_id, started_at, completed_at, schedule_id, created_at, updated_at)
SELECT id, task_name, task_type, priority, status, input, result, assigned_session_id, started_at, completed_at, schedule_id, created_at, updated_at
FROM tasks_backup;

DROP TABLE tasks_backup;

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_schedule_id ON tasks(schedule_id);

CREATE TRIGGER IF NOT EXISTS trg_tasks_updated_at
AFTER UPDATE ON tasks
FOR EACH ROW
BEGIN
  UPDATE tasks SET updated_at = datetime('now','localtime') WHERE id = OLD.id;
END;

COMMIT;
SQL

echo "  [OK] task_type CHECK制約を削除しました"
echo ""
echo "=== マイグレーション 002 完了 ==="
