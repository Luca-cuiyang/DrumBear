#!/usr/bin/env bash
# DB Score - macOS 开发版部署脚本
# 用法：./dev-deploy-mac.sh
# 构建并部署到 /Applications/DB score制谱大师.app（开发测试用，不打包 DMG）

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
QT_BIN="/Users/luca/Desktop/DB score源码/Qt/6.10.2/macos/bin"
BUILD_DIR="$PROJECT_DIR/builds/Mac-Qt6.10.2-macos-Ninja-Release"
BUILT_APP="$BUILD_DIR/src/app/dbscore.app"
TARGET_APP="/Applications/DB score制谱大师.app"

export PATH="$QT_BIN:$PATH"

echo "[1/4] 构建 DBScore"
ninja -C "$BUILD_DIR" DBScore

STAGE="$(mktemp -d)/dbscore.app"
echo "[2/4] 部署 Qt 框架与插件 -> $STAGE"
ditto "$BUILT_APP" "$STAGE"
macdeployqt "$STAGE" -verbose=1 -qmldir="$PROJECT_DIR" > /tmp/macdeployqt.log 2>&1 || {
    tail -20 /tmp/macdeployqt.log
    exit 1
}

if [ -d "$STAGE/Contents/Resources/qml" ]; then
    mv "$STAGE/Contents/Resources/qml" "$STAGE/Contents/Resources/qml_mu"
    sed -i '' 's:Resources/qml:Resources/qml_mu:g' "$STAGE/Contents/Resources/qt.conf"
fi

echo "[3/4] ad-hoc 签名"
find "$STAGE/Contents/PlugIns" -name "*.dylib" -exec codesign --force --sign - {} \; 2>/dev/null || true
find "$STAGE/Contents/Frameworks" -maxdepth 1 -name "*.framework" -exec codesign --force --sign - {} \; 2>/dev/null || true
find "$STAGE/Contents/Frameworks" -maxdepth 1 -name "*.dylib" -exec codesign --force --sign - {} \; 2>/dev/null || true
codesign --force --sign - "$STAGE/Contents/MacOS/museupdater" 2>/dev/null || true
codesign --force --deep --sign - "$STAGE"

echo "[4/4] 部署到 $TARGET_APP"
if [ -d "$TARGET_APP" ]; then
    mv "$TARGET_APP" "$(mktemp -d)/DB score制谱大师.old.app"
fi
ditto "$STAGE" "$TARGET_APP"

echo "部署完成"
