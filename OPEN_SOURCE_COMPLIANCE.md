# DB动谱studio（DrumBear）— 开源合规与发布清单

> 本文档是 DrumBear 每次对外发布（二进制、应用商店、源码仓库）前必须逐项确认的合规底稿。
> 它不能替代法律意见；若用于商业发布，请交由熟悉开源合规的律师复核。

## 1. 项目性质

- DB动谱studio（英文/机器名 **DrumBear**）是 [MuseScore Studio](https://github.com/musescore/MuseScore)
  的 **GNU GPL version 3（GPL-3.0）派生作品**。
- 本项目是一个**独立项目**，与 MuseScore、Muse Group、MuseScore Studio 没有任何隶属、
  赞助或背书关系。
- “MuseScore”“MuseScore Studio” 等名称仅在**描述性使用**的意义上出现，用于说明本项目所支持的
  文件格式（如 `.mscz` / `.mscx`）和上游代码来源，不暗示官方身份或官方背书。

## 2. 发布前必须随包提供的材料

发布二进制时，必须保证用户能获得与二进制**完全对应**的源码，并随包附带以下文件：

- [ ] GPL-3.0 全文：`LICENSE.txt`（内容不得改动）
- [ ] 来源与版权归属说明：`NOTICE.md`
- [ ] 修改记录：`CHANGELOG.md`
- [ ] 第三方组件许可清单：`THIRD_PARTY_LICENSES.md`
- [ ] 字体许可（GNU Freefont / OFL 等，`fonts/*/` 下的许可证文件）
- [ ] SoundFont 许可（`MS Basic`、`FluidR3Mono` 等的 MIT 声明与 COPYING/README）
- [ ] 子模块 `muse`（muse_framework）的 GPL-3.0 `LICENSE.txt`
- [ ] `muse_deps` / `thirdparty/` 下每个第三方库各自的许可证与版权声明
- [ ] 完整对应源码（含子模块）的获取方式，且与发布二进制版本一一对应

## 3. 品牌与商标

- [ ] 不称自己为“MuseScore”“MuseScore Studio”，也不使用其 Logo、图标、splash、字标等标识
- [ ] 应用名、可执行文件名、安装包名、应用标识符、桌面文件名均为 DrumBear 自有
- [ ] 用户可见的“关于”页明确写明“基于 MuseScore Studio 的 GPL-3.0 派生版本”并附独立项目声明
- [ ] 未在宣传中暗示是官方作品或获官方背书

## 4. GPL-3.0 义务

- [ ] 整个 DrumBear（含对上游代码的修改）以 GPL-3.0 分发
- [ ] 不附加与 GPL 冲突的额外限制（例如禁止再分发）
- [ ] 保留上游原始版权声明与作者信息，不隐藏来源
- [ ] 对修改过的文件，保留原版权并注明修改（详见 CHANGELOG.md）

## 5. 发布渠道

- [ ] 源码仓库和二进制下载放在同一可见位置，写清对应关系
- [ ] 应用商店（如 App Store / Google Play / 微软商店）条款与 GPL 的兼容性已单独核对
- [ ] 商店页与下载页包含完整许可证与源码获取说明

## 6. 每次发布的复核动作

- [ ] 重新构建一次，确认应用名、图标、启动画面、“关于”页均为 DrumBear 品牌
- [ ] 用搜索工具扫描安装包与源码，确认无残留的 MuseScore Logo / 商标性标识
- [ ] 确认安装包内包含第 2 节列出的全部许可证文件
- [ ] 确认发布二进制与本次源码提交完全对应（同一条提交 / 标签）
