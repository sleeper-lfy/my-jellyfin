# Windows 发布验收

打包成功表示生成了可测试的安装包。正式发布还要求完成下面的人工验收。自动测试、安装包、源码内容和人工证据记录在同一份 JSON 中；任意重新构建都需要重新核对安装包。

## 自动生成记录

双击 `Build-PC.cmd`，或按 `docs/windows-installer.md` 顺序执行三个构建脚本。构建开始生成 `.local/pc-acceptance.json`，安装和卸载验证成功后生成 `dist/installer/acceptance.json`。一键入口还在本次日志目录保留独立报告，其位置写入 `.local/pc-last-build.json` 的 `acceptance` 字段。

自动门槛包含：

| 项目 | 要求 |
| --- | --- |
| 源码 | 构建前后内容指纹相同，包含未提交代码；发布请求 JSON 不作为构建输入 |
| 测试 | 本次生成的 JUnit 报告，失败、错误和跳过均为零 |
| 安装包 | 本次生成，记录文件大小和 SHA-256 |
| 安装验证 | 同一安装包完成安装、界面启动、mpv 运行库、隔离插件 worker、卸载验证 |
| 人工项目 | 初始均为 `unverified`；自动测试不替代人工签字 |

源码截图回归、扬声器输出和实机视频画面尚未自动化，不能从 UI smoke 测试推断已通过。报告为可审查的证据记录，并非防伪数字签名。

## 人工验收矩阵

使用非私人媒体和测试资料库，验收后填写设备、环境、步骤与观察到的结果，必要时附截图或日志文件名。

| 标识 | 固定验收内容 |
| --- | --- |
| `audio` | 实际扬声器/耳机输出、音量、音画同步 |
| `fullscreen` | 窗口与全屏往返、任务栏隐藏和恢复、播放不中断 |
| `dpi_keyboard` | Windows 100%/150% 缩放，详情/设置/合并预览，键盘焦点与操作 |
| `upgrade_restore` | 从已安装旧版升级，评分/进度/队列保留，恢复旧备份 |
| `plugin_live` | 真实站点搜索、详情解析和错误提示；样本不含凭据 |

先复制自动报告到 `docs/validation/windows-release-acceptance.json`。以下命令中的 Python 可以替换为自己的 Python 3.12 环境；本机使用专用 Conda 环境。

```powershell
Copy-Item dist/installer/acceptance.json docs/validation/windows-release-acceptance.json
& E:/environment/miniconda3/envs/lumen/python.exe -m lumen.release_acceptance record --report docs/validation/windows-release-acceptance.json --installer dist/installer/Lumen-Setup-x64.exe --item audio --reviewer '验收人' --evidence '填写设备、测试步骤与实际结果'
```

对剩余四项分别执行 `record`，更换 `--item` 和具体证据。未实测的项目保持未验证，不使用模板文字冒充实际结果。检查正式发布条件：

```powershell
& E:/environment/miniconda3/envs/lumen/python.exe -m lumen.release_acceptance check --report docs/validation/windows-release-acceptance.json --installer dist/installer/Lumen-Setup-x64.exe --require-release
```

缺少人工项目、安装包改变或当前构建输入改变都会失败。重新构建后应使用新的自动报告重新验收。报告可提交到仓库；不要提交含私人信息的截图或日志。

## 发布流程

`scripts/publish-release.py` 在创建或上传 Release 之前检查固定位置的人工报告、版本、源码内容和安装包哈希。Windows 工作流的发布分支也检查该报告。未验收时仍可打包供测试，正式发布会被阻止。

推荐先打包、下载并验收，再通过已有“发布已验证安装包”的流程发布相同安装包。不要在人工验收后重新构建再尝试复用旧报告；即使版本号相同，重新构建的 EXE 也可能不同。仓库外手动上传或直接调用 `gh` 不受这些脚本约束。

Android 的状态独立保持 `unverified`。本次没有新增 Android 真机或云设备验收；Windows 的报告不能证明 Android 已通过。
