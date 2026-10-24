# 可下载安装包 · Lumen 0.4.7

[**v0.4.7 Release**](https://github.com/sleeper-lfy/my-jellyfin/releases/tag/v0.4.7) 已发布，EXE 与 APK 已从公开链接重新下载并核对大小 / SHA-256。[更新说明](../docs/releases/0.4.7.md) · [功能对照](../docs/basic-feature-audit.md)。

- [Windows 完整 EXE](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.7/Lumen-Setup-x64.exe)：Windows 10/11 x64，直接安装。
- [Android 完整 APK](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.7/Lumen-android-debug.apk)：Android 8.0+，versionCode 10，同签名可覆盖安装。
- [原始 Windows 构建](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/40062702407) 的 Windows job 完成 219 项测试与安装 / 启动 / 卸载验证。末尾 Git 回写失败后，经[交付恢复](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/40063590711)复用原产物，随后[统一发布](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/40063761005)。

本版新增排序、三态观看筛选、手动观看管理、按季选集、倍速、连播开关、队列编辑与全屏剧照；PC 增加批量操作 / 仅移出条目 / 路径重定位，Android 增加共享智能片单与返回位置保留。

## Windows 分片备份

本目录保存同一 EXE 的五个校验分片。下载全部 `Lumen-Setup-x64.exe.part*`、`windows-installer.json` 和 `Prepare-Installer.ps1` 后，在该目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-Installer.ps1
```

脚本校验并合并生成 **Lumen-Setup-x64.exe**（约 192.3 MiB）。Release 与 Actions 中的 EXE 已是完整单文件，无需合并。安装器包含 libmpv、Qt 和 FFmpeg，不需开发环境；卸载不删除资料库或媒体。

## 验证记录

- `windows-installer.json` / `android-build.json`：实际构建源码、文件大小与 SHA-256。两端构建源码为 `4e17fb742cb7bd095b4235cbcb9b3a34880d0c28`。
- `package-status.json`：Windows 构建、219 项测试与交付恢复证据；打包阶段的 `release_published: false` 不代表后续未发布。
- `package-download-verification.json`：Git 获取的 EXE 分片重组校验及公开 APK 下载校验。
- `release-status.json` / `release-download-verification.json`：v0.4.7 发布与两个公开安装包下载校验；发布标签提交另行记录，应用与构建输入已核对一致。

Android 55 项测试、lint、版本与同证书签名校验通过。Windows 原位自动升级、设备显卡和不同 DPI，以及 Android 真机解码 / HDR / VR 长时间播放仍需对应设备验收。Windows 安装器未进行商业代码签名，APK 为开发测试签名。旧源码 / 截图 ZIP 仅用于追溯，不是本版安装器。
