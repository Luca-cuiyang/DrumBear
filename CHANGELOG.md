# DrumBear 变更记录

本文件记录 DrumBear 相对上游 MuseScore Studio 的修改。

## [未发布] — 2026-09-24

### 构建验证（2026-09-24）

- 首次在 macOS（Apple Silicon）完成完整 CMake 配置与编译：Qt 6.10.2 + Ninja，
  Release 构建全部通过（2940 个构建步骤，无报错）。
- 修复首次启动取消提示的一处编译错误：`firstlaunchsetupmodel.cpp` 中 `muse::qtrc`
 误返回 `QString`，但变量为 `std::string`，已改为 `muse::trc`。

### 功能去 Muse 化（Phase 3，第一批）

- 默认关闭 `MUE_BUILD_MUSESOUNDS_MODULE`，不再构建 Muse Sounds 下载/安装模块（回退到内置 stub）。
- 默认关闭 `MUSE_MODULE_CLOUD_MUSESCORECOM`，不再启用 musescore.com 账户后端。
- 移除主页与开发者工具中的 “MuseSounds” 入口、`MuseScore.MuseSounds` QML 导入与相关组件。
- 重写首次启动取消提示，去掉 MuseHub / MuseSounds 引导；命令行帮助移除已禁用的 “MuseSounds” 取值。

### 功能去 Muse 化（Phase 3，第二批）

- 主页导航移除 “账户”（musescore.com 账号）与 “Learn”（MuseScore 教程）入口，
  并移除对应的 `Muse.Cloud` / `Muse.Learn` 导入、页面组件与路由分支。
- “文件”菜单移除 “保存到云端（Save to cloud）” 与 “发布到网上（Publish online）” 子菜单
  （含 MuseScore.com / Audio.com 分享项）。
- “帮助”菜单移除指向 handbook.musescore.org / musescore.org 的 “在线手册” 与 “寻求帮助” 链接。
- 发布工具栏移除 “Share on MuseScore.com / Audio.com” 两项。
- Learn 配置将 “Mastering MuseScore” 课程关闭（`classes_enabled: false`）。
- 删除已无调用的 `museHubFreeMuseSoundsUrl()` 与 `MUSEHUB_FREE_MUSE_SOUNDS_URL` 死代码。

### 功能去 Muse 化（Phase 3，第三批：关于页链接与在线发布/云曲谱）

- “关于”对话框标题改为 “About DB动谱studio”，移除 “访问 MuseScore 官网 / 获取帮助 /
  参与贡献 / 隐私政策” 等指向 musescore.org 的链接（对应 `AboutModel`、
  `IAppShellConfiguration`、`AppShellConfiguration` 中的相关方法一并删除）。
- “帮助”菜单与命令系统移除 “在线手册 / 寻求帮助 / 无障碍声明” 三个指向
  musescore.org 的命令及其处理函数。
- 删除 `PublishPage` 发布页（QML + 工具栏模型 + 页面注册 + 主工具栏 “Publish” 入口 +
  `musescore://publish` 路由与 UI 上下文）。
- 删除 `PROJECT_PUBLISH_COMMAND` / `PROJECT_SHARE_AUDIO_COMMAND` /
  `PROJECT_SAVE_TO_CLOUD_COMMAND` 三个命令及其注册、状态、UI 动作与控制器处理。
- “曲谱”页移除 “我的在线曲谱” 标签页，删除 `CloudScoresView` / `CloudScoresGridView` /
  `CloudScoresListView` 与 `CloudScoresModel`；`ScoresPageModel` 移除 `tabIndex`、
  `viewOnline`、`openScoreManager` 等云端相关接口。

### 功能去 Muse 化（Phase 3，第四批：声音配置显示名）

- 基础回放配置的显示名由 “MuseScore Basic” 改为 “DrumBear Basic”。
- 为兼容旧曲谱，保留 “MuseScore Basic” 作为旧名别名：加载旧谱时
  （`ProjectAudioSettings`）自动映射为新的 “DrumBear Basic”（与既有
  “Muse Sounds → MuseSounds” 的兼容逻辑保持一致）。
- 命令行 `--sound-profile` 帮助文本中的取值示例同步更新。

> 仍待处理（Phase 3 后续，可选）：`SaveProjectScenario` 内的云端保存实现与
> 最近曲谱列表中的云端状态指示（`CloudScoreStatusWatcher` 等）目前仍保留但已不可达，
> 待彻底重构云端保存流程时再一并移除。

### 品牌替换（Phase 2b-2 补充：欢迎页与首次启动文案）

- 重写“欢迎”对话框内容，移除 MuseScore.com / MuseHub / MuseSounds 营销文案与链接，改为 DrumBear 独立内容。
- 删除欢迎页品牌图片（MuseScoreCom / MuseSounds / MuseSoundsPro），首次启动页图片 `MuseSounds.png` 改为 `Sounds.png`。
- 首次启动页与 Windows 标题栏中的“MuseScore Studio”改为“DB动谱studio”。

### 品牌替换（Phase 2b-2：Linux/macOS 打包标识）

- Linux 桌面入口与 AppStream 元数据由 `org.musescore.MuseScore.*` 重命名为 `app.drumbear.DrumBear.*`，
  并同步更新 `SetupAppImagePackaging.cmake`、`portable-utils.in`。
- 重写 AppStream 描述为 DrumBear 独立派生项目，清除 musescore.org/musescore.com 链接与旧发布记录。
- macOS 快速查看 UTI 前缀由 `org.musescore.*` 改为 `app.drumbear.*`。
- 应用桌面文件名（`setDesktopFileName`）改为 `app.drumbear.DrumBear`。

> 仍待处理：MIME 定义 `musescore.xml.in` 及 MIME 图标名、`x-scheme-handler/musescore`
> URL 协议、翻译目录名 `locale/musescore`、内部二进制名 `mscore`、`muse/` 子模块内重复的
> 打包脚本，以及欢迎页营销图片与 musescore.com 云服务集成。

### 品牌替换（Phase 2b-1：图标与启动画面资源）

- 重新生成 DrumBear 应用图标（PNG 全尺寸、ICO、ICNS），替换 `share/icons/AppIcon/*`。
- 重新生成文件图标（`.mscx` / `.mscz` 的 SVG、PNG、ICO、ICNS），替换 `MscxIcon/`、`MsczIcon/`。
- 重写启动画面背景 `LoadingScreen.svg`，并把启动页底部网站由 `www.musescore.org` 改为占位 `www.drumbear.app`。
- 关于页 Logo 由 `mu_logo.svg` 改为新的 `drumbear_logo.svg`，并同步更新 `AboutDialog.qml` 与 `AppShell/CMakeLists.txt`。
- 替换 `share/icons/musescore_logo_full.png` 为 DrumBear 字标。

> 仍待处理（欢迎页/营销图片与云服务）：`resources/welcomedialog/*.png`、
> `FirstLaunchSetup/resources/*`、`OnlineSoundsPreview.gif`，以及 `muse/framework/cloud/`
> 下的 musescore.com 账户/云服务集成（Phase 3 功能去云化）。

### 品牌替换（Phase 2a：核心身份）

- 确定产品显示名为 **DB动谱studio**，英文/机器名为 **DrumBear**。
- 应用标识符由 `org.musescore.MuseScoreStudio5` 改为占位符 `app.drumbear.DrumBear5`。
- 项目名与 CMake 目标名 `MuseScoreStudio` 改为 `DrumBear`。
- 应用组织名/域由 MuseScore 改为 DrumBear（占位域 `drumbear.app`）。
- Windows 清单身份、Windows 可执行名（DrumBear5.exe）、WASM 可执行名改为 DrumBear。
- 关于页与重启提示中的“MuseScore Studio”改为“DB动谱studio”。
- `pyproject.toml` 名称与描述改为 DrumBear。

> 待办（Phase 2b）：Linux `.desktop`/appdata/MIME、macOS 文件类型 UTI、
> 图标与启动画面、QML 目录名、构建脚本与翻译文件、构建 revision 字符串等。

## [0.1.0] — 2026-09-24

### 初始化 fork

- 从 MuseScore Studio `main` 分支（开发中的 5.0.0）创建 fork 基线。
- 上游提交：
  - MuseScore：`171915dfd1f3dfa8498cdb3d78361302d92754c4`
  - muse_framework：`5ee27b82748c64add4b68106b7b1479d401fb9bd`
  - muse_deps：`436c667326379f78714d8ac703532d77182e70f4`
- 新增合规文档：README.md、NOTICE.md、CHANGELOG.md、THIRD_PARTY_LICENSES.md。

> 后续的每个功能/品牌改动都应记录在此，以便满足 GPL-3.0 “说明修改内容”的要求。
