# 可下载安装包 · Lumen 0.4.10

[**v0.4.10 Release**](https://github.com/sleeper-lfy/my-jellyfin/releases/tag/v0.4.10) 已发布，EXE 和 APK 均已从公开链接重新下载校验。[更新说明](../docs/releases/0.4.10.md)。

- [Windows 完整 EXE](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.10/Lumen-Setup-x64.exe)：Windows 10/11 x64。
- [Android 完整 APK](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.10/Lumen-android-debug.apk)：Android 8.0+，versionCode 13，与旧版同签名。
- [Windows 测试 / 构建 / 交付](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/40164654926) · [两端 Release 发布](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/40165237425)。

标签和演员筛选可逐级返回来源页面；推荐 / 发现与首页同级，详情封面支持放大查看，演员头像可通过插件匹配。媒体库和筛选读取、播放记录及大图解码移到后台；修复已复现的 SQLite 争锁、Qt 兼容音频互锁和 Windows 筛选任务生命周期异常，新增自动卡顿日志。

## Windows 分片备份

下载全部 `Lumen-Setup-x64.exe.part*`、`windows-installer.json` 和 `Prepare-Installer.ps1`，在该目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-Installer.ps1
```

校验后生成 **Lumen-Setup-x64.exe**（约 192.5 MiB）。Release / Actions 提供同一完整 EXE，无需合并。安装器包含 libmpv、Qt 和 FFmpeg，卸载不删除资料库或视频。

## 验证记录

- Windows 261 项测试，0 失败 / 错误 / 跳过；安装 / 启动 / 卸载、程序与插件 worker 验证通过。
- Android 63 项测试、lint、构建、同证书签名、版本与 zipalign 校验通过。
- `windows-installer.json` / `android-build.json`：构建源码 `f1ebfb5c05e66328de2c50ff760396415199f4ff`、大小及 SHA-256。
- `package-status.json`：成功构建和打包交付。打包阶段 `release_published: false` 的后续发布结果见 `release-status.json`。
- `package-download-verification.json`：Git 获取的全部 EXE 分片校验 / 重组 / PE 签名检查及公开 APK 校验。
- `release-download-verification.json`：两个公开 Release 安装包的完整 SHA-256 及 PC 更新检测校验。

Windows 不同 DPI / 显卡和 Android 真机解码 / HDR / VR 长时播放仍需设备验收；头像站点的实际联网在此云环境受限，详情见更新说明。
