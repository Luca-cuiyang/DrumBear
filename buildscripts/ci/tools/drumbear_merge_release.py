#!/usr/bin/env python3
"""DB绘谱 更新源合并脚本（在 drumbear.cn 服务器上运行）。

把某个平台的安装包资产合并进软件内更新源：
  - /opt/db-platform/public/updates/db-score.json
  - /opt/db-platform/public/updates/db-score-history.json

用法:
  drumbear_merge_release.py ASSET_NAME VERSION SIZE SHA256 OS NOTES UPDATES_DIR DOWNLOADS_DIR

说明:
  - 两个平台（Windows/macOS）并行跑 CI 时都会调用本脚本，外部用 flock 加锁即可避免竞态。
  - 若更新源当前 tag 与本版本不同，则开启新版本；否则在同一版本下替换本平台的资产，
    保留另一平台已上传的资产。
"""
import json
import os
import sys


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def main():
    if len(sys.argv) != 9:
        print(
            "usage: merge_release.py ASSET_NAME VERSION SIZE SHA256 OS NOTES UPDATES_DIR DOWNLOADS_DIR",
            file=sys.stderr,
        )
        return 2

    asset_name, version, size, sha256, os_name, notes, updates_dir, downloads_dir = sys.argv[1:9]
    size = int(size)

    feed_path = os.path.join(updates_dir, "db-score.json")
    hist_path = os.path.join(updates_dir, "db-score-history.json")

    feed = {"tag_name": "", "bodyMarkdown": "", "assets": []}
    hist = {"releases": []}
    if os.path.exists(feed_path):
        with open(feed_path, encoding="utf-8") as f:
            feed = json.load(f)
    if os.path.exists(hist_path):
        with open(hist_path, encoding="utf-8") as f:
            hist = json.load(f)

    asset = {
        "name": asset_name,
        "browser_download_url": "https://drumbear.cn/downloads/" + asset_name,
        "size": size,
        "sha256": sha256,
    }

    tag = "v" + version
    default_notes = "DB绘谱 " + version
    if feed.get("tag_name") != tag:
        feed = {
            "tag_name": tag,
            "bodyMarkdown": notes or default_notes,
            "assets": [asset],
        }
    else:
        marker = "-Windows-" if os_name == "windows" else "-macOS-"
        assets = [a for a in feed.get("assets", []) if marker not in a.get("name", "")]
        assets.append(asset)
        feed["assets"] = assets

    releases = [r for r in hist.get("releases", []) if r.get("version") != version]
    hist["releases"] = [{"version": version, "notes": notes or default_notes}] + releases

    atomic_write(feed_path, feed)
    atomic_write(hist_path, hist)

    print(
        "merged %s: feed=%s assets=%d history=%d"
        % (asset_name, tag, len(feed["assets"]), len(hist["releases"]))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
