#!/usr/bin/env bash

echo "Package"
trap 'echo Package failed; exit 1' ERR

APP_NAME="DB score制谱大师"
VOL_NAME="DB-Score"
DO_SIGN=false
DEPLOY_ONLY=false
ALLOW_ADHOC=false
SIGN_IDENTITY="${CODE_SIGN_IDENTITY:-Developer ID Application: DB Score}"
APPLE_TEAM_ID=""
APPLE_USERNAME=""
APPLE_PASSWORD=""

#! NOTE Project root, used as the macdeployqt qmldir. Must be an absolute
#! path so macdeployqt can resolve QML imports and deploy their plugins.
PROJECT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --app-name) APP_NAME="$2"; shift ;;
        --vol-name) VOL_NAME="$2"; shift ;;
        --sign) DO_SIGN=true ;;
        --deploy-only) DEPLOY_ONLY=true ;;
        --allow-adhoc) ALLOW_ADHOC=true ;;
        --identity) SIGN_IDENTITY="$2"; shift ;;
        --team-id) APPLE_TEAM_ID="$2"; shift ;;
        --user) APPLE_USERNAME="$2"; shift ;;
        --password) APPLE_PASSWORD="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# Use the locally installed Apple Development identity for development builds.
# A stable signing identity is required for macOS to remember folder permissions
# between launches instead of asking again whenever the binary is rebuilt.
if ! $DO_SIGN; then
    LOCAL_SIGN_IDENTITY="$(
        security find-identity -v -p codesigning 2>/dev/null \
            | sed -n 's/.*"\(Apple Development:.*\)"/\1/p' \
            | head -n 1
    )"
    if [ -n "$LOCAL_SIGN_IDENTITY" ]; then
        DO_SIGN=true
        SIGN_IDENTITY="$LOCAL_SIGN_IDENTITY"
    fi
fi

CODESIGN_TIMESTAMP_ARGS=()
if $DO_SIGN && [[ "$SIGN_IDENTITY" == "Developer ID Application:"* ]]; then
    CODESIGN_TIMESTAMP_ARGS=(--timestamp)
fi

################################################################
# Deploy
################################################################

APP_PATH=applebuild/dbscore.app

# 自动把 Qt 的 bin 目录加入 PATH，确保能找到 macdeployqt（不再依赖环境变量）
if ! command -v macdeployqt >/dev/null 2>&1; then
    for _qtdir in \
        "$(dirname "${PROJECT_DIR}")/Qt/6.10.2/macos/bin" \
        "${HOME}/Qt/6.10.2/macos/bin" \
        "/opt/homebrew/bin" \
        "/usr/local/bin"; do
        if [ -x "${_qtdir}/macdeployqt" ]; then
            export PATH="${_qtdir}:${PATH}"
            break
        fi
    done
fi

# Idempotent deployment: move away any QML dirs left by a previous run so that
# macdeployqt can deploy cleanly and the rename below always succeeds.
STALE_DEPLOY=$(mktemp -d)
for _qdir in qml qml_mu; do
    if [ -e "${APP_PATH}/Contents/Resources/${_qdir}" ]; then
        mv "${APP_PATH}/Contents/Resources/${_qdir}" "${STALE_DEPLOY}/${_qdir}"
    fi
done
# 清掉上次残留的 Qt QML 插件：否则 macdeployqt 会因为「文件已存在」而跳过把插件
# 复制到 Resources/qml/<Module>，导致运行时 "import QtQuick.Controls" 找不到
# qtquickcontrols2plugin，主窗口加载失败、卡在版本页。
if [ -e "${APP_PATH}/Contents/PlugIns/quick" ]; then
    mv "${APP_PATH}/Contents/PlugIns/quick" "${STALE_DEPLOY}/quick"
fi

echo "otool -L pre-macdeployqt"
otool -L ${APP_PATH}/Contents/MacOS/dbscore

echo "macdeployqt"
if $DO_SIGN && [[ "$SIGN_IDENTITY" == "Developer ID Application:"* ]]; then
    sign_args="-sign-for-notarization=${SIGN_IDENTITY}"
else
    sign_args=""
fi
macdeployqt ${APP_PATH} \
    -verbose=2 \
    -qmldir="${PROJECT_DIR}" \
    $sign_args

echo "otool -L post-macdeployqt"
otool -L ${APP_PATH}/Contents/MacOS/dbscore

require_bundled_file() {
    if [ ! -e "$1" ]; then
        echo "Required runtime component is missing: $1" >&2
        exit 1
    fi
}

require_bundled_file "${APP_PATH}/Contents/Frameworks/QtCore.framework/Versions/A/QtCore"
require_bundled_file "${APP_PATH}/Contents/Frameworks/QtQuick.framework/Versions/A/QtQuick"
require_bundled_file "${APP_PATH}/Contents/Frameworks/QtQuickWidgets.framework/Versions/A/QtQuickWidgets"
require_bundled_file "${APP_PATH}/Contents/Frameworks/libfreetype.6.dylib"
require_bundled_file "${APP_PATH}/Contents/Frameworks/libharfbuzz.dylib"
require_bundled_file "${APP_PATH}/Contents/Frameworks/libogg.0.dylib"
require_bundled_file "${APP_PATH}/Contents/PlugIns/platforms/libqcocoa.dylib"
require_bundled_file "${APP_PATH}/Contents/Resources/qml/QtQuick/qmldir"
require_bundled_file "${APP_PATH}/Contents/Resources/locale/qtbase_zh_CN.qm"
require_bundled_file "${APP_PATH}/Contents/Resources/locale/qtmultimedia_zh_CN.qm"
require_bundled_file "${APP_PATH}/Contents/Resources/locale/qtdeclarative_zh_CN.qm"

# DB Score does not use optional third-party SQL backends. Do not ship plugins
# whose dependencies point to Homebrew, Postgres.app, or /usr/local.
mkdir -p "${STALE_DEPLOY}/sqldrivers"
for _driver in libqsqlodbc.dylib libqsqlpsql.dylib libqsqlmimer.dylib; do
    if [ -e "${APP_PATH}/Contents/PlugIns/sqldrivers/${_driver}" ]; then
        mv "${APP_PATH}/Contents/PlugIns/sqldrivers/${_driver}" "${STALE_DEPLOY}/sqldrivers/"
    fi
done

# Qt 6 splits translations by module. The aggregate qt_zh_CN.qm is only a
# dependency stub on some Qt builds and makes QTranslator report a false error.
mkdir -p "${STALE_DEPLOY}/locale"
if [ -e "${APP_PATH}/Contents/Resources/locale/qt_zh_CN.qm" ]; then
    mv "${APP_PATH}/Contents/Resources/locale/qt_zh_CN.qm" "${STALE_DEPLOY}/locale/"
fi

# Remove dSYM files
echo "Remove dSYM files"
find ${APP_PATH}/Contents -type d -name "*.dSYM" -exec rm -r {} +

# Rename Resources/qml to Resources/qml_mu. This way, VST3 plugins that also use QML
# won't find these QML files, to prevent crashes because of conflicts.
# https://github.com/musescore/MuseScore/issues/21372
# https://github.com/musescore/MuseScore/issues/24331
echo "Rename Resources/qml to Resources/qml_mu"
mv ${APP_PATH}/Contents/Resources/qml ${APP_PATH}/Contents/Resources/qml_mu
# Reset any stale qml_mu references first so this stays idempotent across
# repeated packaging runs (otherwise qml_mu becomes qml_mu_mu).
sed -i '' -e 's:Resources/qml_mu_mu:Resources/qml:g' -e 's:Resources/qml_mu:Resources/qml:g' ${APP_PATH}/Contents/Resources/qt.conf
sed -i '' 's:Resources/qml:Resources/qml_mu:g' ${APP_PATH}/Contents/Resources/qt.conf

# 打包通用架构 FFmpeg 到 Frameworks/ffmpeg，保证 Intel 和 Apple Silicon Mac
# 在未安装 Homebrew FFmpeg 时也能直接导出 MP4。
python3 "${PROJECT_DIR}/buildscripts/packaging/macOS/bundle_ffmpeg.py" "${APP_PATH}"
for _ffmpeg_lib in \
    "${APP_PATH}/Contents/Frameworks/ffmpeg/libavformat."*.dylib \
    "${APP_PATH}/Contents/Frameworks/ffmpeg/libavcodec."*.dylib \
    "${APP_PATH}/Contents/Frameworks/ffmpeg/libavutil."*.dylib \
    "${APP_PATH}/Contents/Frameworks/ffmpeg/libswscale."*.dylib \
    "${APP_PATH}/Contents/Frameworks/ffmpeg/libswresample."*.dylib; do
    archs=$(lipo -archs "${_ffmpeg_lib}")
    case " ${archs} " in
        *" arm64 "*) ;;
        *) echo "Missing arm64 FFmpeg architecture: ${_ffmpeg_lib}"; exit 1 ;;
    esac
    case " ${archs} " in
        *" x86_64 "*) ;;
        *) echo "Missing x86_64 FFmpeg architecture: ${_ffmpeg_lib}"; exit 1 ;;
    esac
done

for _ffmpeg_name in libavformat libavcodec libavutil libswscale libswresample; do
    if ! find "${APP_PATH}/Contents/Frameworks/ffmpeg" -maxdepth 1 -type f \
            -name "${_ffmpeg_name}.*.dylib" -print -quit 2>/dev/null | grep -q .; then
        echo "Required FFmpeg runtime is missing: ${_ffmpeg_name}" >&2
        exit 1
    fi
done

echo "Verify bundled dynamic dependencies"
python3 "${PROJECT_DIR}/buildscripts/packaging/macOS/verify_bundle.py" "${APP_PATH}"

if $DO_SIGN; then
    # Re-sign appex to ensure proper entitlements
    APPEX_PATH="${APP_PATH}/Contents/PlugIns/DBScoreQuickLookPreviewExtension.appex"
    if [ -d "${APPEX_PATH}" ]; then
        echo "Re-sign appex"
        codesign --force \
            --options runtime \
            "${CODESIGN_TIMESTAMP_ARGS[@]}" \
            --entitlements "src/macos_integration/entitlements.plist" \
            -s "$SIGN_IDENTITY" \
            "${APPEX_PATH}"
    fi

    # Sign the bundled dylibs that are loaded at runtime and therefore
    # invisible to macdeployqt's dependency walk (e.g. libsndfile, vorbis)
    echo "Sign bundled dylibs"
    find "${APP_PATH}/Contents/Frameworks" -maxdepth 1 -type f -name "*.dylib" \
        -exec codesign --force --options runtime "${CODESIGN_TIMESTAMP_ARGS[@]}" \
        -s "$SIGN_IDENTITY" {} +
    find "${APP_PATH}/Contents/Frameworks/ffmpeg" -maxdepth 1 -type f -name "*.dylib" \
        -exec codesign --force --options runtime "${CODESIGN_TIMESTAMP_ARGS[@]}" \
        -s "$SIGN_IDENTITY" {} +

    # The update helper is a nested executable, so it must be signed before
    # sealing the outer app bundle.
    echo "Sign update helper"
    codesign --force \
        --options runtime \
        "${CODESIGN_TIMESTAMP_ARGS[@]}" \
        -s "$SIGN_IDENTITY" \
        "${APP_PATH}/Contents/MacOS/museupdater"

    # Re-sign main app after removing dSYM files and renaming qml folder
    echo "Re-sign main app"
    codesign --force \
        --options runtime \
        "${CODESIGN_TIMESTAMP_ARGS[@]}" \
        --entitlements "buildscripts/packaging/macOS/entitlements.plist" \
        -s "$SIGN_IDENTITY" \
        "${APP_PATH}"

    echo "Codesign verify"
    codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

    if [[ "$SIGN_IDENTITY" == "Developer ID Application:"* ]]; then
        echo "spctl"
        spctl --assess --type execute -vvv "${APP_PATH}"
    fi

    # Notarize and staple the .app before sealing the DMG
    if [[ "$SIGN_IDENTITY" == "Developer ID Application:"* ]] \
            && [ -n "$APPLE_USERNAME" ] && [ -n "$APPLE_PASSWORD" ]; then
        APP_ZIP="applebuild/app-notarization.zip"
        rm -f "$APP_ZIP"
        ditto -c -k --keepParent "${APP_PATH}" "$APP_ZIP"
        xcrun notarytool submit "$APP_ZIP" \
            --apple-id "$APPLE_USERNAME" \
            --team-id "$APPLE_TEAM_ID" \
            --password "$APPLE_PASSWORD" \
            --wait
        xcrun stapler staple "${APP_PATH}"
        xcrun stapler validate "${APP_PATH}"
        rm -f "$APP_ZIP"
    fi
else
    #! NOTE: 没有 Developer ID 证书时，也必须做 ad-hoc 签名。
    #! 否则 Apple Silicon 上未签名的 Qt 插件会被内核以
    #! “Code Signature Invalid” 杀死，导致安装后打开即“意外退出”。
    echo "Ad-hoc code signing (no Developer ID)"
    find "${APP_PATH}/Contents/PlugIns" -name "*.dylib" -exec codesign --force --sign - {} \;
    find "${APP_PATH}/Contents/Frameworks" -maxdepth 1 -name "*.framework" -exec codesign --force --sign - {} \;
    find "${APP_PATH}/Contents/Frameworks" -maxdepth 1 -name "*.dylib" -exec codesign --force --sign - {} \;
    find "${APP_PATH}/Contents/Frameworks/ffmpeg" -maxdepth 1 -name "*.dylib" -exec codesign --force --sign - {} \;
    codesign --force --sign - "${APP_PATH}/Contents/MacOS/museupdater"
    codesign --force --deep --sign - "${APP_PATH}"
fi

if $DEPLOY_ONLY; then
    echo "Deployment complete: ${APP_PATH}"
    exit 0
fi

if ! { $DO_SIGN && [[ "$SIGN_IDENTITY" == "Developer ID Application:"* ]] \
        && [ -n "$APPLE_TEAM_ID" ] && [ -n "$APPLE_USERNAME" ] && [ -n "$APPLE_PASSWORD" ]; }; then
    if $ALLOW_ADHOC; then
        echo "WARNING: creating a local-only package without Developer ID/notarization" >&2
    else
        echo "Release DMG requires Developer ID signing and notarization credentials." >&2
        echo "Use --allow-adhoc only for a local test package." >&2
        exit 1
    fi
fi

################################################################
# Create DMG
################################################################

DMG_NAME="${VOL_NAME}-uncompressed.dmg"
COMPRESSED_DMG_NAME="${VOL_NAME}.dmg"

rm -f "applebuild/${COMPRESSED_DMG_NAME}"

# Tip: increase the size if error on copy
hdiutil create -size 800m -fs APFS -volname "${VOL_NAME}" "applebuild/${DMG_NAME}"

# Mount the disk image
VOLUME="/Volumes/${VOL_NAME}"
ATTACH_OUTPUT=$(hdiutil attach "applebuild/${DMG_NAME}" -mountpoint "${VOLUME}")
echo "${ATTACH_OUTPUT}"
DEV=$(echo "${ATTACH_OUTPUT}" | head -n1 | awk '{print $1}')

# copy in the application bundle
cp -Rp ${APP_PATH} "${VOLUME}/${APP_NAME}.app"

# Verify the exact payload that will remain inside the final DMG.
python3 "${PROJECT_DIR}/buildscripts/packaging/macOS/verify_bundle.py" "${VOLUME}/${APP_NAME}.app"
codesign --verify --deep --strict "${VOLUME}/${APP_NAME}.app"

# Add symlink to Applications folder
echo "Add symlink to Applications folder"
ln -s /Applications/ "${VOLUME}/Applications"

# Decorate disk image
echo "Decorate disk image"
osascript <<-EOF || echo "Finder decoration skipped (AppleEvent unavailable); continuing."
tell application "Finder"
    set f to POSIX file ("${VOLUME}" as string) as alias
    tell folder f
        open
        tell container window
            set toolbar visible to false
            set statusbar visible to false
            set current view to icon view
            delay 1 -- sync
            set the bounds to {0, 0, 589, 435}
        end tell
        delay 1 -- sync
        set icon size of the icon view options of container window to 120
        set arrangement of the icon view options of container window to not arranged
        try
            set position of item "${APP_NAME}.app" to {150, 200}
        end try
        close
        try
            set position of item "Applications" to {439, 200}
        end try
        open
        set the bounds of the container window to {0, 0, 589, 435}
        update without registering applications
        delay 5 -- sync
        close
    end tell
    delay 5 -- sync
end tell
EOF

echo "Unmount"
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    # Detach by device: a failed eject can leave the image attached with the
    # mountpoint already gone
    if hdiutil detach "${DEV}"; then
        break
    fi
    if ! hdiutil info | grep -qE "^${DEV}(s[0-9]+)?[[:space:]]"; then
        echo "Disk image is already detached"
        break
    fi
    if [ $i -eq 20 ]; then
        echo "Failed to unmount the disk image; exiting after 20 retries."
        exit 1
    fi
    echo "Failed to unmount the disk image; retrying in 30s"
    sleep 30
done

# Convert the disk image to read-only
hdiutil convert "applebuild/${DMG_NAME}" -format ULFO -o "applebuild/${COMPRESSED_DMG_NAME}"

if $DO_SIGN; then
    echo "Codesign DMG"
    DMG_TIMESTAMP_ARGS=()
    if [[ "$SIGN_IDENTITY" == "Developer ID Application:"* ]]; then
        DMG_TIMESTAMP_ARGS=(--timestamp)
    fi
    codesign "${DMG_TIMESTAMP_ARGS[@]}" \
        -s "$SIGN_IDENTITY" \
        "applebuild/${COMPRESSED_DMG_NAME}"

    codesign --verify --verbose=2 "applebuild/${COMPRESSED_DMG_NAME}"
fi

shasum -a 256 "applebuild/${COMPRESSED_DMG_NAME}"

rm "applebuild/${DMG_NAME}"

# 复制最新 DMG 到桌面，并只保留最新安装包（清理旧 .dmg / .msi / .win）
cp "applebuild/${COMPRESSED_DMG_NAME}" "${HOME}/Desktop/DB score制谱大师.dmg"
find "${HOME}/Desktop" -maxdepth 1 -type f \( -name "DBScore-*.dmg" -o -name "DBScore-*.msi" -o -name "DBScore-*.win" -o -name "MuseScore_Studio_Installer*.exe" \) -delete 2>/dev/null
bash "${PROJECT_DIR}/buildscripts/packaging/macOS/cleanup_old_versions.sh" \
    --keep-dmg "${HOME}/Desktop/DB score制谱大师.dmg"
