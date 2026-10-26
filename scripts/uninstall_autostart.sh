#!/bin/bash
# 卸载开机自动启动服务
PLIST_FILE="$HOME/Library/LaunchAgents/com.oneideals.usbbaidusync.plist"

if [ -f "$PLIST_FILE" ]; then
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    rm -f "$PLIST_FILE"
    echo "✅ 已成功卸载开机自启服务！"
else
    echo "ℹ️ 未发现开机自启配置文件。"
fi
