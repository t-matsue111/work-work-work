#!/bin/bash
# SQLiteタスクDBを初期化するスクリプト
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DB_DIR="$PROJECT_DIR/db"
DB_FILE="$DB_DIR/tasks.db"
SCHEMA_FILE="$SCRIPT_DIR/schema.sql"

# DBディレクトリ作成
mkdir -p "$DB_DIR"

if [ -f "$DB_FILE" ]; then
  echo "既存のタスクDB検出: $DB_FILE"
  echo "スキーマを適用します（IF NOT EXISTS のため既存テーブルは影響なし）..."
else
  echo "新規タスクDBを作成します: $DB_FILE"
fi

# スキーマ適用
sqlite3 "$DB_FILE" < "$SCHEMA_FILE"

echo "タスクDB初期化完了: $DB_FILE"
echo "テーブル一覧:"
sqlite3 "$DB_FILE" ".tables"
echo "レコード数:"
sqlite3 "$DB_FILE" "SELECT COUNT(*) || ' 件' FROM tasks;"
