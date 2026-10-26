#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$DIR/USBBaiduSync.app"

echo "📦 正在构建 USBBaiduSync.app..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cat << 'EOF' > "$APP_DIR/Contents/MacOS/launcher"
#!/bin/bash
# USBBaiduSync Launcher
APP_BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_DIR="$(cd "$APP_BUNDLE/.." && pwd)"
cd "$PROJECT_DIR"

# 优先使用项目专用 .venv
if [ -x "$PROJECT_DIR/.venv/bin/python3" ]; then
    PYTHON_EXEC="$PROJECT_DIR/.venv/bin/python3"
elif [ -x "/opt/homebrew/bin/python3" ]; then
    PYTHON_EXEC="/opt/homebrew/bin/python3"
else
    PYTHON_EXEC="python3"
fi

exec "$PYTHON_EXEC" "$PROJECT_DIR/run.py"
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
