#!/usr/bin/env bash
set -euo pipefail

# DB绘谱 发布：版本 +1，桌面目录同步改名，提交并推送（国内镜像 + GitHub），再手动触发自托管台式机打包。

SOURCE_ROOT="${SOURCE_ROOT:-$HOME/Desktop}"
PREFIX="DB绘谱-v"
REPO_BRANCH="${REPO_BRANCH:-ci/player-portrait-three-row-scroll-20261108}"

cd "$(dirname "$0")/.."

current_dir="$(ls -d "$SOURCE_ROOT/${PREFIX}"* 2>/dev/null | sort -V | tail -1 || true)"
if [ -z "$current_dir" ]; then
    echo "找不到当前版本目录: $SOURCE_ROOT/${PREFIX}*" >&2
    exit 1
fi

current_version="$(tr -d '[:space:]' < "$current_dir/DB绘谱/release-version.txt")"
if ! [[ "$current_version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    echo "无效版本号: $current_version" >&2
    exit 1
fi

major="${BASH_REMATCH[1]}"
minor="${BASH_REMATCH[2]}"
patch="${BASH_REMATCH[3]}"
new_version="$major.$minor.$((patch + 1))"
new_dir="$SOURCE_ROOT/${PREFIX}${new_version}"

echo "版本: $current_version -> $new_version"
echo "目录: $current_dir -> $new_dir"

if [ -e "$new_dir" ]; then
    echo "目标目录已存在: $new_dir" >&2
    exit 1
fi

# 1) 写新版本号
printf '%s' "$new_version" > "$current_dir/DB绘谱/release-version.txt"

# 2) 修正旧路径为新路径（CMake 缓存 + 打包脚本 + README）
sed -i '' "s|$current_dir|$new_dir|g" "$current_dir/DB绘谱/build.release/CMakeCache.txt" 2>/dev/null || true
sed -i '' "s|${PREFIX}${current_version}|${PREFIX}${new_version}|g" "$current_dir/README.md" 2>/dev/null || true

# 3) 重命名桌面目录
mv "$current_dir" "$new_dir"

# 4) 提交推送
git -C "$new_dir/DB绘谱" add -A
git -C "$new_dir/DB绘谱" commit -m "release($new_version): bump version" || true
git -C "$new_dir/DB绘谱" push origin "$REPO_BRANCH"
git -C "$new_dir/DB绘谱" push ssh://ubuntu@106.53.124.26/opt/git/DrumBear.git "$REPO_BRANCH:$REPO_BRANCH"

echo "完成。请触发自托管台式机打包（build_windows.yml, windows_x64），"
echo "然后用 buildscripts/ci/tools/upload_installer.sh 上传并更新更新源。"
