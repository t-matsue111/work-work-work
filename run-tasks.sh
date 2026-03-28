#!/bin/bash
# Claude Task Runner: タスクランナーメインスクリプト
# 10分毎にcronで実行される
set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# cron/ネスト実行時にClaude Codeのセッション検出を回避
unset CLAUDECODE 2>/dev/null || true

# --- ディレクトリ設定 ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
DB_FILE="$PROJECT_DIR/db/logs.db"
TASKS_DB="$PROJECT_DIR/db/tasks.db"
CRON_NEXT="$PROJECT_DIR/scripts/cron-next.py"
LOG_DIR="$PROJECT_DIR/logs"
LOCK_FILE="/tmp/claude-task-runner.lock"
TIMEOUT_SECONDS=300
SCHEDULE_ID=""
SCHEDULE_TASK_ID=""
MODEL="sonnet"
MAX_TURNS=30
MCP_OPT=""
RESUME_OPT=""
WORK_DIR=""

# --- ログディレクトリ自動作成 ---
mkdir -p "$LOG_DIR"

# --- ファイルログ設定 ---
TIMESTAMP_FILE="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="$LOG_DIR/run-${TIMESTAMP_FILE}.log"

# ログ関数: stdout/stderrとファイルの両方に出力
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
  # ロックが古い場合（30分以上前）は強制解除
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

# --- タスクソース早期判定（スケジュール展開用） ---
if [ -n "${TASK_SOURCE:-}" ]; then
  _EARLY_SOURCE="$TASK_SOURCE"
else
  _EARLY_SOURCE="$(head -1 "$PROJECT_DIR/sources/source.conf" 2>/dev/null | tr -d '[:space:]')"
fi

# --- スケジュール展開 ---
if [ -f "$TASKS_DB" ]; then
  NOW="$(date '+%Y-%m-%d %H:%M:%S')"

  # 期限到来のスケジュールをタスクに展開
  DUE_SCHEDULES="$(sqlite3 -separator '|' "$TASKS_DB" "
    SELECT id, name, task_type, priority, cron_expr
    FROM schedules
    WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= '${NOW}'
  ;" 2>/dev/null || echo "")"

  if [ -n "$DUE_SCHEDULES" ]; then
    while IFS='|' read -r sid sname stype sprio scron; do
      [ -z "$sid" ] && continue

      # 重複チェック: 同schedule_idのpending/in_progressが既にあればスキップ
      EXISTING="$(sqlite3 "$TASKS_DB" "SELECT COUNT(*) FROM tasks WHERE schedule_id = $sid AND status IN ('pending', 'in_progress');")"
      NEXT_RUN="$(python3 "$CRON_NEXT" "$scron" 2>/dev/null || echo "")"

      if [ "$EXISTING" -gt 0 ]; then
        log "スケジュール $sid ($sname): 既にpending/in_progressタスクあり。スキップ"
        [ -n "$NEXT_RUN" ] && sqlite3 "$TASKS_DB" "UPDATE schedules SET next_run_at = '$(echo "$NEXT_RUN" | sed "s/'/''/g")' WHERE id = $sid;"
        continue
      fi

      # タスク生成
      local_sname="$(echo "$sname" | sed "s/'/''/g")"
      local_stype="$(echo "$stype" | sed "s/'/''/g")"
      local_sprio="$(echo "$sprio" | sed "s/'/''/g")"
      sqlite3 "$TASKS_DB" "INSERT INTO tasks (task_name, task_type, priority, input, schedule_id) VALUES ('${local_sname}', '${local_stype}', '${local_sprio}', '[スケジュール自動生成] ${local_sname}', $sid);"

      # next_run_at更新
      [ -n "$NEXT_RUN" ] && sqlite3 "$TASKS_DB" "UPDATE schedules SET next_run_at = '$(echo "$NEXT_RUN" | sed "s/'/''/g")', last_run_at = '$(echo "$NOW" | sed "s/'/''/g")' WHERE id = $sid;"

      log "スケジュール $sid ($sname) → タスク生成（次回: ${NEXT_RUN:-不明}）"
    done <<< "$DUE_SCHEDULES"
  fi

  # プリフライトチェック: 次のpendingタスクの実行設定を取得
  # spotタスク(schedule_id IS NULL)を優先
  NEXT_TASK="$(sqlite3 -separator '|' "$TASKS_DB" "
    SELECT id, schedule_id, model, timeout_seconds, max_turns, allowed_tools, mcp_config, work_dir FROM tasks
    WHERE status = 'pending'
    ORDER BY
      CASE WHEN schedule_id IS NULL THEN 0 ELSE 1 END,
      CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END,
      created_at ASC
    LIMIT 1;
  " 2>/dev/null || echo "")"

  if [ -n "$NEXT_TASK" ]; then
    IFS='|' read -r SCHEDULE_TASK_ID SCHEDULE_ID T_MODEL T_TIMEOUT T_MAXTURNS T_TOOLS T_MCP T_WORKDIR <<< "$NEXT_TASK"
    if [ -n "$SCHEDULE_ID" ]; then
      log "次のタスク (ID: $SCHEDULE_TASK_ID) はスケジュール由来 (schedule_id: $SCHEDULE_ID)"
    fi
    # spot taskの実行設定をオーバーライド
    if [ -z "$SCHEDULE_ID" ]; then
      [ -n "$T_MODEL" ] && MODEL="$T_MODEL" && log "タスク設定: model=$T_MODEL"
      [ -n "$T_TIMEOUT" ] && TIMEOUT_SECONDS="$T_TIMEOUT"
      [ -n "$T_MAXTURNS" ] && MAX_TURNS="$T_MAXTURNS"
      [ -n "$T_TOOLS" ] && ALLOWED_TOOLS="$T_TOOLS" && log "タスク設定: allowed_tools=$T_TOOLS"
      [ -n "$T_MCP" ] && MCP_OPT="--mcp-config $T_MCP" && log "タスク設定: mcp_config=$T_MCP"
      [ -n "$T_WORKDIR" ] && WORK_DIR="$T_WORKDIR" && log "タスク設定: work_dir=$T_WORKDIR"
    fi
  else
    if [ "$_EARLY_SOURCE" = "sqlite" ]; then
      log "pendingタスクがありません。claude起動をスキップします。"
      exit 0
    else
      log "pendingタスクなし（${_EARLY_SOURCE}ソースのため外部チェック続行）"
    fi
  fi
fi

# --- タスクソース決定 ---
if [ -n "${TASK_SOURCE:-}" ]; then
  log "環境変数 TASK_SOURCE を使用: $TASK_SOURCE"
else
  SOURCE_CONF="$PROJECT_DIR/sources/source.conf"
  if [ -f "$SOURCE_CONF" ]; then
    TASK_SOURCE="$(head -1 "$SOURCE_CONF" | tr -d '[:space:]')"
    log "source.conf から読み込み: $TASK_SOURCE"
  else
    log_error "TASK_SOURCE が未設定かつ source.conf が見つかりません。"
    exit 1
  fi
fi

# --- タスクソース検証 ---
if [ "$TASK_SOURCE" != "notion" ] && [ "$TASK_SOURCE" != "github" ] && [ "$TASK_SOURCE" != "sqlite" ]; then
  log_error "不明なタスクソース: $TASK_SOURCE（notion, github, sqlite のいずれかを指定してください）"
  exit 1
fi

# --- ソース別の設定読み込み ---
MCP_OPT=""
SOURCE_DIR="$PROJECT_DIR/sources/$TASK_SOURCE"
CONFIG_ENV="$SOURCE_DIR/config.env"
PROMPT_FILE="$SOURCE_DIR/prompt.txt"

if [ ! -f "$CONFIG_ENV" ]; then
  log_error "config.env が見つかりません: $CONFIG_ENV"
  exit 1
fi

if [ ! -f "$PROMPT_FILE" ]; then
  log_error "prompt.txt が見つかりません: $PROMPT_FILE"
  exit 1
fi

# config.env を読み込み
# shellcheck disable=SC1090
source "$CONFIG_ENV"

if [ "$TASK_SOURCE" = "notion" ]; then
  # Notionの場合: NOTION_TOKEN を secrets から読み込み、MCP設定を付与
  NOTION_SECRET_FILE="$HOME/.claude/secrets/notion.env"
  if [ -f "$NOTION_SECRET_FILE" ]; then
    # shellcheck disable=SC1090
    source "$NOTION_SECRET_FILE"
    export NOTION_TOKEN
    log "NOTION_TOKEN を読み込みました"
  else
    log_error "Notion秘密情報ファイルが見つかりません: $NOTION_SECRET_FILE"
    exit 1
  fi

  MCP_CONFIG="$SOURCE_DIR/mcp-config.json"
  if [ ! -f "$MCP_CONFIG" ]; then
    log_error "MCP設定が見つかりません: $MCP_CONFIG"
    exit 1
  fi
  MCP_OPT="--mcp-config $MCP_CONFIG --strict-mcp-config"
  log "Notionモード: MCP設定を使用"
elif [ "$TASK_SOURCE" = "github" ]; then
  log "GitHubモード: MCP不要"
elif [ "$TASK_SOURCE" = "sqlite" ]; then
  log "SQLiteモード: MCP不要、スタンドアロン実行"
fi

# --- プロンプト読み込みと変数展開 ---
PROMPT="$(cat "$PROMPT_FILE")"

# config.env で定義された変数を {{VAR_NAME}} パターンで展開
# 現在の環境変数から展開対象を収集
while IFS= read -r line; do
  # コメント行・空行をスキップ
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ -z "$line" ]] && continue
  # VAR=VALUE 形式から変数名を取得
  if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)= ]]; then
    VAR_NAME="${BASH_REMATCH[1]}"
    VAR_VALUE="${!VAR_NAME:-}"
    if [ -n "$VAR_VALUE" ]; then
      PROMPT="$(echo "$PROMPT" | sed "s|{{${VAR_NAME}}}|${VAR_VALUE}|g")"
    fi
  fi
done < "$CONFIG_ENV"

log "プロンプト読み込み完了（${#PROMPT} 文字）"

# --- セッションID生成 ---
SESSION_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
log "セッションID: $SESSION_ID"

# --- スケジュール由来タスクの設定オーバーライド ---
if [ -n "$SCHEDULE_ID" ]; then
  log "スケジュール設定をオーバーライド中 (schedule_id: $SCHEDULE_ID)..."

  # スケジュールから設定を取得
  SCHED_ROW="$(sqlite3 -separator '|' "$TASKS_DB" "
    SELECT model, timeout_seconds, max_turns, allowed_tools, mcp_config, prompt, prompt_file, work_dir, session_persistent, backend
    FROM schedules WHERE id = $SCHEDULE_ID;
  ")"

  if [ -n "$SCHED_ROW" ]; then
    IFS='|' read -r S_MODEL S_TIMEOUT S_MAXTURNS S_TOOLS S_MCP S_PROMPT S_PROMPTFILE S_WORKDIR S_PERSISTENT S_BACKEND <<< "$SCHED_ROW"

    # モデルオーバーライド
    [ -n "$S_MODEL" ] && MODEL="$S_MODEL"

    # タイムアウトオーバーライド
    [ -n "$S_TIMEOUT" ] && [ "$S_TIMEOUT" -gt 0 ] 2>/dev/null && TIMEOUT_SECONDS="$S_TIMEOUT"

    # max-turnsオーバーライド
    [ -n "$S_MAXTURNS" ] && [ "$S_MAXTURNS" -gt 0 ] 2>/dev/null && MAX_TURNS="$S_MAXTURNS"

    # 許可ツールオーバーライド
    if [ -n "$S_TOOLS" ]; then
      ALLOWED_TOOLS="$S_TOOLS"
      log "  許可ツール: $ALLOWED_TOOLS"
    fi

    # MCP設定オーバーライド
    if [ -n "$S_MCP" ] && [ -f "$S_MCP" ]; then
      MCP_OPT="--mcp-config $S_MCP"
      log "  MCP設定: $S_MCP"
    fi

    # プロンプトオーバーライド
    if [ -n "$S_PROMPT" ]; then
      PROMPT="$S_PROMPT"
      log "  プロンプト: スケジュール定義のテキストを使用"
    elif [ -n "$S_PROMPTFILE" ] && [ -f "$S_PROMPTFILE" ]; then
      PROMPT="$(cat "$S_PROMPTFILE")"
      log "  プロンプト: $S_PROMPTFILE を使用"
    fi

    # 作業ディレクトリ
    if [ -n "$S_WORKDIR" ] && [ -d "$S_WORKDIR" ]; then
      WORK_DIR="$S_WORKDIR"
      log "  作業ディレクトリ: $S_WORKDIR"
    fi

    # セッション永続化
    if [ "$S_PERSISTENT" = "1" ]; then
      SESSION_DIR="$PROJECT_DIR/.sessions"
      mkdir -p "$SESSION_DIR"
      SESSION_FILE="$SESSION_DIR/schedule-${SCHEDULE_ID}-session-id"
      if [ -f "$SESSION_FILE" ]; then
        SAVED_SESSION="$(cat "$SESSION_FILE")"
        RESUME_OPT="--resume $SAVED_SESSION"
        log "  セッション永続: resume $SAVED_SESSION"
      fi
    fi

    log "  モデル: $MODEL, タイムアウト: ${TIMEOUT_SECONDS}秒, max-turns: $MAX_TURNS"
  fi
fi

# --- claude CLI 実行 ---
START_TIME="$(date +%s)"
TIMESTAMP_ISO="$(date '+%Y-%m-%dT%H:%M:%S%z')"
RAW_RESPONSE=""
CLI_EXIT_CODE=0

log "claude CLI を実行中..."

# タスクソース別の許可ツール設定（スケジュールでオーバーライドされていなければ）
if [ -z "${ALLOWED_TOOLS:-}" ]; then
  ALLOWED_TOOLS="Read Grep Glob WebSearch WebFetch"
  if [ "$TASK_SOURCE" = "github" ]; then
    ALLOWED_TOOLS="Read Grep Glob WebSearch WebFetch Bash(git:*) Bash(gh:*)"
  elif [ "$TASK_SOURCE" = "sqlite" ]; then
    ALLOWED_TOOLS="Read Grep Glob WebSearch WebFetch Bash(git:*) Bash(sqlite3:*) Bash(curl:*)"
  fi
fi

# 実行コマンドをログに記録
CMD_LOG="timeout $TIMEOUT_SECONDS claude -p \"(プロンプト ${#PROMPT}文字)\" --output-format json --allowedTools \"$ALLOWED_TOOLS\" --max-turns $MAX_TURNS --model $MODEL"
[ -n "$MCP_OPT" ] && CMD_LOG="$CMD_LOG $MCP_OPT"
[ -n "$RESUME_OPT" ] && CMD_LOG="$CMD_LOG $RESUME_OPT"
[ -n "$WORK_DIR" ] && CMD_LOG="(cd $WORK_DIR) $CMD_LOG"
log "実行コマンド: $CMD_LOG"

# 作業ディレクトリ変更（指定があれば）
if [ -n "$WORK_DIR" ] && [ -d "$WORK_DIR" ]; then
  log "作業ディレクトリへ移動: $WORK_DIR"
  cd "$WORK_DIR"
fi

# タイムアウト付きで実行（エラーでも継続するため set +eu）
set +eu
RAW_RESPONSE="$(timeout "$TIMEOUT_SECONDS" \
  claude -p "$PROMPT" \
    --output-format json \
    --allowedTools "$ALLOWED_TOOLS" \
    $MCP_OPT \
    $RESUME_OPT \
    --max-turns "$MAX_TURNS" \
    --model "$MODEL" \
  2>>"$LOG_FILE")"
CLI_EXIT_CODE=$?
set -eu

# 元のディレクトリに戻る
cd "$PROJECT_DIR"

END_TIME="$(date +%s)"
DURATION_SECONDS=$((END_TIME - START_TIME))

log "claude CLI 終了（exit code: $CLI_EXIT_CODE, ${DURATION_SECONDS}秒）"

# --- 結果パース ---
STATUS="error"
TASK_NAME=""
TASK_TYPE=""
TASK_EXTERNAL_ID=""
RESULT_SUMMARY=""
RESULT_DETAIL=""
COST_USD=""
INPUT_TOKENS=""
OUTPUT_TOKENS=""
# MODELはスケジュールオーバーライドで変更されている可能性あり
MODEL="${MODEL:-sonnet}"
ERROR_MESSAGE=""

if [ $CLI_EXIT_CODE -eq 124 ]; then
  # timeout によるkill
  STATUS="timeout"
  ERROR_MESSAGE="実行がタイムアウトしました（${TIMEOUT_SECONDS}秒）"
  log_error "$ERROR_MESSAGE"
elif [ $CLI_EXIT_CODE -ne 0 ]; then
  STATUS="error"
  ERROR_MESSAGE="claude CLI が異常終了しました (exit code: ${CLI_EXIT_CODE})"
  log_error "$ERROR_MESSAGE"
else
  # 正常終了: JSONをパース
  log "結果をパース中..."

  # claude CLIの出力からresult要素を抽出
  # 出力形式: {"type":"result",...} または [{"type":"result",...}]
  RESULT_JSON="$(echo "$RAW_RESPONSE" | jq -r 'if type == "array" then .[-1] else . end // empty' 2>/dev/null || echo "")"

  if [ -n "$RESULT_JSON" ]; then
    # メタ情報の抽出
    IS_ERROR="$(echo "$RESULT_JSON" | jq -r '.is_error // false' 2>/dev/null || echo "false")"
    COST_USD="$(echo "$RESULT_JSON" | jq -r '.cost_usd // .total_cost_usd // empty' 2>/dev/null || echo "")"
    INPUT_TOKENS="$(echo "$RESULT_JSON" | jq -r '.usage.input_tokens // empty' 2>/dev/null || echo "")"
    OUTPUT_TOKENS="$(echo "$RESULT_JSON" | jq -r '.usage.output_tokens // empty' 2>/dev/null || echo "")"

    # resultフィールドからタスク結果を抽出
    RESULT_TEXT="$(echo "$RESULT_JSON" | jq -r '.result // empty' 2>/dev/null || echo "")"

    if [ "$IS_ERROR" = "true" ]; then
      STATUS="error"
      ERROR_MESSAGE="claude CLI がエラーを返しました"
      RESULT_SUMMARY="$RESULT_TEXT"
    else
      # resultフィールド内のJSONを抽出（テキストに埋め込まれたJSONブロック）
      TASK_RESULT="$(echo "$RESULT_TEXT" | jq '.' 2>/dev/null || \
        echo "$RESULT_TEXT" | sed -n '/^{/,/^}/p' | jq '.' 2>/dev/null || \
        echo "")"

      if [ -n "$TASK_RESULT" ]; then
        TASK_NAME="$(echo "$TASK_RESULT" | jq -r '.task_name // empty' 2>/dev/null || echo "")"
        TASK_TYPE="$(echo "$TASK_RESULT" | jq -r '.task_type // empty' 2>/dev/null || echo "")"
        TASK_EXTERNAL_ID="$(echo "$TASK_RESULT" | jq -r '.task_external_id // empty' 2>/dev/null || echo "")"
        RESULT_SUMMARY="$(echo "$TASK_RESULT" | jq -r '.result_summary // empty' 2>/dev/null || echo "")"
        RESULT_DETAIL="$(echo "$TASK_RESULT" | jq -r '.result_detail // empty' 2>/dev/null || echo "")"

        TASK_STATUS="$(echo "$TASK_RESULT" | jq -r '.status // empty' 2>/dev/null || echo "")"
        case "$TASK_STATUS" in
          success) STATUS="success" ;;
          error) STATUS="error" ;;
          needs_clarification) STATUS="needs_clarification" ;;
          *) STATUS="success" ;;
        esac
      else
        # JSONパースできなかった場合は、resultテキストをそのまま記録
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
[ -n "$TASK_NAME" ] && log "タスク名: $TASK_NAME"
[ -n "$TASK_TYPE" ] && log "タスク種別: $TASK_TYPE"
[ -n "$COST_USD" ] && log "コスト: \$${COST_USD}"

# --- セッション永続化: セッションID保存 ---
if [ -n "$SCHEDULE_ID" ] && [ -n "$RESUME_OPT" ] || [ -n "$SCHEDULE_ID" ]; then
  # session_persistent=1の場合、レスポンスからセッションIDを保存
  SCHED_PERSISTENT="$(sqlite3 "$TASKS_DB" "SELECT session_persistent FROM schedules WHERE id = $SCHEDULE_ID;" 2>/dev/null || echo "0")"
  if [ "$SCHED_PERSISTENT" = "1" ] && [ -n "$RESULT_JSON" ]; then
    RESP_SESSION="$(echo "$RESULT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")"
    if [ -n "$RESP_SESSION" ]; then
      SESSION_DIR="$PROJECT_DIR/.sessions"
      mkdir -p "$SESSION_DIR"
      echo "$RESP_SESSION" > "$SESSION_DIR/schedule-${SCHEDULE_ID}-session-id"
      log "セッションID保存: $RESP_SESSION"
    fi
  fi
fi

# --- スケジュール結果処理 ---
if [ -n "$SCHEDULE_ID" ]; then
  log "スケジュール $SCHEDULE_ID の結果を処理中..."
  # スケジュール由来タスクのステータスを同期
  if [ -n "$SCHEDULE_TASK_ID" ]; then
    if [ "$STATUS" = "success" ]; then
      sqlite3 "$TASKS_DB" "UPDATE tasks SET status = 'completed', completed_at = datetime('now','localtime') WHERE id = $SCHEDULE_TASK_ID AND status = 'pending';"
    else
      sqlite3 "$TASKS_DB" "UPDATE tasks SET status = 'error', result = '$(echo "${ERROR_MESSAGE:-実行失敗}" | sed "s/'/''/g")' WHERE id = $SCHEDULE_TASK_ID AND status = 'pending';"
    fi
  fi

  if [ "$STATUS" = "success" ]; then
    # 成功: consecutive_failures をリセット
    sqlite3 "$TASKS_DB" "UPDATE schedules SET consecutive_failures = 0, last_status = 'success' WHERE id = $SCHEDULE_ID;"
    log "  成功: consecutive_failures = 0"
  else
    # 失敗: consecutive_failures をインクリメント
    sqlite3 "$TASKS_DB" "UPDATE schedules SET consecutive_failures = consecutive_failures + 1, last_status = '$(echo "$STATUS" | sed "s/'/''/g")' WHERE id = $SCHEDULE_ID;"

    # 自動無効化チェック
    FAIL_INFO="$(sqlite3 -separator '|' "$TASKS_DB" "SELECT consecutive_failures, max_consecutive_failures FROM schedules WHERE id = $SCHEDULE_ID;")"
    IFS='|' read -r CUR_FAILS MAX_FAILS <<< "$FAIL_INFO"
    if [ -n "$CUR_FAILS" ] && [ -n "$MAX_FAILS" ] && [ "$CUR_FAILS" -ge "$MAX_FAILS" ]; then
      sqlite3 "$TASKS_DB" "UPDATE schedules SET enabled = 0 WHERE id = $SCHEDULE_ID;"
      log_error "  スケジュール $SCHEDULE_ID を自動無効化しました（連続失敗: ${CUR_FAILS}/${MAX_FAILS}）"
    else
      log "  失敗: consecutive_failures = ${CUR_FAILS}/${MAX_FAILS}"
    fi
  fi
fi

# --- SQLiteへのログ記録 ---
log "SQLiteにログを記録中..."

# SQLインジェクション防止のためシングルクォートをエスケープ
escape_sql() {
  echo "$1" | sed "s/'/''/g"
}

SQL_TIMESTAMP="$(escape_sql "$TIMESTAMP_ISO")"
SQL_TASK_SOURCE="$(escape_sql "$TASK_SOURCE")"
SQL_SESSION_ID="$(escape_sql "$SESSION_ID")"
SQL_TASK_TYPE="$(escape_sql "$TASK_TYPE")"
SQL_TASK_NAME="$(escape_sql "$TASK_NAME")"
SQL_TASK_EXTERNAL_ID="$(escape_sql "$TASK_EXTERNAL_ID")"
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
  error_message, raw_response, schedule_id
) VALUES (
  '${SQL_TIMESTAMP}', 'task_runner', '${SQL_TASK_SOURCE}', '${SQL_SESSION_ID}',
  '${SQL_TASK_TYPE}', '${SQL_TASK_NAME}', '${SQL_TASK_EXTERNAL_ID}', '${SQL_STATUS}',
  '${SQL_RESULT_SUMMARY}', '${SQL_RESULT_DETAIL}', ${DURATION_SECONDS},
  ${COST_USD:-"null"}, ${INPUT_TOKENS:-"null"}, ${OUTPUT_TOKENS:-"null"}, '${MODEL}',
  '${SQL_ERROR_MESSAGE}', '${SQL_RAW_RESPONSE}', ${SCHEDULE_ID:-"null"}
);"

log "SQLiteログ記録完了"

# --- ファイルログに結果サマリーを記録 ---
{
  echo "=== 実行結果サマリー ==="
  echo "タイムスタンプ: $TIMESTAMP_ISO"
  echo "セッションID: $SESSION_ID"
  echo "タスクソース: $TASK_SOURCE"
  echo "ステータス: $STATUS"
  echo "所要時間: ${DURATION_SECONDS}秒"
  [ -n "$TASK_NAME" ] && echo "タスク名: $TASK_NAME"
  [ -n "$TASK_TYPE" ] && echo "タスク種別: $TASK_TYPE"
  [ -n "$COST_USD" ] && echo "コスト: \$${COST_USD}"
  [ -n "$INPUT_TOKENS" ] && echo "入力トークン: $INPUT_TOKENS"
  [ -n "$OUTPUT_TOKENS" ] && echo "出力トークン: $OUTPUT_TOKENS"
  [ -n "$RESULT_SUMMARY" ] && echo "結果要約: $RESULT_SUMMARY"
  [ -n "$ERROR_MESSAGE" ] && echo "エラー: $ERROR_MESSAGE"
  echo "========================"
} >> "$LOG_FILE"

log "完了"
