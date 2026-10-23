# 可下载安装包 · Lumen 0.4.4

[**v0.4.4 Release**](https://github.com/sleeper-lfy/my-jellyfin/releases/tag/v0.4.4) 已统一发布两端安装包及 SHA-256。

- [Windows x64 完整安装包：Lumen-Setup-x64.exe](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.4/Lumen-Setup-x64.exe)，Windows 10/11 x64，包含 libmpv、FFmpeg 和 Qt。
- [Android 完整安装包：Lumen-android-debug.apk](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.4/Lumen-android-debug.apk)，Android 8.0+，versionCode 7。也可下载[本目录 APK](Lumen-android-debug.apk)。签名与 0.4.3 相同，可覆盖安装；46 项测试、lint、签名、ZIP 对齐及版本检查通过。

本版包含导入、重复导入弹窗、全屏、书签与内存修复，以及 Android GitHub 更新、VR 陀螺仪串轴修复、灵敏度和平滑设置、蓝牙上一集 / 下一集。[本版更新说明](../docs/releases/0.4.4.md) · [页面截图和验证范围](../docs/pc-stability-and-updates.md)。

## Windows 仓库备份

Release 提供的 EXE 是完整单文件，直接下载并安装。本目录因为 GitHub 单文件限制保存同一安装器的校验分片。下载全部 `Lumen-Setup-x64.exe.part*`、`windows-installer.json` 和 `Prepare-Installer.ps1`，在该目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-Installer.ps1
```

脚本校验并合并得到 `Lumen-Setup-x64.exe`。安装器默认为当前用户安装，可创建桌面 / 开始菜单快捷方式；卸载不删除媒体或资料库。开发版本尚未进行商业代码签名。

## 交付与验证记录

[本次 Windows 构建、安装和卸载验证及统一发布](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/39972260074) 已通过。`windows-installer.json` 与 `android-build.json` 记录各产物的源码、大小和 SHA-256。Android 先在源码提交构建，再将相同 Android 源码树及 APK 提交到发布标签；Windows 从该标签构建，发布时再次验证 APK 与该源码树匹配。

- `release-status.json`：v0.4.4 远端构建及发布结果。
- `release-download-verification.json`：本版公开 Release 安装包的下载与 SHA-256 校验。
- `package-status.json` / `package-download-verification.json`：0.4.3 仅打包交付的历史记录。
- `release-upload.json`：早期 Windows 交付的历史记录。

历史版本说明：[0.4.3（仅打包）](../docs/releases/0.4.3.md)、[0.4.2](../docs/releases/0.4.2.md)。旧源码 / 截图 ZIP 保留用于追溯，不是本版安装程序。普通提交不自动发布，仅在用户明确要求后执行打包或发布。
