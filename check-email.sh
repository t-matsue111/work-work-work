#!/bin/bash
# Claude Task Runner: メールチェッカー
# 平日8-20時に毎時cronで実行される
set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# cron/ネスト実行時にClaude Codeのセッション検出を回避
unset CLAUDECODE 2>/dev/null || true

# --- ディレクトリ設定 ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
DB_FILE="$PROJECT_DIR/db/logs.db"
LOG_DIR="$PROJECT_DIR/logs"
LOCK_FILE="/tmp/claude-email-checker.lock"
TIMEOUT_SECONDS=180

# --- ログディレクトリ自動作成 ---
mkdir -p "$LOG_DIR"

# --- ファイルログ設定 ---
TIMESTAMP_FILE="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="$LOG_DIR/email-${TIMESTAMP_FILE}.log"

# ログ関数
log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "$msg" | tee -a "$LOG_FILE"
}

log_error() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*"
  echo "$msg" | tee -a "$LOG_FILE" >&2
}

# --- 排他制御（macOS互換: mkdir アトミックロック） ---
cleanup_lock() {
  rm -rf "$LOCK_FILE"
}

if ! mkdir "$LOCK_FILE" 2>/dev/null; then
  if [ -d "$LOCK_FILE" ]; then
    lock_age=$(( $(date +%s) - $(stat -f %m "$LOCK_FILE") ))
    if [ "$lock_age" -gt 1800 ]; then
      log "古いロックを検出（${lock_age}秒前）。強制解除します。"
      rm -rf "$LOCK_FILE"
      mkdir "$LOCK_FILE" 2>/dev/null || { log "ロック取得に失敗しました。"; exit 0; }
    else
      log "別のインスタンスが実行中です。スキップします。"
      exit 0
    fi
  else
    log "別のインスタンスが実行中です。スキップします。"
    exit 0
  fi
fi
trap cleanup_lock EXIT

# --- DB存在チェック ---
if [ ! -f "$DB_FILE" ]; then
  log "DBファイルが見つかりません。init-db.sh を実行します。"
  bash "$PROJECT_DIR/scripts/init-db.sh"
fi

# --- MCP設定確認 ---
MCP_CONFIG="$PROJECT_DIR/mcp-config-email.json"
if [ ! -f "$MCP_CONFIG" ]; then
  log_error "MCP設定ファイルが見つかりません: $MCP_CONFIG"
  exit 1
fi

# --- プロンプト読み込み ---
PROMPT_FILE="$PROJECT_DIR/prompts/email-checker.txt"
if [ ! -f "$PROMPT_FILE" ]; then
  log_error "プロンプトファイルが見つかりません: $PROMPT_FILE"
  exit 1
fi

PROMPT="$(cat "$PROMPT_FILE")"
log "プロンプト読み込み完了（${#PROMPT} 文字）"

# --- セッション永続化（email_checkはセッション継続） ---
SESSION_DIR="$PROJECT_DIR/.sessions"
SESSION_FILE="$SESSION_DIR/email-checker-session-id"
mkdir -p "$SESSION_DIR"

RESUME_OPT=""
if [ -f "$SESSION_FILE" ]; then
  SAVED_SESSION_ID="$(cat "$SESSION_FILE")"
  if [ -n "$SAVED_SESSION_ID" ]; then
    RESUME_OPT="--resume $SAVED_SESSION_ID"
    log "セッション継続: $SAVED_SESSION_ID"
  fi
else
  log "新規セッション（初回実行）"
fi

SESSION_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"

# --- claude CLI 実行 ---
START_TIME="$(date +%s)"
TIMESTAMP_ISO="$(date '+%Y-%m-%dT%H:%M:%S%z')"
RAW_RESPONSE=""
CLI_EXIT_CODE=0

log "claude CLI を実行中..."

set +eu
RAW_RESPONSE="$(timeout "$TIMEOUT_SECONDS" \
  claude -p "$PROMPT" \
    --output-format json \
    --mcp-config "$MCP_CONFIG" \
    --strict-mcp-config \
    --allowedTools "mcp__google_workspace_mcp__search_gmail_messages,mcp__google_workspace_mcp__get_gmail_message,mcp__google_workspace_mcp__list_gmail_labels,mcp__google_workspace_mcp__get_gmail_thread" \
    --max-turns 20 \
    --model sonnet \
    $RESUME_OPT \
  2>>"$LOG_FILE")"
CLI_EXIT_CODE=$?
set -eu

# セッションIDを保存（次回のresumeに使用）
# claude CLIのJSON出力からsession_idを抽出
NEW_SESSION_ID="$(echo "$RAW_RESPONSE" | jq -r 'if type == "array" then .[-1].session_id else .session_id end // empty' 2>/dev/null || echo "")"
if [ -n "$NEW_SESSION_ID" ]; then
  echo "$NEW_SESSION_ID" > "$SESSION_FILE"
  SESSION_ID="$NEW_SESSION_ID"
  log "セッションID保存: $NEW_SESSION_ID"
elif [ $CLI_EXIT_CODE -ne 0 ] && [ -n "$RESUME_OPT" ]; then
  # resume失敗時はセッションファイルを削除して次回新規作成
  log "セッション継続に失敗。次回は新規セッションで実行します。"
  rm -f "$SESSION_FILE"
fi

END_TIME="$(date +%s)"
DURATION_SECONDS=$((END_TIME - START_TIME))

log "claude CLI 終了（exit code: $CLI_EXIT_CODE, ${DURATION_SECONDS}秒）"

# --- 結果パース ---
STATUS="error"
TASK_NAME="メールチェック"
TASK_TYPE="email_check"
TASK_EXTERNAL_ID=""
RESULT_SUMMARY=""
RESULT_DETAIL=""
COST_USD=""
INPUT_TOKENS=""
OUTPUT_TOKENS=""
MODEL="sonnet"
ERROR_MESSAGE=""

if [ $CLI_EXIT_CODE -eq 124 ]; then
  STATUS="timeout"
  ERROR_MESSAGE="実行がタイムアウトしました（${TIMEOUT_SECONDS}秒）"
  log_error "$ERROR_MESSAGE"
elif [ $CLI_EXIT_CODE -ne 0 ]; then
  STATUS="error"
  ERROR_MESSAGE="claude CLI が異常終了しました（exit code: $CLI_EXIT_CODE）"
  log_error "$ERROR_MESSAGE"
else
  log "結果をパース中..."

  RESULT_JSON="$(echo "$RAW_RESPONSE" | jq -r 'if type == "array" then .[-1] else . end // empty' 2>/dev/null || echo "")"

  if [ -n "$RESULT_JSON" ]; then
    IS_ERROR="$(echo "$RESULT_JSON" | jq -r '.is_error // false' 2>/dev/null || echo "false")"
    COST_USD="$(echo "$RESULT_JSON" | jq -r '.cost_usd // .total_cost_usd // empty' 2>/dev/null || echo "")"
    INPUT_TOKENS="$(echo "$RESULT_JSON" | jq -r '.usage.input_tokens // empty' 2>/dev/null || echo "")"
    OUTPUT_TOKENS="$(echo "$RESULT_JSON" | jq -r '.usage.output_tokens // empty' 2>/dev/null || echo "")"

    RESULT_TEXT="$(echo "$RESULT_JSON" | jq -r '.result // empty' 2>/dev/null || echo "")"

    if [ "$IS_ERROR" = "true" ]; then
      STATUS="error"
      ERROR_MESSAGE="claude CLI がエラーを返しました"
      RESULT_SUMMARY="$RESULT_TEXT"
    else
      TASK_RESULT="$(echo "$RESULT_TEXT" | jq '.' 2>/dev/null || \
        echo "$RESULT_TEXT" | sed -n '/^{/,/^}/p' | jq '.' 2>/dev/null || \
        echo "")"

      if [ -n "$TASK_RESULT" ]; then
        TASK_NAME="$(echo "$TASK_RESULT" | jq -r '.task_name // "メールチェック"' 2>/dev/null || echo "メールチェック")"
        RESULT_SUMMARY="$(echo "$TASK_RESULT" | jq -r '.result_summary // empty' 2>/dev/null || echo "")"
        RESULT_DETAIL="$(echo "$TASK_RESULT" | jq -r '.result_detail // empty' 2>/dev/null || echo "")"

        TASK_STATUS="$(echo "$TASK_RESULT" | jq -r '.status // empty' 2>/dev/null || echo "")"
        case "$TASK_STATUS" in
          success) STATUS="success" ;;
          error) STATUS="error" ;;
          *) STATUS="success" ;;
        esac
      else
        STATUS="success"
        RESULT_SUMMARY="$RESULT_TEXT"
      fi
    fi
  else
    STATUS="error"
    ERROR_MESSAGE="claude CLIの出力をパースできませんでした"
    log_error "$ERROR_MESSAGE"
  fi
fi

log "ステータス: $STATUS"
[ -n "$COST_USD" ] && log "コスト: \$${COST_USD}"

# --- SQLiteへのログ記録 ---
log "SQLiteにログを記録中..."

escape_sql() {
  echo "$1" | sed "s/'/''/g"
}

SQL_TIMESTAMP="$(escape_sql "$TIMESTAMP_ISO")"
SQL_SESSION_ID="$(escape_sql "$SESSION_ID")"
SQL_TASK_NAME="$(escape_sql "$TASK_NAME")"
SQL_STATUS="$(escape_sql "$STATUS")"
SQL_RESULT_SUMMARY="$(escape_sql "$RESULT_SUMMARY")"
SQL_RESULT_DETAIL="$(escape_sql "$RESULT_DETAIL")"
SQL_ERROR_MESSAGE="$(escape_sql "$ERROR_MESSAGE")"
SQL_RAW_RESPONSE="$(escape_sql "$RAW_RESPONSE")"

sqlite3 "$DB_FILE" "INSERT INTO execution_logs (
  timestamp, runner_type, task_source, session_id,
  task_type, task_name, task_external_id, status,
  result_summary, result_detail, duration_seconds,
  cost_usd, input_tokens, output_tokens, model,
  error_message, raw_response
) VALUES (
  '${SQL_TIMESTAMP}', 'email_checker', null, '${SQL_SESSION_ID}',
  'email_check', '${SQL_TASK_NAME}', null, '${SQL_STATUS}',
  '${SQL_RESULT_SUMMARY}', '${SQL_RESULT_DETAIL}', ${DURATION_SECONDS},
  ${COST_USD:-null}, ${INPUT_TOKENS:-null}, ${OUTPUT_TOKENS:-null}, '${MODEL}',
  '${SQL_ERROR_MESSAGE}', '${SQL_RAW_RESPONSE}'
);"

log "SQLiteログ記録完了"

# --- ファイルログに結果サマリーを記録 ---
{
  echo "=== 実行結果サマリー ==="
  echo "タイムスタンプ: $TIMESTAMP_ISO"
  echo "セッションID: $SESSION_ID"
  echo "ステータス: $STATUS"
  echo "所要時間: ${DURATION_SECONDS}秒"
  [ -n "$COST_USD" ] && echo "コスト: \$${COST_USD}"
  [ -n "$INPUT_TOKENS" ] && echo "入力トークン: $INPUT_TOKENS"
  [ -n "$OUTPUT_TOKENS" ] && echo "出力トークン: $OUTPUT_TOKENS"
  [ -n "$RESULT_SUMMARY" ] && echo "結果要約: $RESULT_SUMMARY"
  [ -n "$ERROR_MESSAGE" ] && echo "エラー: $ERROR_MESSAGE"
  echo "========================"
} >> "$LOG_FILE"

log "完了"
