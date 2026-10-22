# 可下载安装包

## Android

下载 `Lumen-android-debug.apk` 后安装，SHA-256 校验值见同名 `.sha256` 文件。当前为已本地构建验证的 LibVLC 测试版，Android 8.0+，约 96 MiB。

## Windows

Windows Actions 构建并验证成功后，会自动向本目录提交：

- `windows-package.json`：来源提交和 SHA-256 校验值。
- `Lumen-windows-x64.zip.part001` 等分片：每片不超过 48 MiB，适应 GitHub 单文件大小限制。

**没有上述文件时，表示尚未交付 Windows 包，不能把脚本当成已构建程序。**

下载仓库 ZIP 并解压，确保 `target` 内的全部分片都在同一目录，然后在该目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Extract-Windows.ps1
```

脚本先校验每片和完整 ZIP，再解压到 `windows-提交号` 文件夹；运行其中的 `Lumen\Lumen.exe`。原始资料库不受影响。不要只下载第一个分片。

构建状态：https://github.com/sleeper-lfy/my-jellyfin/actions/workflows/windows.yml
