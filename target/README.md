# 0.4.6 打包构建（不发布 Release）

按明确请求构建 Windows EXE 和 Android APK。新版 APK 已完成构建、54 项测试、lint、签名与版本检查，版本 0.4.6 / versionCode 9，可覆盖安装。Windows 正在验证构建；实际完成状态见 package-status.json 的 version / windows / delivery。本次不发布 Release，下面保留 0.4.5 历史说明，不能据此判断新 EXE 已完成。

[0.4.6 安装包说明](../docs/releases/0.4.6.md)。

# 可下载安装包 · Lumen 0.4.5

[**v0.4.5 Release**](https://github.com/sleeper-lfy/my-jellyfin/releases/tag/v0.4.5) 已统一发布两端安装包及 SHA-256。

- [Windows x64 完整安装包：Lumen-Setup-x64.exe](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.5/Lumen-Setup-x64.exe)，Windows 10/11 x64，包含 libmpv、FFmpeg 和 Qt。
- [Android 完整安装包：Lumen-android-debug.apk](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.5/Lumen-android-debug.apk)，Android 8.0+，versionCode 8。也可下载[本目录 APK](Lumen-android-debug.apk)。签名与 0.4.4 相同，可覆盖安装；54 项测试、lint、签名、ZIP 对齐及版本检查通过。

本版修复 VR 大幅抬头的左右转向与视频切换，补齐播放页上一 / 下个视频按钮，并增加手机控制 Windows 关机。[更新说明](../docs/releases/0.4.5.md) · [VR 与蓝牙](../docs/android-vr.md)。

关机需要两端升级，并在 PC 设置 → 局域网 / Android 中启用服务、手机遥控和允许手机关机。手机确认后有 15 秒倒计时，两端均可取消，不强制结束未保存的程序。

## Windows 仓库备份

Release 中的 EXE 是完整单文件，直接下载并安装。本目录因为 GitHub 单文件限制保存同一安装器的校验分片。下载全部 `Lumen-Setup-x64.exe.part*`、`windows-installer.json` 和 `Prepare-Installer.ps1`，在该目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-Installer.ps1
```

脚本校验并合并得到 `Lumen-Setup-x64.exe`。安装器默认为当前用户安装，可创建桌面 / 开始菜单快捷方式；卸载不删除媒体或资料库。开发版本尚未进行商业代码签名。

## 交付与验证记录

[本次 Windows 构建、安装和卸载验证及统一发布](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/39978714401) 已通过。`windows-installer.json` 与 `android-build.json` 记录各产物的源码、大小和 SHA-256。Android 先在源码提交构建，再将相同 Android 源码树及 APK 提交到发布标签；Windows 从该标签构建，发布时再次验证 APK 与该源码树匹配。

- `release-status.json`：v0.4.5 远端构建及发布结果。
- `release-download-verification.json`：本版公开 Release 安装包的下载与 SHA-256 校验。
- `package-status.json` / `package-download-verification.json`：0.4.3 仅打包交付的历史记录。
- `release-upload.json`：早期 Windows 交付的历史记录。

历史版本说明：[0.4.4](../docs/releases/0.4.4.md)、[0.4.3（仅打包）](../docs/releases/0.4.3.md)、[0.4.2](../docs/releases/0.4.2.md)。旧源码 / 截图 ZIP 保留用于追溯，不是本版安装程序。普通提交不自动发布，仅在用户明确要求后执行打包或发布。
