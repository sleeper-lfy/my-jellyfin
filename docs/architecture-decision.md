# ADR 001：独立 Windows 桌面应用

日期：2026-10-22。状态：采用并实现。产品名暂定 Lumen（私人光影库）。

## 证据与方案比较

阅读了 Jellyfin 服务端、Web 和插件模板仓库的 README：

- https://github.com/jellyfin/jellyfin ：服务端使用 .NET，依赖 FFmpeg，Web 客户端是另一个项目；支持 Windows，典型运行形态为服务进程加 8096 端口客户端。
- https://github.com/jellyfin/jellyfin-web ：Node/npm/Webpack 前端构建。
- https://github.com/jellyfin/jellyfin-plugin-template ：编译型 .NET 插件；元数据、LibraryManager、计划任务等接口成熟；插件包版本须匹配服务端版本。

官方文档域名在本环境返回代理 403，因此实际核对的是上述上游仓库原文，不声称运行或测试过 Jellyfin 本体。

| 维度 | Jellyfin 二次开发 | 独立 PySide6 桌面应用 |
|---|---|---|
| 首次媒体服务能力 | 扫描、元数据、用户、转码、设备支持成熟 | 需实现扫描、数据库、任务和播放记录 |
| 单机拖拽和安全移动 | Web 与服务端文件权限边界复杂，需原生壳/桥接 | QFileDialog、桌面拖拽及本地文件 API 直接实现 |
| 第三方脚本 | .NET 插件默认拥有宿主权限，需再增加脚本隔离层 | 直接采用受限 JS 引擎、宿主网络代理和进程超时 |
| 随机对象/发现/演员均分 | 可做插件，但与核心用户状态和前端导航深度耦合 | 用专用作品模型实现业务规则 |
| UI 重构 | 需维护大规模 Web 分叉，跟随上游重构 | 一套 Qt 桌面主题与可复用卡片、对话框 |
| Windows 启动 | 服务端、端口、Web 资源、可选原生壳 | 单一桌面进程，SQLite，无端口/账户要求 |
| 后续升级 | .NET/API/插件/Web 多项目兼容性 | Python/Qt/FFmpeg 三类依赖，模块边界可控 |
| 最合适场景 | NAS、多用户、跨设备流媒体 | 本项目的个人本地整理与观看 |

## 选择

采用 Python 3.11–3.13 + PySide6 6.8.3 + SQLite。Qt Multimedia 的 FFmpeg 后端负责视频解码、音轨和内嵌字幕；外部 FFmpeg/FFprobe 负责探测、缩略图与外挂字幕转换。不自研解码器。

评估 libmpv：格式/滤镜能力强，但需额外维护 Windows 原生 DLL 分发、窗口嵌入和 IPC 生命周期。Qt 已包含成熟媒体后端，与 UI 共用部署链，因此第一版选 Qt。播放器封装于 `player.py`，若 Windows 特定格式兼容性测试要求替换内核，可独立替换。

采用系统 Qt Widgets + 自绘海报卡片，避免附加 Chromium 和本地 HTTP 服务。界面深色统一，保留原生输入/文件选择习惯。海报只使用真实缓存图片；空库不填演示影片。

## 代价与边界

- 大型库查询采用批量加载与虚拟绘制；不宣称百万级库性能。
- 本环境为 Linux，已能验证 Qt FFmpeg 实际视频解码；Windows 音频输出、硬件加速、DPI、系统安装仍须 Windows CI/实机验收。
- PySide6/Qt/FFmpeg 使用 LGPL 等许可证，Windows 分发保留对应许可证及动态库；不打包来源不明或禁用签名验证的二进制。
- 初版不提供系统托盘守护服务：定期发现仅在程序运行时执行。
- 优先接入 TVmaze（用户确认），另提供通用 JSON 协议和可选公开电影目录插件。真实网站逻辑全部位于插件目录，核心不识别网站 HTML。
