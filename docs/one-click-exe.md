# 一键生成 Windows EXE 安装包

在项目目录双击 **`Build-PC.cmd`**。它会依次执行完整测试、构建桌面程序、生成安装器，以及独立目录的安装 / 启动 / 卸载验证。只有全部通过才显示 `SUCCESS`。

## 你现在这台电脑

项目位置：`E:\workspaces\my-jellyfin`。本次已经检测到以下工具，可直接双击根目录的 `Build-PC.cmd`：

- Python：`E:\environment\miniconda3\envs\lumen\python.exe`，Conda 的 Python 3.12 x64。
- FFmpeg / FFprobe：`E:\environment\ffmpeg\bin`。
- Inno Setup：项目内 `.local\tools\innosetup\ISCC.exe`。
- 7-Zip：项目内 `.local\tools\7zip\7z.exe`。

保持窗口打开，等待测试、压缩和安装验证完成。打包可能需要数分钟，首次还需要联网下载依赖和固定版本的播放器内核。完成后按任意键关闭窗口。

## 在哪里拿安装包

成功后使用：

| 文件 | 用途 |
| --- | --- |
| `dist\installer\Lumen-Setup-x64.exe` | 可直接分发、双击安装的完整安装包 |
| `dist\installer\Lumen-Setup-x64.exe.sha256` | 安装包 SHA-256 校验值 |
| `dist\Lumen-windows-x64.zip` | 便携版，完整解压后运行其中的 `Lumen\Lumen.exe` |

不要单独复制 `dist\Lumen\Lumen.exe`，它还需要同目录的 `_internal` 等文件。安装器会自动包含这些文件。

打包包含当前保存到磁盘的源码改动，无需先提交 Git。它不会推送代码、发布 Release、更新 `target` 备份或构建 Android。资料库、个人视频和访问密钥不会打入安装包。当前版本号来自项目现有配置，打包本身不自动升版。

## 换电脑或工具路径不同

准备 Windows 10 / 11 x64、Conda Python 3.12 x64、FFmpeg（含 FFprobe）、7-Zip，以及 Inno Setup 6。工具未准备好时，脚本会先停止，不会自动安装系统级软件。

新建专用 Conda 环境时，在已配置 Conda 的终端运行一次：

```powershell
conda create -n lumen python=3.12 -y
```

将根目录 `pc-build.example.json` 复制为 **`pc-build.local.json`**，用文本编辑器修改为这台电脑的实际路径。JSON 中 Windows 路径的反斜杠必须写成 `\\`：

```json
{
  "PythonPath": "E:\\environment\\miniconda3\\envs\\lumen\\python.exe",
  "CompilerPath": "E:\\workspaces\\my-jellyfin\\.local\\tools\\innosetup\\ISCC.exe",
  "SevenZipPath": "E:\\workspaces\\my-jellyfin\\.local\\tools\\7zip\\7z.exe",
  "FFmpegDirectory": "E:\\environment\\ffmpeg\\bin",
  "PipIndexUrl": "https://pypi.tuna.tsinghua.edu.cn/simple"
}
```

`PipIndexUrl` 可省略；省略时沿用该 Python 环境原有的下载配置。不要使用其他项目的专用 Conda 环境，因为构建会按本项目的 `requirements.lock` 安装依赖。`pc-build.local.json` 已被 Git 忽略，仅保存在当前电脑。

修改后先检查路径，再双击打包：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\package-pc.ps1 -CheckOnly
```

显示 `Preflight passed. No package generated.` 表示工具和 Python 版本检查通过；这一命令不运行测试，也不生成新包。正式打包仍会安装锁定依赖、测试和验证产物。

也可以从终端启动完整流程：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\package-pc.ps1
```

## 失败时看哪里

构建会生成绑定源码和 EXE 哈希的自动验收记录；声音、全屏、缩放、实际升级恢复和真实站点项目仍需人工验证。报告位置、签字命令和正式发布门槛见 [Windows 发布验收](release-acceptance.md)。

- 工具路径或 Python 版本不符：在窗口中按提示修改 `pc-build.local.json`，重新执行预检。
- 下载失败：检查网络，必要时修改 `PipIndexUrl`；播放器内核走固定的 GitHub 下载地址并验证 SHA-256，首次下载需要可访问 GitHub。
- 测试失败：修复失败项后重试。脚本不会跳过测试继续生成安装包。
- 文件被占用：关闭从项目 `dist\Lumen` 启动的程序，再重试。
- 完整构建日志：`.local\pc-build-日期时间-编号\build.log`。
- 最近一次状态：`.local\pc-last-build.json`；只有 `status` 为 `success` 才表示本次自动构建及验收完成，人工验收另见报告。
- `-CheckOnly` 成功时状态为 `preflight_passed`，仅表示预检完成；预检失败也会写入 `failed`，不会沿用上一轮的成功标记。
- 安装验证日志：`.local\installer-test.log`；测试结果：`.local\test-results.xml`。

失败时 `dist` 里可能还保留上一轮安装包，不能仅凭“文件存在”判断本次成功。以本轮 `SUCCESS` 和最近一次状态为准。

安装验证使用独立目录和独立卸载标识，不创建桌面快捷方式、不关闭现有客户端，也不使用个人资料库。生成的新包不会自动覆盖你正在使用的客户端；正式升级时先退出旧客户端，再手动运行安装包。
