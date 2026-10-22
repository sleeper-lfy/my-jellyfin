$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 venv creation failed' }
}
$LumenPython = '.venv\Scripts\python.exe'
& $LumenPython -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed' }
& $LumenPython -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
$LumenFfmpeg = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
$LumenFfprobe = (Get-Command ffprobe.exe -ErrorAction Stop).Source
# Chocolatey exposes shims on PATH; bundle the actual executables, not machine-specific shims.
if ($env:ChocolateyInstall -and $LumenFfmpeg.StartsWith((Join-Path $env:ChocolateyInstall 'bin'), [System.StringComparison]::OrdinalIgnoreCase)) {
    $LumenActual = Get-ChildItem (Join-Path $env:ChocolateyInstall 'lib\ffmpeg') -Filter ffmpeg.exe -Recurse | Select-Object -First 1
    if (-not $LumenActual) { throw 'Cannot locate actual FFmpeg executable behind Chocolatey shim' }
    $LumenFfmpeg = $LumenActual.FullName
    $LumenFfprobe = Join-Path $LumenActual.DirectoryName 'ffprobe.exe'
}
if (-not (Test-Path $LumenFfprobe)) { throw 'FFprobe executable missing' }
New-Item -ItemType Directory -Force '.local\ffmpeg-bundle' | Out-Null
Copy-Item $LumenFfmpeg '.local\ffmpeg-bundle\ffmpeg.exe' -Force
Copy-Item $LumenFfprobe '.local\ffmpeg-bundle\ffprobe.exe' -Force
Get-ChildItem (Split-Path $LumenFfmpeg) -Filter '*.dll' | Copy-Item -Destination '.local\ffmpeg-bundle' -Force
& $LumenPython -m pytest -q --junitxml=.local/test-results.xml
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; packaging stopped' }
& $LumenPython -m PyInstaller --noconfirm --clean --windowed --onedir --name Lumen --paths src `
  --hidden-import lumen.js_worker --hidden-import lumen.sandbox --collect-submodules PySide6.QtQml `
  --add-binary '.local/ffmpeg-bundle/*;lumen/bin' `
  --add-data 'plugins;plugins' --add-data 'docs;docs' scripts/launcher.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
Copy-Item README.md dist\Lumen\README.md
Copy-Item THIRD_PARTY_NOTICES.md dist\Lumen\THIRD_PARTY_NOTICES.md
& $LumenPython scripts/collect-licenses.py dist/Lumen/licenses
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
& $LumenPython scripts/verify-package.py dist/Lumen/Lumen.exe
if ($LASTEXITCODE -ne 0) { throw 'Packaged application/worker verification failed' }
Compress-Archive -Path dist\Lumen -DestinationPath dist\Lumen-windows-x64.zip -Force
Write-Host 'Build complete: dist\Lumen-windows-x64.zip'
