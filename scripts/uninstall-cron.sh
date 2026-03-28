#!/bin/bash
# claude-task-runner の cron エントリを削除するスクリプト
# マーカー区間のみを削除し、他のエントリは保持する

set -euo pipefail

MARKER_BEGIN="# BEGIN claude-task-runner"
MARKER_END="# END claude-task-runner"

echo "=== claude-task-runner cron アンインストーラー ==="
echo ""

# 現在の crontab を取得
CURRENT_CRON=$(crontab -l 2>/dev/null || true)

# マーカーの存在チェック
if ! echo "$CURRENT_CRON" | grep -q "$MARKER_BEGIN"; then
    echo "[情報] claude-task-runner の cron エントリは登録されていません。"
    echo "何もせず終了します。"
    exit 0
fi

# 削除対象を表示
echo "以下のエントリを削除します:"
echo "---"
echo "$CURRENT_CRON" | sed -n "/$MARKER_BEGIN/,/$MARKER_END/p"
echo "---"
echo ""

# 確認プロンプト
read -p "削除してよろしいですか？ [y/N]: " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "キャンセルしました。"
    exit 0
fi

# マーカー区間を削除
NEW_CRON=$(echo "$CURRENT_CRON" | sed "/$MARKER_BEGIN/,/$MARKER_END/d")

# 末尾の空行を整理
NEW_CRON=$(echo "$NEW_CRON" | sed -e :a -e '/^\n*$/{$d;N;ba;}')

# crontab に書き込み（空になった場合は crontab を削除）
if [ -z "$(echo "$NEW_CRON" | tr -d '[:space:]')" ]; then
    crontab -r 2>/dev/null || true
    echo ""
    echo "crontab が空になったため削除しました。"
else
    echo "$NEW_CRON" | crontab -
    echo ""
    echo "=== アンインストール完了 ==="
    echo ""
    echo "--- 現在の crontab ---"
    crontab -l
    echo "----------------------"
fi
