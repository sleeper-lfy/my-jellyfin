# 可下载安装包 · Lumen 0.4.6

先完成打包交付，随后按明确要求统一发布 [v0.4.6 Release](https://github.com/sleeper-lfy/my-jellyfin/releases/tag/v0.4.6)，复用本目录已验证的原始文件。[0.4.6 更新说明](../docs/releases/0.4.6.md) · [功能入口与实际截图](../docs/pc-maintenance.md)。

- [Windows 完整 EXE](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.6/Lumen-Setup-x64.exe)，直接安装，无需分片合并。
- [Android 完整 APK](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.6/Lumen-android-debug.apk)，0.4.6 / versionCode 9，Android 8.0+，签名与上一版一致，可覆盖安装。
- [原始打包运行](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/40058565831) 的 Lumen-windows-x64 Artifact 与下方 target 分片保留相同产物。

Windows 包含电视剧按文件夹归集、任务窗口后台分页、PC GitHub 更新检测 / 可选自动安装、剧照预览稳定性修复。Android 保留 VR 转向、视频切换、蓝牙及手机控制 Windows 关机等现有功能。

## Windows 分片备份

GitHub 单文件限制下，本目录保存同一 EXE 的校验分片。下载全部 `Lumen-Setup-x64.exe.part*`、`windows-installer.json` 和 `Prepare-Installer.ps1` 后，在下载目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-Installer.ps1
```

脚本校验并合并得到 **Lumen-Setup-x64.exe**（约 192.1 MiB）。Actions 中的 EXE 为完整单文件，无需合并。Windows 10/11 x64，包含 libmpv、Qt 和 FFmpeg，不需安装开发环境；安装位置默认当前用户目录，卸载不删除资料库或媒体。

## 验证与历史交付

Windows 已完成 211 项测试、打包程序 / 插件 worker、安装 / 启动 / 卸载检查。Windows 分片已校验并重新合并，与完整 SHA-256 和 PE 头一致；APK 已从 GitHub 公开地址重新下载核对。真实 Windows 原位自动升级及显卡上的闪烁表现仍需设备验收。

- `package-status.json`：0.4.6 最初仅打包交付的历史状态，后续发布另行记录。
- `windows-installer.json` / `android-build.json`：本次两端源码、文件大小与 SHA-256。
- `package-download-verification.json`：本次 target 文件下载及重组校验。
- `release-status.json` / `release-download-verification.json`：本次 v0.4.6 发布及公开下载校验。构建源码保留原始提交，发布标签提交另外记录，应用与构建输入已核对一致。
- `release-upload.json`：更早 Windows 交付记录。

历史 [v0.4.5 Release](https://github.com/sleeper-lfy/my-jellyfin/releases/tag/v0.4.5) 不包含本次 PC 修复。PC 更新检测可读取本次已发布的稳定 Release。开发安装包尚未进行商业代码签名。旧源码 / 截图 ZIP 只用于追溯，不是本版安装器。
