#!/usr/bin/env bash
set -euo pipefail

# 云端直传 v2：打包产物由「服务器多线程从 GitHub 拉取」上架到 drumbear.cn，
# 并更新软件内更新源。避开 GitHub 云端机器 → 国内服务器的慢速单连接 scp。
#
# 必需 env（由 workflow 注入）：
#   GH_TOKEN             GitHub 令牌（${{ github.token }}），仅用于解析 artifact 下载地址
#   GH_REPO              owner/repo
#   GH_RUN_ID            当前 run id
#   UPLOAD_ARTIFACT_NAME 本 job 上传的 artifact 名
#   DEPLOY_SSH_KEY / DEPLOY_HOST / DEPLOY_USER / DEPLOY_DOWNLOAD_DIR / DEPLOY_UPDATES_DIR
#   OS                  windows | macos
# 可选 env：DEPLOY_PORT(22) APP_NAME(DB绘谱)
#
# VERSION 从 release-version.txt 读取，RELEASE_NOTES 从 release-notes.txt 读取。

: "${GH_TOKEN:?}" "${GH_REPO:?}" "${GH_RUN_ID:?}" "${UPLOAD_ARTIFACT_NAME:?}"
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

# 1) 解析本 job 的 artifact 下载地址（GitHub 302 → Azure blob SAS URL）
API="https://api.github.com/repos/${GH_REPO}/actions/runs/${GH_RUN_ID}/artifacts"
ARTIFACT_URL="$(curl -fsSL -H "Authorization: Bearer ${GH_TOKEN}" "$API" \
  | python3 -c 'import json,sys,os; d=json.load(sys.stdin); print(next(a["archive_download_url"] for a in d.get("artifacts",[]) if a["name"]==os.environ["UPLOAD_ARTIFACT_NAME"]))')"
FINAL_URL="$(curl -fsSI -H "Authorization: Bearer ${GH_TOKEN}" "$ARTIFACT_URL" | tr -d '\r' | awk 'tolower($1)=="location:" {print $2; exit}')"
[ -n "$FINAL_URL" ] || { echo "无法解析 artifact 下载地址" >&2; exit 1; }

FNAME="${APP_NAME}-${SUFFIX}-${VERSION}.${EXT}"
echo "服务器将多线程拉取 artifact -> $FNAME"

# 2) 把合并脚本放到服务器（很小）
MERGE_DIR=/opt/db-platform/tools
ssh "${SSH_ARGS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" "mkdir -p '$MERGE_DIR'"
scp "${SCP_ARGS[@]}" buildscripts/ci/tools/drumbear_merge_release.py "$DEPLOY_USER@$DEPLOY_HOST:$MERGE_DIR/merge_release.py"

# 3) 服务器多线程拉取 + 解包 + 上架 + 更新更新源（URL/说明经 base64 传递避免 shell 转义问题）
B64_URL="$(printf '%s' "$FINAL_URL" | base64 | tr -d '\n')"
B64_NOTES="$(printf '%s' "$RELEASE_NOTES" | base64 | tr -d '\n')"
ssh "${SSH_ARGS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" bash -s \
  "$B64_URL" "$FNAME" "$VERSION" "$OS" "$B64_NOTES" \
  "$DEPLOY_UPDATES_DIR" "$DEPLOY_DOWNLOAD_DIR" "$MERGE_DIR" <<'REMOTE'
set -euo pipefail
URL="$(printf '%s' "$1" | base64 -d)"
FNAME="$2"; VERSION="$3"; OS="$4"
NOTES="$(printf '%s' "$5" | base64 -d)"
UPDATES_DIR="$6"; DOWNLOADS_DIR="$7"; MERGE_DIR="$8"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

echo "aria2 多线程拉取中…"
aria2c -x 16 -s 16 -k 1M --auto-file-renaming=false --max-tries=3 --retry-wait=5 --quiet=true -o dl.zip "$URL"

mkdir -p x
unzip -q -o dl.zip -d x
ART="$(find x -type f \( -name '*.msi' -o -name '*.dmg' \) | head -1)"
[ -n "$ART" ] || { echo "zip 中未找到安装包："; find x -maxdepth 2 | head -40; exit 1; }

SIZE="$(stat -c%s "$ART")"
SHA="$(sha256sum "$ART" | awk '{print $1}')"
mv "$ART" "$DOWNLOADS_DIR/$FNAME"

flock -w 300 /tmp/db-score-feed.lock python3 "$MERGE_DIR/merge_release.py" \
  "$FNAME" "$VERSION" "$SIZE" "$SHA" "$OS" "$NOTES" "$UPDATES_DIR" "$DOWNLOADS_DIR"

echo "上架完成：$FNAME（$SIZE 字节，sha256=$SHA）"
REMOTE

echo "完成：$FNAME 已上架并更新 db-score.json"
