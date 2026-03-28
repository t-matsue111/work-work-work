#!/bin/bash
# マイグレーション: tasksテーブルに実行設定カラムを追加
# 冪等実行可能
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TASKS_DB="$PROJECT_DIR/db/tasks.db"

echo "=== マイグレーション 003: タスク実行設定 ==="

if [ ! -f "$TASKS_DB" ]; then
  echo "[スキップ] tasks.db が存在しません"
  exit 0
fi

COLS="model timeout_seconds max_turns allowed_tools mcp_config work_dir"
for col in $COLS; do
  HAS=$(sqlite3 "$TASKS_DB" "SELECT COUNT(*) FROM pragma_table_info('tasks') WHERE name='$col';")
  if [ "$HAS" = "0" ]; then
    case "$col" in
      timeout_seconds) sqlite3 "$TASKS_DB" "ALTER TABLE tasks ADD COLUMN $col INTEGER;" ;;
      max_turns)       sqlite3 "$TASKS_DB" "ALTER TABLE tasks ADD COLUMN $col INTEGER;" ;;
      *)               sqlite3 "$TASKS_DB" "ALTER TABLE tasks ADD COLUMN $col TEXT;" ;;
    esac
    echo "  [OK] tasks.$col 追加"
  else
    echo "  [スキップ] tasks.$col は既に存在"
  fi
done

echo "=== マイグレーション 003 完了 ==="
