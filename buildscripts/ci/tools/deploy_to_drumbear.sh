#!/usr/bin/env bash
set -euo pipefail

# 云端直传：把打包产物直接 scp 到 drumbear.cn 下载站，并更新软件内更新源。
# 安装包不再回传到开发者电脑，全程由 GitHub Actions 云端完成。
#
# 必需 env：
#   DEPLOY_SSH_KEY      服务器私钥（GitHub secret）
#   DEPLOY_HOST         服务器地址（GitHub variable）
#   DEPLOY_USER         服务器用户（GitHub variable）
#   DEPLOY_DOWNLOAD_DIR 下载站目录（GitHub variable）
#   DEPLOY_UPDATES_DIR  更新源目录（GitHub variable）
#   OS                  windows | macos
# 可选 env：
#   DEPLOY_PORT         默认 22
#   APP_NAME            默认 DB绘谱
#
# VERSION 从 release-version.txt 读取，RELEASE_NOTES 从 release-notes.txt 读取。

: "${DEPLOY_SSH_KEY:?}" "${DEPLOY_HOST:?}" "${DEPLOY_USER:?}"
: "${DEPLOY_DOWNLOAD_DIR:?}" "${DEPLOY_UPDATES_DIR:?}"
: "${OS:?}"

DEPLOY_PORT="${DEPLOY_PORT:-22}"
APP_NAME="${APP_NAME:-DB绘谱}"

VERSION="$(tr -d '[:space:]' < release-version.txt)"
RELEASE_NOTES="$(tr -d '\r' < release-notes.txt 2>/dev/null || true)"

KEY_FILE="$(mktemp)"
trap 'rm -f "$KEY_FILE"' EXIT
printf '%s\n' "$DEPLOY_SSH_KEY" > "$KEY_FILE"
chmod 600 "$KEY_FILE"

SSH_ARGS=(-i "$KEY_FILE" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30 -p "$DEPLOY_PORT")
SCP_ARGS=(-i "$KEY_FILE" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30 -P "$DEPLOY_PORT")

case "$OS" in
  windows) EXT=msi; SUFFIX=Windows ;;
  macos)   EXT=dmg; SUFFIX=macOS ;;
  *) echo "未知 OS: $OS" >&2; exit 1 ;;
esac

ARTIFACT="$(ls -1t build.artifacts/*."$EXT" 2>/dev/null | head -1 || true)"
if [ -z "$ARTIFACT" ]; then
  echo "未找到 $EXT 产物，build.artifacts 内容：" >&2
  ls -la build.artifacts/ >&2 || true
  exit 1
fi

FNAME="${APP_NAME}-${SUFFIX}-${VERSION}.${EXT}"
SIZE="$(stat -c%s "$ARTIFACT" 2>/dev/null || stat -f%z "$ARTIFACT")"
SHA="$(sha256sum "$ARTIFACT" 2>/dev/null | awk '{print $1}' || shasum -a 256 "$ARTIFACT" | awk '{print $1}')"

echo "上传 $ARTIFACT -> $FNAME（$SIZE 字节，sha256=$SHA）"

REMOTE_TMP="$DEPLOY_DOWNLOAD_DIR/.tmp-${FNAME}.$$"
scp "${SCP_ARGS[@]}" "$ARTIFACT" "$DEPLOY_USER@$DEPLOY_HOST:$REMOTE_TMP"
ssh "${SSH_ARGS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" "mv -f '$REMOTE_TMP' '$DEPLOY_DOWNLOAD_DIR/$FNAME'"

MERGE_DIR=/opt/db-platform/tools
ssh "${SSH_ARGS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" "mkdir -p '$MERGE_DIR'"
scp "${SCP_ARGS[@]}" buildscripts/ci/tools/drumbear_merge_release.py "$DEPLOY_USER@$DEPLOY_HOST:$MERGE_DIR/merge_release.py"

ssh "${SSH_ARGS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" \
  "flock -w 300 /tmp/db-score-feed.lock python3 '$MERGE_DIR/merge_release.py' \
   '$FNAME' '$VERSION' '$SIZE' '$SHA' '$OS' '$RELEASE_NOTES' '$DEPLOY_UPDATES_DIR' '$DEPLOY_DOWNLOAD_DIR'"

echo "完成：$FNAME 已上架并更新 db-score.json"
