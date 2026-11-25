# Windows 打包与发布（已锁定）

DB绘谱 的 Windows 安装包**只允许**通过自托管台式机 runner 打包，禁止云端打包、禁止虚拟机。

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

自托管 runner 从国内镜像 `drumbear.cn/git/DrumBear.git` 拉取代码，在台式机上完成编译与 MSI 打包。

## 发布（上传下载站 + 更新更新源）

打包完成后，用本机直传脚本上传（DB绘谱 与 鼓乐熊Studio 共用）：

```bash
bash buildscripts/ci/tools/upload_installer.sh \
  <MSI 文件路径> windows db-score
```

脚本会：

1. 把 MSI 直传到 `ubuntu@106.53.124.26:/opt/db-platform/public/downloads/`；
2. 计算 size 与 sha256；
3. 调用服务器上的 `merge_release.py` 更新 `db-score.json` 与 `db-score-history.json`。

macOS 安装包同理，把 `windows` 换成 `macos` 即可。
