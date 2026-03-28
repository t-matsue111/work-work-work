#!/bin/bash
# SQLiteタスクDBにタスクを投入するヘルパースクリプト
#
# 使い方:
#   ./add-task.sh "タスク名" "research" "調査内容の詳細" [high|medium|low]
#
# 引数:
#   $1 - タスク名 (必須)
#   $2 - タスク種別 (必須): research / sentry_analysis / planning / code_review
#   $3 - 入力テキスト (必須): タスクの詳細・入力情報
#   $4 - 優先度 (省略時 medium): high / medium / low
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.env"

# 引数チェック
if [ $# -lt 3 ]; then
  echo "使い方: $0 \"タスク名\" \"タスク種別\" \"入力テキスト\" [優先度]"
  echo ""
  echo "タスク種別: research / sentry_analysis / planning / code_review"
  echo "優先度:     high / medium / low (デフォルト: medium)"
  echo ""
  echo "例:"
  echo "  $0 \"Next.js App Router調査\" \"research\" \"App Routerの移行戦略を調査\" high"
  echo "  $0 \"PR #42 レビュー\" \"code_review\" \"https://github.com/org/repo/pull/42\""
  exit 1
fi

TASK_NAME="$1"
TASK_TYPE="$2"
INPUT="$3"
PRIORITY="${4:-medium}"

# タスク種別の検証
case "$TASK_TYPE" in
  research|sentry_analysis|planning|code_review)
    ;;
  *)
    echo "エラー: 不明なタスク種別 '$TASK_TYPE'"
    echo "有効な種別: research / sentry_analysis / planning / code_review"
    exit 1
    ;;
esac

# 優先度の検証
case "$PRIORITY" in
  high|medium|low)
    ;;
  *)
    echo "エラー: 不明な優先度 '$PRIORITY'"
    echo "有効な優先度: high / medium / low"
    exit 1
    ;;
esac

# DB存在チェック
if [ ! -f "$SQLITE_TASK_DB" ]; then
  echo "エラー: タスクDBが見つかりません: $SQLITE_TASK_DB"
  echo "init-tasks-db.sh を先に実行してください。"
  exit 1
fi

# SQLインジェクション防止のためシングルクォートをエスケープ
escape_sql() {
  echo "$1" | sed "s/'/''/g"
}

SQL_NAME="$(escape_sql "$TASK_NAME")"
SQL_TYPE="$(escape_sql "$TASK_TYPE")"
SQL_INPUT="$(escape_sql "$INPUT")"
SQL_PRIORITY="$(escape_sql "$PRIORITY")"

# タスク投入
sqlite3 "$SQLITE_TASK_DB" "INSERT INTO tasks (task_name, task_type, input, priority) VALUES ('${SQL_NAME}', '${SQL_TYPE}', '${SQL_INPUT}', '${SQL_PRIORITY}');"

# 投入したタスクのIDを取得
TASK_ID="$(sqlite3 "$SQLITE_TASK_DB" "SELECT last_insert_rowid();")"

echo "タスクを追加しました:"
echo "  ID:       $TASK_ID"
echo "  タスク名: $TASK_NAME"
echo "  種別:     $TASK_TYPE"
echo "  優先度:   $PRIORITY"
echo "  入力:     $INPUT"
