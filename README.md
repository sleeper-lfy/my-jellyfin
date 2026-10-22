# Lumen · 私人光影库

Windows 本地影音管理软件：真实文件扫描与播放、电影/整部电视剧/其他目录、插件刮削、安全整理、完整候选随机队列、个人评分与统计、女演员墙、可解释推荐和新片发现。无需云账号。

采用 PySide6 + Qt FFmpeg 播放后端 + SQLite。所有页面读取本地真实数据，空库不伪造影片、评分或观影记录。优先站点插件为用户指定的 TVmaze。

## 下载

- 源码：仓库页面点击 **Code → Download ZIP**。
- Android APK：[Android 构建记录](https://github.com/sleeper-lfy/my-jellyfin/actions/workflows/android.yml)，打开成功的运行，在 **Artifacts** 下载 `Lumen-android-debug`，解压后安装 APK。
- Windows 程序：[Windows 构建记录](https://github.com/sleeper-lfy/my-jellyfin/actions/workflows/windows.yml)，打开成功的运行，在 **Artifacts** 下载 `Lumen-windows-x64`。

推送会自动触发构建；首次产物需要等待工作流成功。下载 Actions 产物通常需要登录 GitHub。Android 为开发测试签名，云构建与此前本地 APK 的签名可能不同；若覆盖安装提示签名冲突，需卸载旧版后安装并重新填写连接信息。

## Windows 安装与启动

需要 Windows 10/11 x64、Python 3.12、FFmpeg 与 FFprobe（两个程序加入 PATH）。可通过已安装的 Winget 获取 Python/FFmpeg，或从各项目官方渠道安装；保持包签名/校验验证。

```powershell
cd my-jellyfin
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock
.venv\Scripts\python -m pip install --no-deps -e .
.venv\Scripts\python -m lumen
```

也可运行 `scripts/start-windows.ps1`。默认数据目录 `%LOCALAPPDATA%\Lumen`；`--data-dir D:\MyLumenData` 可自定义。`LUMEN_DATA_DIR` 环境变量也可覆盖。相同目录使用单实例锁。

## 实际使用

1. 点击导入或拖入一个文件夹，选择电影/电视剧/其他；扫描所有子目录，默认引用原文件。电视剧推荐文件名 `剧名.S01E01.mkv`，也支持 `剧名/Season 1/01 标题.mp4`，未识别的季集会记录失败原因。
2. 双击卡片查看详情，继续播放或双击具体集。空格暂停/继续，内嵌字幕和音轨可选；自动读取同名外挂 SRT/ASS/SSA/VTT，也可手选。字幕转换保留文本和时间，不承诺完整 ASS 特效渲染。
3. 设置 → 插件 → 安装 `plugins/tvmaze`，检查声明的域名后启用。关键词搜索或粘贴 TVmaze 详情页，确认候选再入库；影片来源按钮可打开浏览器。
4. 设置 → 导入规则，可指定分区自动刮削插件和整理目标。**保存带目标的规则需要确认，之后唯一匹配成功会移动原文件。** 未匹配/多候选进入任务列表；也可在详情中手动整理并查看文件计划。
5. 全局搜索或组合筛选后创建随机队列。全部匹配对象等概率洗牌，不局限当前显示页；整部电视剧算一个对象。上一/下一作品与剧内下一集分开，队列结束停止，重启可继续。
6. 电影/电视剧可评 1–10 分、收藏、想看或不感兴趣。女演员墙仅包含显式女性演员，均分排除未评分、同作品多版本只计一次。
7. 发现页刷新插件数据，按来源/分类筛选，只提供资料与来源网址，无资源下载/购买。定期刷新仅在程序运行时执行。
8. 统计页展示实际观看时间、严格超过 600 秒的有效播放、日周月年趋势、偏好和年报。暂停、缓冲与跳转不增加观看时间。

## Android 局域网客户端

已增加原生 Android 客户端（Android 8.0+）。在电脑端设置 → 局域网 / Android 中启用服务，手机填写电脑局域网地址与访问密钥，即可浏览媒体、播放视频并同步观看记录。安卓播放器使用 LibVLC，支持硬件优先、软件解码兜底和手动切换，可选择音轨与字幕。安装、构建和连接说明见 [Android 文档](docs/android.md)。

## 数据安全

- 文件操作不静默覆盖，跨卷先复制、同步并 SHA-256 校验，成功后才删除源文件。失败在任务页重试。
- 元数据字段可锁定。个人评分和站点评分独立。
- 设置中支持数据库备份和恢复；恢复前自动备份当前库。数据库备份不包含视频、海报或插件；完整迁移须另外备份数据目录与视频。
- JS 插件在独立进程中运行，无文件/进程/网络原生 API；宿主提供限定域名、预算和代理的 GET 请求。不是任意 Python 插件执行器。

## 测试与打包

```powershell
.venv\Scripts\python -m pytest -q
./scripts/build-windows.ps1
```

Windows 打包输出 `dist\Lumen\Lumen.exe` 和 `dist\Lumen-windows-x64.zip`，使用 onedir 保留可替换的动态库。包含 FFmpeg/FFprobe 和插件示例，必须在 Windows 上构建。`.github/workflows/windows.yml` 定义测试、打包和 artifact；本次尚未在远端执行该工作流。

Linux 云开发：

```bash
bash scripts/setup-cloud.sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=offscreen .venv/bin/python -m lumen --smoke --data-dir .local/smoke
# 有桌面显示时：
.venv/bin/python -m lumen
```

Linux 运行可验证核心逻辑、真实解码和 UI，但不代表 Windows 音频、驱动和安装兼容性。当前验证范围和限制见 [进展记录](docs/progress.md)。

## 文档

[需求](docs/requirements.md) · [技术选型](docs/architecture-decision.md) · [架构](docs/architecture.md) · [插件开发](docs/plugin-development.md) · [UI 规范](docs/ui-design.md) · [阶段验收](docs/implementation-plan.md) · [第三方许可](THIRD_PARTY_NOTICES.md)
