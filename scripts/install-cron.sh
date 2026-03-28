#!/bin/bash
# claude-task-runner の cron エントリをインストールするスクリプト
# 既存の crontab を保持し、マーカー区間のみ追加/更新する

set -euo pipefail

MARKER_BEGIN="# BEGIN claude-task-runner"
MARKER_END="# END claude-task-runner"

# 追加する cron エントリ
# メールチェッカーはschedules機能に移行済み（./task schedule-add で管理）
CRON_ENTRIES=$(cat <<'ENTRIES'
# BEGIN claude-task-runner

# タスクランナー: 10分毎（schedules展開も含む）
*/10 * * * * /bin/bash ~/project/claude-task-runner/run-tasks.sh >> ~/project/claude-task-runner/logs/cron-tasks.log 2>&1

# DB最適化: 毎日深夜3時
0 3 * * * sqlite3 ~/project/claude-task-runner/db/logs.db "VACUUM;"

# END claude-task-runner
ENTRIES
)

echo "=== claude-task-runner cron インストーラー ==="
echo ""

# 現在の crontab を取得（crontab が空の場合もエラーにしない）
CURRENT_CRON=$(crontab -l 2>/dev/null || true)

if echo "$CURRENT_CRON" | grep -q "$MARKER_BEGIN"; then
    echo "[更新] 既存の claude-task-runner エントリを置換します..."
    # マーカー区間を置換
    # sed で BEGIN から END までを削除し、新しいエントリを挿入
    NEW_CRON=$(echo "$CURRENT_CRON" | sed "/$MARKER_BEGIN/,/$MARKER_END/d")
    # 末尾の空行を整理
    NEW_CRON=$(echo "$NEW_CRON" | awk 'NF{p=1}p'| awk '{lines[NR]=$0} END{for(i=NR;i>=1;i--){if(lines[i]!=""){last=i;break}} for(i=1;i<=last;i++) print lines[i]}')
    if [ -n "$NEW_CRON" ]; then
        NEW_CRON="$NEW_CRON"$'\n\n'"$CRON_ENTRIES"
    else
        NEW_CRON="$CRON_ENTRIES"
    fi
else
    echo "[新規] claude-task-runner エントリを追加します..."
    if [ -n "$CURRENT_CRON" ]; then
        NEW_CRON="$CURRENT_CRON"$'\n\n'"$CRON_ENTRIES"
    else
        NEW_CRON="$CRON_ENTRIES"
    fi
fi

# crontab に書き込み
echo "$NEW_CRON" | crontab -

echo ""
echo "=== インストール完了 ==="
echo ""
echo "--- 現在の crontab ---"
crontab -l
echo "----------------------"
