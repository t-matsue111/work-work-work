#!/bin/bash
# SQLite DB初期化スクリプト
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DB_DIR="$PROJECT_DIR/db"
DB_FILE="$DB_DIR/logs.db"
SCHEMA_FILE="$DB_DIR/schema.sql"

if [ ! -f "$SCHEMA_FILE" ]; then
  echo "エラー: schema.sql が見つかりません: $SCHEMA_FILE"
  exit 1
fi

mkdir -p "$DB_DIR"

if [ -f "$DB_FILE" ]; then
  echo "既存のDBファイルが見つかりました: $DB_FILE"
  echo "スキーマを適用します（IF NOT EXISTS で安全）..."
else
  echo "新規DBを作成します: $DB_FILE"
fi

sqlite3 "$DB_FILE" < "$SCHEMA_FILE"
echo "DB初期化完了: $DB_FILE"
