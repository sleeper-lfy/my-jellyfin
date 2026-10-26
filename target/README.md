# 可下载安装包 · Lumen 0.4.11

[v0.4.11 Release](https://github.com/sleeper-lfy/my-jellyfin/releases/tag/v0.4.11) 已发布，两个安装包均已通过公开下载重新校验。[更新说明](../docs/releases/0.4.11.md)。

- [Windows 完整 EXE](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.11/Lumen-Setup-x64.exe)：Windows 10/11 x64。
- [Android 完整 APK](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.11/Lumen-android-debug.apk)：Android 8.0+，versionCode 14，原签名覆盖安装。
- [Windows 构建及安装验证](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/40278428799) · [Release 发布](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/40279528110)。

新增透明字幕、发现名称/标签本地筛选及在线站点搜索、完整结果排序、Fans 作者文件夹归并。Android ASS 自带框及位图/烧录字幕限制见更新说明。

## Windows 分片备份

下载所有 `Lumen-Setup-x64.exe.part*`、`windows-installer.json` 和 `Prepare-Installer.ps1`，在同一目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-Installer.ps1
```

校验后生成完整 EXE（约 192.7 MiB）。Release 已提供同一完整文件，无需合并。卸载保留媒体库和视频。

## 验证

Windows 323 项测试，0 失败/错误/跳过；程序、插件 worker、安装/启动/卸载验证通过。Android 71 项、lint、构建、原证书签名、版本和 zipalign 校验通过。

构建源码 `504bc33c5b395227a7b443b0df2587e60c6719ae`。`windows-installer.json` / `android-build.json` 记录大小及 SHA-256；`package-status.json` 记录打包阶段，后续发布见 `release-status.json`。`package-download-verification.json` 记录每个分片和完整 EXE 重组/PE 检查；`release-download-verification.json` 记录两个公开下载及 PC 更新检测验证。

真实站点连通、Windows 驱动与 Android 真机仍需实际使用环境验收。
