#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$DIR/USBBaiduSync.app"
DIST_DIR="$DIR/dist"
BUILD_DIR="$DIR/build"
ZIP_FILE="$DIR/USBBaiduSync.zip"

echo "📦 正在构建 USBBaiduSync.app 独立可分发安装包..."

# 1. 优先使用 PyInstaller 打包完全自包含的独立二进制 App（脱离本地 Python 依赖）
PYINSTALLER=""
if [ -x "$DIR/.venv/bin/pyinstaller" ]; then
    PYINSTALLER="$DIR/.venv/bin/pyinstaller"
elif which pyinstaller >/dev/null 2>&1; then
    PYINSTALLER="$(which pyinstaller)"
fi

if [ -n "$PYINSTALLER" ]; then
    echo "⚡ 正在使用 PyInstaller 编译独立可执行 App Bundle..."
    cd "$DIR"
    "$PYINSTALLER" --noconfirm --onedir --windowed \
        --name "USBBaiduSync" \
        --osx-bundle-identifier "com.oneideals.usbbaidusync" \
        --add-data "usb_baidu_sync:usb_baidu_sync" \
        run.py

    rm -rf "$APP_DIR"
    cp -R "$DIST_DIR/USBBaiduSync.app" "$APP_DIR"

    # 设置 LSUIElement 为 true，隐藏 Dock 栏图标，作为纯菜单栏驻留程序
    plutil -insert LSUIElement -bool true "$APP_DIR/Contents/Info.plist" 2>/dev/null || \
    plutil -replace LSUIElement -bool true "$APP_DIR/Contents/Info.plist"

    # 内置通用架构 BaiduPCS-Go 二进制
    if [ -f "$DIR/bin/BaiduPCS-Go" ]; then
        echo "📥 嵌入 Universal BaiduPCS-Go 命令行工具..."
        mkdir -p "$APP_DIR/Contents/MacOS/bin" "$APP_DIR/Contents/Resources/bin"
        cp "$DIR/bin/BaiduPCS-Go" "$APP_DIR/Contents/MacOS/bin/"
        cp "$DIR/bin/BaiduPCS-Go" "$APP_DIR/Contents/MacOS/"
        cp "$DIR/bin/BaiduPCS-Go" "$APP_DIR/Contents/Resources/bin/"
        chmod +x "$APP_DIR/Contents/MacOS/BaiduPCS-Go" \
                 "$APP_DIR/Contents/MacOS/bin/BaiduPCS-Go" \
                 "$APP_DIR/Contents/Resources/bin/BaiduPCS-Go"
    fi

    # 重新进行 Ad-hoc 代码签名
    codesign --force --deep --sign - "$APP_DIR" 2>/dev/null || true

    # 生成分发 Zip 压缩包（保留符号链接）
    echo "🗜️ 正在打包为分发 Zip 文件: $ZIP_FILE..."
    rm -f "$ZIP_FILE"
    zip -q -r -y "$ZIP_FILE" "USBBaiduSync.app"

    echo "🎉 构建完成！"
    echo "   App 目录: $APP_DIR"
    echo "   分发 Zip: $ZIP_FILE (可直接发送给他人解压测试)"
    exit 0
fi

echo "⚠️ 未找到 PyInstaller，使用轻量 Launcher 模式构建..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cp "$DIR/run.py" "$APP_DIR/Contents/Resources/"
cp -R "$DIR/usb_baidu_sync" "$APP_DIR/Contents/Resources/"
if [ -d "$DIR/bin" ]; then
    cp -R "$DIR/bin" "$APP_DIR/Contents/Resources/"
fi

cat << 'EOF' > "$APP_DIR/Contents/MacOS/launcher"
#!/bin/bash
APP_BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
RESOURCES_DIR="$APP_BUNDLE/Contents/Resources"

if [ -f "$RESOURCES_DIR/run.py" ]; then
    CODE_DIR="$RESOURCES_DIR"
else
    CODE_DIR="$(cd "$APP_BUNDLE/.." && pwd)"
fi

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

if [ -z "$PYTHON_EXEC" ]; then
    osascript -e 'display alert "USBBaiduSync 启动失败" message "未检测到包含 rumps 的 Python3 环境。"'
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

rm -f "$ZIP_FILE"
zip -q -r -y "$ZIP_FILE" "USBBaiduSync.app"

echo "✅ USBBaiduSync.app 构建完成: $APP_DIR"
