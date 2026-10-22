# Third-party notices

- Python: Python Software Foundation License — https://www.python.org/psf/license/
- PySide6 / Qt: LGPL v3, GPL v3 or commercial terms depending on module. This application dynamically links the selected Qt Core, GUI, Widgets, Multimedia and QML modules. Retain their license texts and users' ability to replace compatible shared libraries. https://doc.qt.io/qt-6/licensing.html
- Qt FFmpeg backend libraries: the runtime reports FFmpeg 7.1 LGPL v2.1 or later for the tested PySide6 build. External FFmpeg binaries may have additional GPL codecs: inspect the exact build's `ffmpeg -L` and `ffmpeg -buildconf`, retain notices and provide corresponding-source information before public binary distribution. https://ffmpeg.org/legal.html
- HTTPX, HTTPcore: BSD-3-Clause; AnyIO: MIT; Certifi: MPL-2.0; IDNA: BSD-3-Clause; SocksIO: Apache-2.0; H11: MIT.
- TVmaze data: CC BY-SA, attribution required. The UI retains TVmaze source links; redistributions of metadata should follow the provider's terms. https://www.tvmaze.com/api
- Internet Archive metadata/images: ownership and reuse rights depend on the item. The app only displays metadata and source links; it does not download video resources.

The build helper collects installed package license files. This is not a claim that every possible FFmpeg binary is redistributable under identical terms. Use verified official/package-manager sources and preserve their build-specific notices. No third-party film images or videos are committed to this repository.

## Android 客户端

LibVLC Android 3.7.7（VideoLAN / VLC authors）采用 LGPL 2.1 或后续版本，使用上游未修改的动态库。APK 的 `assets/licenses/` 包含许可文本和来源说明。项目公开 Gradle 构建工程，可替换库后重新构建 APK。

- 项目与原生库构建说明：https://code.videolan.org/videolan/libvlcjni
- 对应发布包与 Java 源码：https://repo.maven.apache.org/maven2/org/videolan/android/libvlc-all/3.7.7/
- VLC 核心源码：https://code.videolan.org/videolan/vlc
- AndroidX 依赖：Apache License 2.0；Kotlin 标准库：Apache License 2.0。

Android Gradle Plugin 和 Gradle 为构建工具，不打包进 APK。Android SDK 和 JDK 的使用受各自发行条款约束；源码包不包含 SDK/JDK。

## Windows libmpv

python-mpv 1.0.8 和固定的 libmpv 构建包含 GPL 组件。版本、许可证和对应源码入口见 [docs/mpv-runtime.md](docs/mpv-runtime.md)。应用自带的 `gentle-sharpen.glsl` 是本项目源码。
