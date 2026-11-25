#!/usr/bin/env bash
set -euo pipefail

# 上传安装包到 drumbear.cn 下载站，并更新软件内更新源（本地直传，不走云端）。
# DB绘谱 与 鼓乐熊Studio 共用。
#
# 用法:
#   upload_installer.sh <安装包路径> <windows|macos> <db-score|db-studio> [版本号]
#
#   - 版本号省略时读取当前目录的 release-version.txt
#   - 更新说明读取当前目录的 release-notes.txt（可无）
#
# 可用环境变量覆盖服务器配置:
#   DEPLOY_HOST / DEPLOY_USER / DEPLOY_PORT / DEPLOY_DOWNLOAD_DIR / DEPLOY_UPDATES_DIR

INSTALLER="${1:?用法: upload_installer.sh <安装包> <windows|macos> <db-score|db-studio> [版本]}"
OS_NAME="${2:?需要 windows 或 macos}"
FEED="${3:?需要 db-score 或 db-studio}"
VERSION="${4:-}"

HOST="${DEPLOY_HOST:-106.53.124.26}"
USER="${DEPLOY_USER:-ubuntu}"
PORT="${DEPLOY_PORT:-22}"
DOWNLOADS="${DEPLOY_DOWNLOAD_DIR:-/opt/db-platform/public/downloads}"
UPDATES="${DEPLOY_UPDATES_DIR:-/opt/db-platform/public/updates}"
MERGE_DIR="/opt/db-platform/tools"

case "$FEED" in
    db-score) APP="DB绘谱" ;;
    db-studio) APP="鼓乐熊Studio" ;;
    *) echo "未知产品: $FEED（支持 db-score / db-studio）" >&2; exit 2 ;;
esac

case "$OS_NAME" in
    windows) SUFFIX="Windows"; EXT="msi" ;;
    macos)   SUFFIX="macOS";   EXT="dmg" ;;
    *) echo "未知系统: $OS_NAME（支持 windows / macos）" >&2; exit 2 ;;
esac

[ -f "$INSTALLER" ] || { echo "找不到安装包: $INSTALLER" >&2; exit 2; }

VERSION="${VERSION:-$(tr -d '[:space:]' < release-version.txt)}"
NOTES="$(cat release-notes.txt 2>/dev/null || true)"
FNAME="${APP}-${SUFFIX}-${VERSION}.${EXT}"
SIZE="$(stat -f%z "$INSTALLER" 2>/dev/null || stat -c%s "$INSTALLER")"
SHA="$(shasum -a 256 "$INSTALLER" | awk '{print $1}')"

echo "上传: $INSTALLER"
echo "目标: $HOST:$DOWNLOADS/$FNAME（$SIZE 字节，sha256=$SHA）"

scp -P "$PORT" -o StrictHostKeyChecking=accept-new "$INSTALLER" "$USER@$HOST:$DOWNLOADS/$FNAME"

printf '%s' "$NOTES" | ssh -p "$PORT" -o StrictHostKeyChecking=accept-new "$USER@$HOST" \
    "bash -s -- '$FNAME' '$VERSION' '$SIZE' '$SHA' '$OS_NAME' '$FEED' '$UPDATES' '$DOWNLOADS' '$MERGE_DIR'" <<'REMOTE'
set -euo pipefail
FNAME="$1"; VERSION="$2"; SIZE="$3"; SHA="$4"; OS_NAME="$5"
FEED="$6"; UPDATES="$7"; DOWNLOADS="$8"; MERGE_DIR="$9"
NOTES="$(cat)"
flock -w 300 "/tmp/${FEED}-feed.lock" python3 "$MERGE_DIR/merge_release.py" \
    "$FNAME" "$VERSION" "$SIZE" "$SHA" "$OS_NAME" "$NOTES" "$FEED" "$UPDATES" "$DOWNLOADS"
REMOTE

echo "完成: $FNAME 已上架并更新 ${FEED}.json"
