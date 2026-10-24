# Android 局域网客户端

Lumen Android 是本项目服务端的原生客户端，最低 Android 8.0（API 26）。采用与桌面相同的 Jellyfin 风格：黑色背景、青色重点按钮、媒体分类、海报网格。使用 LibVLC 3.7.7 播放器，内置软件解码器。它连接 Lumen 的 API，不是 Jellyfin 协议客户端。

## 安装和连接

1. 安装 `Lumen-android-debug.apk`（开发测试签名）。Android 提示时，允许当前文件管理器安装此应用。
2. 在电脑端导入视频，打开 **设置 → 局域网 / Android**，勾选启动服务，默认端口 `8097`，点击应用。
3. 手机和电脑连接同一路由器。电脑防火墙允许 Lumen/Python 在专用网络接收入站连接；若需要手动规则，允许 TCP 8097（更改端口后相应调整）和用于自动发现的 UDP 8098。
4. 打开手机连接页会自动发现约 3 秒，点击地址旁的 **⌄** 下拉选择电脑；也可点“重新发现服务端”重试或手动输入地址，例如 `http://192.168.1.10:8097`，复制电脑设置中的完整访问密钥，连接。不要用 `localhost`、`127.0.0.1` 或 `0.0.0.0` 作为手机连接地址。
5. 可浏览电影/电视剧/VR电影/其他、搜索、收藏、推荐、查看详情，继续播放或选集；支持个人评分、想看、随机队列和观影统计。观看进度与电脑共用数据库。媒体库的 **筛选** 提供标签、演员和年份三个可输入的下拉框，候选来自该分类下的全部本地作品；多个条件同时生效，分页、推荐和随机队列遵循筛选，可一键清空。

发现只返回设备名称和 HTTP 端口，不传送访问密钥或媒体资料；选择地址后仍须输入电脑端访问密钥。UDP 广播被路由器或防火墙拦截时，手动输入仍可用。

电脑应用必须保持运行，电脑休眠、服务关闭或媒体盘离线时无法播放。访客 Wi-Fi 的设备隔离也会阻止连接。IP 变化后可在手机右上角菜单切换连接。连接凭据由 Android Keystore 加密保存，不包含在系统备份内。

视频按原格式传输，支持 Range 拖动、内嵌及同名外挂 SRT/VTT/ASS/SSA 字幕。默认自动模式优先硬件加速，LibVLC 可回落到软件解码；播放核心报错时客户端还会以软件模式重试一次，并保留播放位置。遇到花屏、黑屏或只有声音时，也可点 **解码 → 软件** 手动切换。手动选择会保存为下次播放的偏好，自动重试不会改变默认偏好。

播放界面使用覆盖在视频上的浮层控件；点画面唤出／收起，播放时闲置自动隐藏。全屏控件避开刘海和系统导航区域，横屏不再把多排按钮挤在视频下方。普通视频按解码器给出的显示宽高比自动选择横屏或竖屏，并考虑旋转信息和像素比例；方形视频用竖屏。可在 **播放设置 → 屏幕方向** 手动覆盖，VR 始终横屏。**−10 秒／+10 秒** 可点击跳转。画面上单指向右滑快进、向左滑后退；滑动显示目标时间，松手后跳转，整屏宽度最多调节 120 秒并限制在片头／片尾。VR 默认也支持横滑调进度，可在 VR 设置切回拖动转向；双指缩放不触发跳转。

蓝牙耳机、HID 遥控器与手柄控制及 VR 回正、缩放见 [VR 与按键映射](android-vr.md)。

播放器的 **音轨** 可选择配音或关闭声音，**字幕** 可切换/关闭内嵌和外挂字幕；进度条可拖动。软件解码扩大了不具备对应系统解码器的手机的格式覆盖，但高码率 4K、HEVC/AV1 10-bit 的流畅度仍依赖 CPU、散热与 Wi-Fi。HDR/Dolby Vision 的显示效果还取决于设备和输出路径；不承诺所有配置均能正确色调映射。当前没有转码或离线下载，也不支持 DRM 解密；损坏文件和复杂字幕特效仍需实际素材验证。切到后台暂停，返回继续；没有后台音频服务。

电脑导入额外识别 RM/RMVB、ASF、VOB、OGV、MTS、3GP/3G2、DIVX、F4V、M2V/M2T，仍须通过 FFprobe 的实际文件检查。扩展名只是容器提示，不代表内部编码。APK 同时包含 ARM64、ARMv7、x86 和 x86_64 原生解码库，因此比之前的播放器版本明显增大。

HTTP 用于可信家庭局域网，访问密钥提供鉴权，传输本身没有加密。不要把该端口映射至公网。所有 API，包括封面、字幕和视频，均要求 `Authorization: Bearer <密钥>`；URL 参数不能替代该请求头。服务默认关闭。

## 构建

用 Android Studio 打开 `android/`，安装 Android SDK Platform 36 和 Build Tools 35.0.0。使用 JDK 17 或 21。

```bash
cd android
./gradlew :app:assembleDebug :app:lintDebug :app:testDebugUnitTest
```

Windows 使用 `gradlew.bat`。输出 `android/app/build/outputs/apk/debug/app-debug.apk`。`local.properties`、SDK、Gradle 缓存、APK 和签名密钥不进入源码。Gradle Wrapper 固定 8.11.1 并校验分发包 SHA-256；依赖版本在构建文件固定。正式发布需要自行保管长期签名密钥；当前 APK 为开发测试版本。

普通 push / pull request 只编译验证、运行单元测试和静态检查，不生成 APK、不发布 Release。明确要求打包后，在 `.github/workflows/android.yml` 的 **Run workflow** 勾选 `package` 才生成 APK Artifact；同时勾选 `publish` 才上传 Release。只做源码验证可运行 `:app:lintDebug :app:testDebugUnitTest`。本地 Linux 云环境可使用 `scripts/setup-android-cloud.py` 安装校验后的工具，再使用 `scripts/build-android-cloud.py` 构建（需要已安装 Python 项目依赖和网络访问）。

## 服务接口 v1

| 方法与路径 | 用途 |
| --- | --- |
| GET `/api/info` | 协议版本和连接验证 |
| GET `/api/works` | 分页列表；kind、q、favorite、tag、actor、year、offset、limit |
| GET `/api/filters` | 完整本地媒体库的 tags / actors（含别名）/ years 候选；可按 kind 限定 |
| GET `/api/works/{id}` | 详情、文件、恢复播放位置 |
| GET `/api/works/{id}/cover` | 缓存封面 |
| GET/HEAD `/api/files/{id}/stream` | 视频，单段 Range；无效范围返回 416 |
| GET `/api/files/{id}/subtitles` | 同名字幕列表 |
| GET `/api/files/{id}/subtitles/{index}` | 字幕内容 |
| GET `/api/recommendations` | 推荐列表 |
| GET `/api/stats` | 共用观看统计 |
| POST `/api/works/{id}/personal` | rating、favorite、watchlist、disliked |
| POST `/api/works/{id}/downloads` | 按资源下标在电脑排队下载，完成后自动关联影视信息 |
| POST `/api/works/{id}/download-directory` | 保存该作品的电脑下载目录；留空恢复分类默认 |
| GET `/api/downloads/{task_id}` | 电脑端下载 / 入库进度 |
| POST `/api/works/{id}/import-downloads` | 检查已完成的外部下载并关联当前影视信息 |
| POST `/api/queue` | 对全部筛选结果洗牌，电视剧作为整体 |
| POST `/api/playback/start` | file_id，返回 session_id |
| POST `/api/playback/{id}/tick` | seq、position、playing、seeking、rate |
| POST `/api/playback/{id}/stop` | 最终状态及 completed |

播放状态每秒同步。服务端去重序号，仅在连续播放且位置增量合理时累计实际时间；暂停、跳转和长时间失联不累计。严格超过 600 秒才计为有效播放，与桌面规则一致。

可在已配置密钥的数据目录运行无界面服务：

```bash
python -m lumen --serve --data-dir /path/to/Lumen --port 8097
```

启动命令不会打印密钥。数据库恢复前必须关闭局域网服务，恢复后重新开启；如备份中的密钥不同，需要更新手机连接。

## 解码验证范围

已添加真实样本导入和服务端 HTTP 解码检查：H.264/AAC MP4、10-bit HEVC/E-AC-3 MKV、VP9/Opus WebM、AV1/FLAC MKV、MPEG-4/MP3 AVI、WMV2/WMA2 ASF、MPEG-2/AC-3 VOB、RealVideo 2 RM。这些检查使用 Linux FFmpeg，验证导入与传输，不等同于 Android LibVLC 真机验证。

客户端通过只监听本机回环地址的流式转发器向 LibVLC 供流，上游继续使用 Bearer 请求头鉴权；访问密钥不写入视频 URL。每次播放的本机地址有随机令牌，只能读取当前视频和字幕，保留 Range/HEAD，并拒绝重定向。单元测试覆盖字节完整性、鉴权、拖动范围、字幕、路径隔离、重定向和关闭。

真机验收应覆盖：上述实际编码的声音与画面、硬解失败软解重试、切换音轨/字幕、拖动后位置、后台恢复、4K 长时间播放，以及不同设备的 HDR 表现。目前尚未完成这组真机测试。

## 无痕打开网页

Android 0.4.1 的信息来源链接默认进入应用内无痕浏览页；关闭后清理 WebView 的缓存与页面历史，不启用 Cookie、DOM 存储、网页数据库或表单保存，也不把链接交给普通浏览器窗口。部分需要 Cookie／登录的网站可能无法正常使用。当前源码的下载资源按钮交给电脑服务端处理，使用电脑上的分类默认目录；HTTP 完成后自动加入当前影视库。磁力由电脑端配置的外部下载器处理，完成后可在手机点击检查入库。详见 [下载与影视入库](downloads.md)。

## GitHub 检查更新（0.4.4）

连接页点击“检查客户端更新”，或媒体库更多菜单 → 检查更新。无需连接电脑；同时查看 GitHub Releases 和仓库 target 的构建清单，选择更高版本。手动下载后显示进度，校验大小、SHA-256、包名、版本与当前签名，再交给系统确认安装。首次可能需要为 Lumen 授予安装应用的系统权限。不静默安装、不把媒体服务器密钥发送到 GitHub，也不把 APK 整体读入内存。取消会清理临时文件，失败可重新下载。完整流程及限制见 [稳定性与更新修复](pc-stability-and-updates.md)。


## 0.4.7 媒体库与播放补全

更多菜单提供排序、智能片单及播放队列；排序保存为手机默认设置，智能片单与 PC 共用。已加载列表从详情返回时保留分页和滚动位置。筛选支持未开始 / 观看中 / 已完成。电视剧详情按季选集，长按单集可标记已看或重置；作品级观看状态按钮支持整部操作和从头播放。

播放设置新增 0.5–2 倍速及自动下一集开关。详情可加入手机播放队列；队列支持上下移、移除、播放指定作品和循环模式，仍以整部剧为一个对象。剧照点击全屏，双指缩放、放大后拖动、缩小时左右滑动切换；单集剧照使用相同交互。


## 0.4.8 播放中评分与偏好

点画面唤出控制栏，使用“评分 / 收藏 / 喜欢 / 不喜欢”。喜欢与收藏独立，喜欢和不喜欢互斥且可取消。操作异步保存到 PC，不退出播放器、不重启视频；评分可清除，整剧的各集共用作品级评分 / 偏好。切换作品会刷新按钮；保存失败会提示重试，不显示成功状态。普通视频和 VR 的入口相同，独立喜欢需同版 PC 服务端。


## 0.4.9 最终确认：喜欢就是收藏

播放器改为评分、喜欢／收藏、不喜欢三个入口。喜欢与收藏共用一份状态，和不喜欢互斥；评分独立。重复点击可取消，仍在后台保存，不退出或重载视频。0.4.8 的独立状态说明为历史记录，新版本以本节和 [0.4.9](releases/0.4.9.md) 为准。
