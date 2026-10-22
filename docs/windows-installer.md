# Windows EXE 安装包

安装文件名为 `Lumen-Setup-x64.exe`，使用 Inno Setup 6 包装已验证的 Windows PyInstaller onedir 程序。支持 Windows 10/11 x64，包含运行所需 Python、Qt、FFmpeg 和 FFprobe。

## 下载和安装

Windows 构建成功后，从仓库 [Releases](https://github.com/sleeper-lfy/my-jellyfin/releases) 下载完整 EXE，双击打开安装向导。默认安装到 `%LOCALAPPDATA%\Programs\Lumen`，无需管理员权限；提供开始菜单快捷方式和可选桌面快捷方式。可以在 Windows“已安装的应用”中卸载。

资料库仍位于 `%LOCALAPPDATA%\Lumen`，媒体保持原路径；卸载程序不删除这些文件。默认安装目录与资料库不同，不要手动将两者设置到同一目录。更新已有安装时使用同一个安装目录，先退出正在运行的 Lumen。

同一安装包还会写入仓库 `target`：小于 99 MiB 时直接保存 EXE，更大时按 48 MiB 分片，使用 `target/Prepare-Installer.ps1` 校验并合并。Releases 提供的始终是完整 EXE。

开发版目前未配置商业代码签名。Windows 原生构建/安装测试成功之前，不能把构建脚本或 Linux 产物当成已交付的安装包。

## Windows 本地构建

安装 Python 3.12、FFmpeg 和 Inno Setup 6，随后在仓库目录运行：

```powershell
./scripts/build-windows.ps1
./scripts/build-installer-windows.ps1
./scripts/verify-installer-windows.ps1
```

产物：`dist/installer/Lumen-Setup-x64.exe` 和 `.exe.sha256`。验证脚本会在独立测试目录静默安装、验证安装后的 UI 和插件 worker，再静默卸载；不会使用实际个人媒体库。

GitHub Windows 工作流执行相同过程，测试成功后才发布 Releases 并提交 `target`。失败时可在 Actions 下载 `windows-build-diagnostics` 检查安装日志和测试结果。工作流需要 `contents: write` 才能创建 Release 和提交安装包；仓库禁止工作流写入时，构建产物仍可从成功上传的 Actions Artifact 下载。
