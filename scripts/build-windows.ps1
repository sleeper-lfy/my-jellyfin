param([string]$PythonPath = '', [switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not $PythonPath -and -not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 venv creation failed' }
}
$LumenPython = if ($PythonPath) { $PythonPath } else { '.venv\Scripts\python.exe' }
& $LumenPython -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed' }
& $LumenPython -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $LumenPython -m lumen.release_acceptance begin --report .local/pc-acceptance.json
if ($LASTEXITCODE -ne 0) { throw 'Acceptance initialization failed' }
$LumenFfmpeg = (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue).Source
if (-not $LumenFfmpeg) { throw 'FFmpeg must be on PATH for the test suite; the installer no longer bundles it.' }
# FFmpeg is no longer shipped inside the installer: the app uses a local install when present
# and otherwise offers configuration or a one-time download at first run.
./scripts/fetch-mpv-windows.ps1
$env:LUMEN_REQUIRE_MPV = '1'
if ($SkipTests) {
    # Dependencies and the mpv bundle are still prepared; only the pytest gate is skipped.
    Write-Host 'SKIPPED: unit tests (-SkipTests). This package is NOT test-verified; do not publish it.'
    Remove-Item .local\test-results.xml -ErrorAction SilentlyContinue
} else {
    & $LumenPython -m pytest -q --junitxml=.local/test-results.xml
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; packaging stopped' }
}
& $LumenPython -m PyInstaller --noconfirm --clean --windowed --onedir --name Lumen --paths src --icon assets/lumen.ico `
  --hidden-import lumen.js_worker --hidden-import lumen.sandbox --hidden-import lumen.browser_http_worker --additional-hooks-dir scripts/pyinstaller-hooks --collect-all curl_cffi --collect-submodules PySide6.QtQml `
  --add-binary '.local/mpv-bundle/libmpv-2.dll;lumen/bin' `
  --add-data '.local/mpv-bundle/build.json;lumen/bin' --collect-data lumen `
  --add-data 'assets;assets' --add-data 'plugins;plugins' --add-data 'docs;docs' scripts/launcher.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
# PyInstaller collects the whole PySide6 Qt tree; remove modules the application never imports.
# Kept: Core/Gui/Widgets/Svg/OpenGL/Network/Multimedia(+SpatialAudio)/Qml/Quick family and opengl32sw fallback.
$PySide = 'dist\Lumen\_internal\PySide6'
$Unused = @('3D*','WebEngine*','Pdf*','Charts*','DataVisualization*','Graphs*','Labs*','Location','Positioning*','Scxml','Test','QuickTest','StateMachine','Sensors*','SerialPort','VirtualKeyboard','TextToSpeech','RemoteObjects','WebChannel','WebSockets','Help','Designer','UiTools','HttpServer','NetworkAuth')
Get-ChildItem $PySide -Filter 'Qt6*.dll' | Where-Object { $name = $_.BaseName.Substring(3); @($Unused | Where-Object { $name -like $_ }).Count -gt 0 } | Remove-Item -Force
foreach ($module in @('Qt3D','QtCharts','QtDataVisualization','QtGraphs','QtLocation','QtPositioning','QtQuick3D','QtRemoteObjects','QtScxml','QtSensors','QtTest','QtTextToSpeech','QtWebChannel','QtWebEngine','QtWebSockets','QtWebView','Qt5Compat')) {
    if (Test-Path "$PySide\qml\$module") { Remove-Item "$PySide\qml\$module" -Recurse -Force }
}
if (Test-Path "$PySide\plugins\qmltooling") { Remove-Item "$PySide\plugins\qmltooling" -Recurse -Force }
Get-ChildItem "$PySide\translations" -Filter 'qt_help_*.qm' -ErrorAction SilentlyContinue | Remove-Item -Force
if (Test-Path "$PySide\translations\qtwebengine_locales") { Remove-Item "$PySide\translations\qtwebengine_locales" -Recurse -Force }
$PrunedSize = [math]::Round((Get-ChildItem 'dist\Lumen' -Recurse | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "Pruned unused Qt modules; packaged size now $PrunedSize MB"
Copy-Item README.md dist\Lumen\README.md
Copy-Item THIRD_PARTY_NOTICES.md dist\Lumen\THIRD_PARTY_NOTICES.md
Copy-Item docs/mpv-runtime.md dist\Lumen\mpv-runtime.md
& $LumenPython scripts/collect-licenses.py dist/Lumen/licenses
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
& $LumenPython scripts/verify-package.py dist/Lumen/Lumen.exe
if ($LASTEXITCODE -ne 0) { throw 'Packaged application/worker verification failed' }
Compress-Archive -Path dist\Lumen -DestinationPath dist\Lumen-windows-x64.zip -Force
Write-Host 'Build complete: dist\Lumen-windows-x64.zip'
