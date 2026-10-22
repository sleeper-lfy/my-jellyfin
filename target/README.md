# 可下载安装包

## Android

下载 `Lumen-android-debug.apk` 后安装，SHA-256 校验值见同名 `.sha256` 文件。当前为已本地构建验证的 LibVLC 测试版，Android 8.0+，约 96 MiB。

## Windows EXE 安装包

优先从 [Releases](https://github.com/sleeper-lfy/my-jellyfin/releases) 下载 **Lumen-Setup-x64.exe**，双击安装。支持 Windows 10/11 x64，包含 Python/Qt 和 FFmpeg，不需额外安装开发环境。安装位置默认为当前用户的 `%LOCALAPPDATA%\Programs\Lumen`，可创建桌面和开始菜单快捷方式，并支持卸载。卸载不删除媒体或 `%LOCALAPPDATA%\Lumen` 资料库。

Windows 工作流会先运行测试、打包程序，再静默安装、验证安装后的程序和卸载；成功后才发布 Releases 并提交到本目录。**当前目录没有 `windows-installer.json` 时，代表安装包尚未交付；构建脚本不是安装包。**

本目录的交付方式：

- 小于 99 MiB：直接提供 `Lumen-Setup-x64.exe`。
- 更大时：提供 `.exe.part001` 等分片及 `windows-installer.json`。下载全部分片后运行以下命令，校验并合并出同一个 EXE，再双击安装：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-Installer.ps1
```

Releases 中的 EXE 始终是完整单文件，不需要合并。开发版本尚未进行商业代码签名。

构建状态：https://github.com/sleeper-lfy/my-jellyfin/actions/workflows/windows.yml
