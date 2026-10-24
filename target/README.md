# 可下载安装包 · Lumen 0.4.9

[**v0.4.9 Release**](https://github.com/sleeper-lfy/my-jellyfin/releases/tag/v0.4.9) 已发布，EXE 和 APK 均已从公开链接重新下载校验。[更新说明](../docs/releases/0.4.9.md)。

- [Windows 完整 EXE](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.9/Lumen-Setup-x64.exe)：Windows 10/11 x64。
- [Android 完整 APK](https://github.com/sleeper-lfy/my-jellyfin/releases/download/v0.4.9/Lumen-android-debug.apk)：Android 8.0+，versionCode 12，与旧版同签名。
- [Windows 测试 / 构建 / 交付](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/40068831314) · [两端 Release 发布](https://github.com/sleeper-lfy/my-jellyfin/actions/runs/40069351635)。

播放器直接评分、喜欢／收藏、不喜欢。按用户确认，喜欢就是收藏，共用一份状态，与不喜欢互斥；评分独立。普通播放、全屏及手机 VR 使用相同入口，保存不重启视频。

## Windows 分片备份

下载全部 `Lumen-Setup-x64.exe.part*`、`windows-installer.json` 和 `Prepare-Installer.ps1`，在该目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-Installer.ps1
```

校验后生成 **Lumen-Setup-x64.exe**（约 192.3 MiB）。Release / Actions 已提供完整 EXE，无需合并。安装器包含 libmpv、Qt 和 FFmpeg，卸载不删除资料库或视频。

## 验证记录

- Windows 225 项测试，0 失败 / 错误 / 跳过；安装 / 启动 / 卸载、程序与插件 worker 验证通过。
- Android 59 项测试、lint、构建、同证书签名、版本与 zipalign 校验通过。
- `windows-installer.json` / `android-build.json`：构建源码 `0400d9e247aae3108eb497a02748ae4ef4fc8376`、大小及 SHA-256。
- `package-status.json`：本次成功构建和打包交付。打包阶段 `release_published: false` 的后续发布结果见 `release-status.json`。
- `package-download-verification.json`：Git 获取的全部 EXE 分片校验 / 重组 / PE 签名检查及公开 APK 校验。
- `release-download-verification.json`：两个公开 Release 安装包的大小和完整 SHA-256 校验。

0.4.8 为采用独立喜欢的历史版本，最终按用户确认以 0.4.9 为准。Windows 不同 DPI / 显卡和 Android 真机解码 / HDR / VR 长时播放仍需设备验收。Windows 安装器未商业签名，APK 使用原开发测试签名。
