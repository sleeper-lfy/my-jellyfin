# 可下载安装包

## 0.4.4 发布构建

Windows + Android 正在执行明确授权的统一发布。新 APK 为 0.4.4 / versionCode 7；Windows 安装器完成验证后同步更新本目录并上传 [v0.4.4 Release](https://github.com/sleeper-lfy/my-jellyfin/releases/tag/v0.4.4)。状态以 `release-status.json` 的 tag 与结果为准。下方为历史交付记录，不代表新 Windows 安装器已完成。

本版包含导入、全屏、书签和内存优化，以及 Android GitHub 更新、VR 陀螺仪串轴修复和蓝牙上一集 / 下一集。[更新说明](../docs/releases/0.4.4.md)。

## 0.4.3 打包交付（不发布 Release）

本次按明确请求打包，源码为 `91f07502e6afd58a46375082f9f487ab15e51eb9`。新增目录监控、播放诊断、字幕调节、时间书签、按视频保存 VR 设置、手机遥控、媒体库体检和后台队列管理；没有增加新的 GPU 增强算法、安卓离线观看或 2D VR。

- [Android APK](Lumen-android-debug.apk)：0.4.3 / versionCode 6，已构建，33 项测试、lint、签名与 ZIP 对齐检查通过，与上一版签名相同，可覆盖安装。
- Windows EXE：已完成 [构建、测试和安装验证](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/39930617864)，180 项测试全部通过。下载本目录的 4 个 `.exe.part*` 分片、`windows-installer.json` 和 `Prepare-Installer.ps1`，运行脚本合并得到完整安装包（约 192 MiB）；也可登录 GitHub 后从该运行的 `Lumen-windows-x64` Artifact 下载完整 EXE。

本次仅提交安装包到本目录并保存 Actions Artifacts，不创建或更新 Release。下方 v0.4.2 链接继续指向历史版本。

两端源码与校验值已核对，Windows 分片已重新合并并核对完整 EXE，APK 已从公开链接重新下载校验；见 `package-download-verification.json`。[0.4.3 更新说明](../docs/releases/0.4.3.md)。

## 0.4.2 统一发布

完整 Windows EXE 和 Android APK 使用同一个 [v0.4.2 Release](https://github.com/sleeper-lfy/my-jellyfin/releases/tag/v0.4.2) 交付，附带各自的 SHA-256。发布流程在 Windows 测试、打包、安装与卸载检查通过后统一上架，不会把旧 EXE 当作新版上传。本目录的 `windows-installer.json`、`android-build.json` 记录实际文件对应的源码和校验值；`release-status.json` 记录远端发布结果。

已完成公开下载与校验：[完整 EXE（约 191 MiB）](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.2/Lumen-Setup-x64.exe) · [Android APK（约 96 MiB）](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.2/Lumen-android-debug.apk)。两者均已重新下载并核对 SHA-256，记录见 `release-download-verification.json`。

本版包含 UI 调整、默认下载目录与下载后入库、详情刮削候选、局域网发现和 PC 真全屏修复，不包含 2D 视频 VR 观看功能。详细说明见 [0.4.2 更新记录](../docs/releases/0.4.2.md)。下方保留历史交付记录，判断版本时以当前构建清单为准。

## Android

下载 `Lumen-android-debug.apk` 后安装，SHA-256 校验值见同名 `.sha256` 文件。当前为 0.4.3 LibVLC + VR180 测试版（已本地构建、单元测试和 lint 验证），Android 8.0+，约 96 MiB。

## Windows EXE 安装包

当前 0.4.3 从本目录分片合并，或从上方 Actions Artifact 获取 **Lumen-Setup-x64.exe**；[Releases](https://github.com/sleeper-lfy/my-jellyfin/releases) 中仍是历史 0.4.2。双击安装器安装。支持 Windows 10/11 x64，包含 Python/Qt 和 FFmpeg，不需额外安装开发环境。安装位置默认为当前用户的 `%LOCALAPPDATA%\Programs\Lumen`，可创建桌面和开始菜单快捷方式，并支持卸载。卸载不删除媒体或 `%LOCALAPPDATA%\Lumen` 资料库。

Windows 工作流会先运行测试、打包程序，再静默安装、验证安装后的程序和卸载；成功后提交到本目录，只有明确请求发布时才更新 Releases。**当前目录没有 `windows-installer.json` 时，代表安装包尚未交付；构建脚本不是安装包。**

本目录的交付方式：

- 小于 99 MiB：直接提供 `Lumen-Setup-x64.exe`。
- 更大时：提供 `.exe.part001` 等分片及 `windows-installer.json`。下载全部分片后运行以下命令，校验并合并出同一个 EXE，再双击安装：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-Installer.ps1
```

Actions Artifact 和历史 Releases 中的 EXE 是完整单文件，不需要合并。开发版本尚未进行商业代码签名。

构建状态：https://github.com/sleeper-lfy/my-jellyfin/actions/workflows/windows.yml

## 本次界面修复版本（360138a）

- [源码包](Lumen-source-360138a.zip)：对应本次导入进度、NFO、播放器和媒体库界面修复，解压后按 README 运行或构建。
- [界面截图包](Lumen-UI-review-360138a.zip)：8 张实际运行截图，使用测试媒体。
- 两个 ZIP 均附带 `.sha256` 校验文件。源码包不是 Windows 安装程序。

下载 Windows 安装包时，请检查 `windows-installer.json` 的 `source_commit` 是否为 `360138a50755dd6023a287836204c74ef804c519` 或包含它的后续版本；旧版本不包含这次修复。

## 快速导入与安全退出版本（658d19a）

[下载对应源码包](Lumen-source-658d19a.zip)。本版新增快速增量导入、后台补充媒体信息，以及扫描中安全退出。Windows 安装包的 `source_commit` 应为 `658d19a734b093761d550865b32c0ce58141ac31` 或包含它的后续版本；源码 ZIP 不是安装程序。

VR电影：桌面导入时选择“VR电影”，或海报右键移入分类。安卓打开后自动使用 VR180 左右 3D；其他分类使用普通播放。标准／鱼眼投影、陀螺仪、单屏／双眼与立体声说明见 [android-vr.md](../docs/android-vr.md)。安卓 VR 仍需真机观看确认。

0.4.0 同时包含剧照画廊（插件 `stills`、本地 NFO 与单集剧照）、下载资源列表（磁力交给系统下载器，桌面直链支持进度和取消）、新版 Lumen 图标。Windows 原生 libmpv GPU 播放与可选锐化见 [mpv-runtime.md](../docs/mpv-runtime.md)，插件字段见 [plugin-development.md](../docs/plugin-development.md)。

本轮完整源码：[Lumen-source-de453a3.zip](Lumen-source-de453a3.zip)，校验文件：[SHA-256](Lumen-source-de453a3.zip.sha256)。源码提交 `de453a3`，不包含旧安装包和本地媒体。Windows + Android 将发布在同一个版本的 GitHub Release 中。

Android 0.4.1：安全区域内的浮层控制、按视频显示比例自动横竖屏、VR 一键回正及缩放、HID / AVRCP 蓝牙控制和按设备自定义映射，见 [android-vr.md](../docs/android-vr.md)。

Windows 0.4.1：剧照与发现详情资源加载、本地 NFO 图片手动补充／覆盖、无痕打开来源、大库后台读取及图片异步解码、首页垂直滚轮修复。新版安装包须以本目录 windows-installer.json 的 source_commit 和 Release 校验值为准。
