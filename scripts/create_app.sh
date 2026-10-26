#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$DIR/USBBaiduSync.app"

echo "📦 正在构建支持全路径任意移动的 USBBaiduSync.app..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# 将核心代码复制到 App Bundle 内部，使 App 自包含、随处可移
cp "$DIR/run.py" "$APP_DIR/Contents/Resources/"
cp -R "$DIR/usb_baidu_sync" "$APP_DIR/Contents/Resources/"

cat << 'EOF' > "$APP_DIR/Contents/MacOS/launcher"
#!/bin/bash
# USBBaiduSync Universal Launcher (支持任意移动位置运行)

APP_BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
RESOURCES_DIR="$APP_BUNDLE/Contents/Resources"

# 1. 寻找代码目录 (内置源码 > 邻近目录 > 外置硬盘仓库目录)
if [ -f "$RESOURCES_DIR/run.py" ]; then
    CODE_DIR="$RESOURCES_DIR"
elif [ -f "$APP_BUNDLE/../run.py" ]; then
    CODE_DIR="$(cd "$APP_BUNDLE/.." && pwd)"
elif [ -f "/Volumes/External/LocalStorage/GitHub/usb-baidu-sync/run.py" ]; then
    CODE_DIR="/Volumes/External/LocalStorage/GitHub/usb-baidu-sync"
elif [ -f "$HOME/LocalStorage/GitHub/usb-baidu-sync/run.py" ]; then
    CODE_DIR="$HOME/LocalStorage/GitHub/usb-baidu-sync"
else
    osascript -e 'display alert "USBBaiduSync 启动失败" message "未找到程序核心代码，请确认外置硬盘已连接。"'
    exit 1
fi

# 2. 寻找可用的 Python 环境 (优先带 rumps 依赖的环境)
PYTHON_EXEC=""
CANDIDATES=(
    "$APP_BUNDLE/../.venv/bin/python3"
    "/Volumes/External/LocalStorage/GitHub/usb-baidu-sync/.venv/bin/python3"
    "$HOME/LocalStorage/GitHub/usb-baidu-sync/.venv/bin/python3"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "$(which python3 2>/dev/null)"
)

for p in "${CANDIDATES[@]}"; do
    if [ -x "$p" ]; then
        if "$p" -c "import rumps, AppKit" 2>/dev/null; then
            PYTHON_EXEC="$p"
            break
        fi
    fi
done

# 次选：若未检测到完全匹配依赖，使用第一个存在的 Python
if [ -z "$PYTHON_EXEC" ]; then
    for p in "${CANDIDATES[@]}"; do
        if [ -x "$p" ]; then
            PYTHON_EXEC="$p"
            break
        fi
    done
fi

if [ -z "$PYTHON_EXEC" ]; then
    osascript -e 'display alert "USBBaiduSync 启动失败" message "未检测到可用的 Python3 环境，请先安装 Python。"'
    exit 1
fi

export PYTHONPATH="$CODE_DIR:$PYTHONPATH"
cd "$CODE_DIR"
exec "$PYTHON_EXEC" "$CODE_DIR/run.py"
EOF

chmod +x "$APP_DIR/Contents/MacOS/launcher"

cat << 'EOF' > "$APP_DIR/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.oneideals.usbbaidusync</string>
    <key>CFBundleName</key>
    <string>USBBaiduSync</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

echo "✅ USBBaiduSync.app 构建完成: $APP_DIR"
