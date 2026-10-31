param([string]$PythonPath = '')
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
& $LumenPython -m pytest -q --junitxml=.local/test-results.xml
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; packaging stopped' }
& $LumenPython -m PyInstaller --noconfirm --clean --windowed --onedir --name Lumen --paths src --icon assets/lumen.ico `
  --hidden-import lumen.js_worker --hidden-import lumen.sandbox --collect-submodules PySide6.QtQml `
  --add-binary '.local/mpv-bundle/libmpv-2.dll;lumen/bin' `
  --add-data '.local/mpv-bundle/build.json;lumen/bin' --collect-data lumen `
  --add-data 'assets;assets' --add-data 'plugins;plugins' --add-data 'docs;docs' scripts/launcher.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
Copy-Item README.md dist\Lumen\README.md
Copy-Item THIRD_PARTY_NOTICES.md dist\Lumen\THIRD_PARTY_NOTICES.md
Copy-Item docs/mpv-runtime.md dist\Lumen\mpv-runtime.md
& $LumenPython scripts/collect-licenses.py dist/Lumen/licenses
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
& $LumenPython scripts/verify-package.py dist/Lumen/Lumen.exe
if ($LASTEXITCODE -ne 0) { throw 'Packaged application/worker verification failed' }
Compress-Archive -Path dist\Lumen -DestinationPath dist\Lumen-windows-x64.zip -Force
Write-Host 'Build complete: dist\Lumen-windows-x64.zip'
