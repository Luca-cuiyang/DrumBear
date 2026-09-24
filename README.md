# DB动谱studio（DrumBear）

DB动谱studio（英文/机器名 **DrumBear**，DB 为其缩写）是一款开源、免费的音乐制谱软件，是
[MuseScore Studio](https://github.com/musescore/MuseScore) 的 GPL-3.0 派生作品（fork）。

## 命名说明

| 用途 | 名称 |
| --- | --- |
| 产品显示名（关于页、应用名、用户可见文案） | DB动谱studio |
| 英文/机器名（可执行文件、Bundle、CMake 目标、路径） | DrumBear |
| 应用标识符（占位，待替换为正式域名） | app.drumbear.DrumBear5 |

DB动谱studio / DrumBear 是一个**独立项目**，与 MuseScore、Muse Group、MuseScore Studio
没有任何隶属、背书或赞助关系。“MuseScore”“MuseScore Studio” 等名称仅用于**描述性说明**，
指出本项目所支持的文件格式（如 `.mscz` / `.mscx`）和上游代码来源，不代表官方身份或官方背书。
“MuseScore” 名称和 Logo 是各自权利人的商标，本项目不使用这些商标标识。

## 许可证

DrumBear 以 **GNU General Public License version 3（GPL-3.0）** 分发。
完整的许可证文本见 [LICENSE.txt](LICENSE.txt)。

原始版权声明：

```text
Copyright (C) 1999-2026 MuseScore Limited and others
```

DrumBear 的修改与新增部分：

```text
Copyright (C) 2026 DrumBear
```

本项目的来源、修改说明和第三方组件许可，请分别查看：

- [NOTICE](NOTICE.md) — 来源与版权归属
- [CHANGELOG.md](CHANGELOG.md) — 修改记录
- [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) — 第三方许可证清单
- [OPEN_SOURCE_COMPLIANCE.md](OPEN_SOURCE_COMPLIANCE.md) — 开源合规与发布清单

## 上游基线

本项目从 MuseScore Studio 仓库的 `main` 分支（开发中的 5.0.0）复制而来。

| 仓库 | 提交 |
| --- | --- |
| musescore/MuseScore | `171915dfd1f3dfa8498cdb3d78361302d92754c4` |
| muse（muse_framework 子模块） | `5ee27b82748c64add4b68106b7b1479d401fb9bd` |
| muse_deps（依赖子模块） | `436c667326379f78714d8ac703532d77182e70f4` |

基线日期：2026-09-24

## 构建

构建方式与上游一致，使用 CMake。完整步骤请参考上游
[MuseScore 构建文档](https://github.com/musescore/MuseScore)。

简要步骤（以 macOS 为例）：

```bash
git submodule update --init --recursive
cmake -P build.cmake -DCMAKE_BUILD_TYPE=Release
cmake -P build.cmake -DCMAKE_BUILD_TYPE=Release run
```

> 注意：DrumBear 正在逐步替换品牌名称和标识。在品牌替换完成前，
> 构建产物中仍可能出现上游的“MuseScore”字样，请勿对外分发未完成改名的版本。

## 关于

DrumBear 是基于 MuseScore Studio 的 GPL-3.0 派生版本。
如需支持、参与或报告问题，请使用本项目自己的渠道。
