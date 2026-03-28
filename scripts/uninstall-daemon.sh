#!/bin/bash
# work-work-work デーモンをアンインストール
set -euo pipefail

PLIST_DST="$HOME/Library/LaunchAgents/com.work-work-work.server.plist"
LABEL="com.work-work-work.server"

echo "=== work-work-work daemon uninstaller ==="

if launchctl list | grep -q "$LABEL" 2>/dev/null; then
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    echo "[OK] デーモン停止"
fi

if [ -f "$PLIST_DST" ]; then
    rm "$PLIST_DST"
    echo "[OK] plist 削除"
fi

echo "=== アンインストール完了 ==="
