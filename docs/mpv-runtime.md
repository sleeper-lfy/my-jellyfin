# libmpv 播放内核与 GPU 画质增强

Windows 正常界面默认使用 libmpv；视频由 libmpv 原生 GPU 窗口渲染，Qt 的控制层以独立的原生子窗口叠加，只覆盖标题、字幕和按钮区域，保留视频画面区域。缺少 libmpv 时显示兼容模式提示并使用 Qt Multimedia。无显示环境的 UI 自动测试使用 Qt 兼容模式，另有 libmpv 实际解码测试。

播放设置 → “GPU 画质增强”：启用 spline36 缩放、Mitchell 缩小和应用自带的轻度锐化着色器。默认关闭，可随时切换；该功能不是 AI 超分，也不修改原文件。硬件解码采用 libmpv `auto-safe`，不支持时由软件解码。性能取决于分辨率、编码、显卡与驱动。音频默认立体声。

Windows 构建脚本下载固定的 x86_64 上游 DLL 并验证 SHA-256，安装程序包含 DLL、着色器和构建记录，不要求用户安装 mpv。普通 x86_64 构建不额外要求 x86_64-v3/AVX2。Linux 开发环境需要系统 libmpv（Debian: libmpv2）和可用的 GPU 渲染驱动。显卡不兼容时可在播放设置勾选“兼容播放模式”，重启后使用原有 Qt 内核。

- python-mpv: 1.0.8，GPL-2.0-or-later；https://github.com/jaseg/python-mpv
- libmpv 构建: https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20261021
- 文件: mpv-dev-x86_64-20261021-git-e471496c56.7z
- SHA-256: `efc719eff3dc5954b4a5efc800632808bcec01cc9034940dd14e5eb7fe9ea633`
- mpv 源码版本: https://github.com/mpv-player/mpv/tree/e471496c56
- 构建配方与依赖来源: https://github.com/shinchiro/mpv-winbuild-cmake

该上游构建含 GPL 组件，不能按纯 LGPL 包分发。发行物须保留许可证及对应源码、依赖构建信息；本项目通过未修改的独立 DLL 动态加载。Python 包许可证由 `collect-licenses.py` 收集，mpv 许可证位于 `docs/licenses/`。不要将这里的版本信息用于其他 DLL 构建。
