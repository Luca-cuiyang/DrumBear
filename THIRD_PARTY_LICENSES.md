# DrumBear — 第三方许可证清单

本文列出 DrumBear（继承自 MuseScore Studio）中包含的第三方组件及其许可。
分发 DrumBear 时必须保留所有这些许可证与版权声明文件，不得只分发二进制。

## 主许可证

- 软件主体：**GNU GPL v3**，见 [LICENSE.txt](LICENSE.txt)。
- 字体嵌入例外：LICENSE.txt 顶部包含一段字体例外说明，保留该例外文本。

## 字体

字体目录 `fonts/` 下的字体各自带有许可证，主要位于各子目录的
`LICENSE.txt`、`OFL.txt`、`LICENSE` 或 `COPYING` 文件中。分发时逐一保留。

已知字体及许可类型：

| 字体/目录 | 说明 | 许可 |
| --- | --- | --- |
| bravura | SMuFL 参考字体 | SIL OFL |
| leland | MuseScore 主乐谱符号字体 | SIL OFL |
| edwin | 文本字体家族 | SIL OFL |
| musejazz | 手写风格字体 | SIL OFL |
| petaluma | SMuFL 字体 | SIL OFL |
| campania | 罗马数字分析字体 | 见 `campania/LICENSE` |
| gootville | 基于 Gonville 的乐谱符号字体 | 见目录内许可文件 |
| mscore / mscore-BC | 图标字体与旧版默认字体 | 见目录内许可文件 |
| finalemaestro / finalebroadway | 来自 MakeMusic 的字体 | 见目录内许可文件（OFL） |
| FreeSans / FreeSerif | 自由字体 | GNU Freefont / GPL + 字体例外 |
| MuseScoreTab* | 指法谱字体 | 见目录内许可文件 |
| smufl | SMuFL 规范与文档 | 见目录内许可文件 |

> 注意：bravura、petaluma、finalemaestro、finalebroadway、smufl 等**不是** MuseScore
> 维护的字体，请勿修改其内容；分发时保留各自许可证与文档。

## SoundFont（声音字体）

`share/sound/` 下自带的 SoundFont 均以 **MIT** 许可分发：

- `MS Basic.sf3` — 见 `share/sound/MS Basic_License.md`、`MS Basic_Readme.md`
- `FluidR3Mono_GM.sf3` — 见 `share/sound/FluidR3Mono_License.md`

必须保留上述许可与版权声明文件。

## 壁纸

- `share/wallpapers/COPYRIGHT` — 保留该版权说明。

## 框架子模块

- `muse/`（muse_framework）：**GNU GPL v3**，见 `muse/LICENSE.txt`。

## 随源码捆绑的第三方库

以下目录包含内嵌的第三方源码，各自目录内有许可文件，分发时保留：

| 位置 | 组件 |
| --- | --- |
| `muse/framework/global/thirdparty/` | kors_async、kors_logger、kors_modularity、kors_msgpack、kors_profiler、kors_rpcqueue、sg14 |
| `muse/framework/audio/thirdparty/` | fluidsynth、moodycamel、stb |
| `muse/framework/media/thirdparty/` | ffmpeg |
| `muse/framework/dockwindow/thirdparty/` | KDDockWidgets |
| `src/engraving/thirdparty/` | dtl、intervaltree |
| `src/importexport/midi/thirdparty/` | beatroot |
| `src/importexport/mei/thirdparty/` | libmei |
| `src/importexport/capella/thirdparty/` | rtf2html |

## 依赖引擎（muse_deps）

`muse_deps/` 以 recipe 方式管理约 50 个第三方依赖，每个 recipe 的 `spec.cmake`
中包含该依赖的版本、来源与许可证信息。常见依赖包括（非完整列表）：

expat、flac、freetype、harfbuzz、libcurl、liblouis、libpng、libsndfile、
mpg123、ogg、openssl、opus、opusfile、portaudio、pugixml、rapidjson、
sqlite、soundtouch、vorbis、zlib 等。

> 待办：在发布前的合规验证阶段（Phase 4），需要逐项汇总每个依赖的许可证文本，
> 并在安装包中一并提供。
