# Windows 打包（已锁定）

DB绘谱 的 Windows 安装包**只允许**通过 GitHub Actions 云端打包，禁止再用本地虚拟机
（Parallels）或其他本地方式出包。

## 出包方式（唯一）

在 GitHub 仓库 `Luca-cuiyang/DrumBear` 手动触发工作流 `Build: Windows`：

```text
platforms = windows_x64
build_mode = stable
publish   = off
```

或命令行：

```bash
gh workflow run "Build: Windows" -R Luca-cuiyang/DrumBear \
  --ref <分支名> \
  -f platforms=windows_x64 \
  -f build_mode=stable \
  -f publish=off
```

工作流完成后，从 GitHub Actions 的 artifacts 下载 MSI。

## 发布（上传下载站）

安装包上传到生产服务器，并通过更新源发布：

```text
服务器: ubuntu@106.53.124.26
目录:   /opt/db-platform/public/downloads/
更新源: /opt/db-platform/public/updates/db-score.json
```

上传后更新 `db-score.json` 中对应 asset 的 `size` 与 `sha256`，并追加
`db-score-history.json` 条目。
