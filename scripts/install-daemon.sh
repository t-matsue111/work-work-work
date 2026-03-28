#!/bin/bash
# work-work-work を macOS launchd デーモンとしてインストール
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/com.work-work-work.server.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.work-work-work.server.plist"
LABEL="com.work-work-work.server"

echo "=== work-work-work daemon installer ==="

# 既存があれば停止
if launchctl list | grep -q "$LABEL" 2>/dev/null; then
    echo "[更新] 既存デーモンを停止..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# plistをコピー
cp "$PLIST_SRC" "$PLIST_DST"
echo "[OK] plist をインストール: $PLIST_DST"

# 起動
launchctl load "$PLIST_DST"
echo "[OK] デーモン起動"

echo ""
echo "=== インストール完了 ==="
echo "  状態確認: launchctl list | grep work-work-work"
echo "  ログ:     tail -f logs/server-stdout.log"
echo "  停止:     bash scripts/uninstall-daemon.sh"
echo "  Web UI:   http://localhost:8766"
