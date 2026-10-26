#!/bin/bash
# 一键安装开机自动启动 (LaunchAgent)
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_FILE="$HOME/Library/LaunchAgents/com.oneideals.usbbaidusync.plist"
mkdir -p "$HOME/Library/LaunchAgents"

if [ -x "$DIR/.venv/bin/python3" ]; then
    PYTHON_EXEC="$DIR/.venv/bin/python3"
else
    PYTHON_EXEC="$(which python3)"
fi

echo "正在配置开机自启服务: $PLIST_FILE"

cat << EOF > "$PLIST_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.oneideals.usbbaidusync</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_EXEC</string>
        <string>$DIR/run.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/USBBaiduSync/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/USBBaiduSync/stderr.log</string>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
</dict>
</plist>
EOF

mkdir -p "$HOME/Library/Logs/USBBaiduSync"
launchctl unload "$PLIST_FILE" 2>/dev/null || true
launchctl load "$PLIST_FILE"

echo "✅ 开机自启服务已安装并已启动！"
echo "状态栏右上角应已出现 💾 小图标。"
