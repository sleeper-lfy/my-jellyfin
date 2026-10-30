param([string]$ConfigPath = '', [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$TaskRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $TaskRoot
$TaskLogs = Join-Path $TaskRoot ('.local\pc-build-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $TaskLogs -Force | Out-Null
$TaskStatusPath = Join-Path $TaskRoot '.local\pc-last-build.json'
$TaskStatus = @{ status = 'preflight'; started = (Get-Date).ToString('o'); log = (Join-Path $TaskLogs 'build.log'); published = $false }
$TaskStatus | ConvertTo-Json | Set-Content -LiteralPath $TaskStatusPath -Encoding UTF8
Start-Transcript -Path $TaskStatus.log | Out-Null
try {
if ($ConfigPath -and -not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) { throw "Configuration file missing: $ConfigPath" }
if (-not $ConfigPath) { $ConfigPath = Join-Path $TaskRoot 'pc-build.local.json' }
$TaskConfig = if (Test-Path -LiteralPath $ConfigPath) { Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { @{} }
function Find-BuildFile($Explicit, $Candidates, $CommandName) {
    if ($Explicit) {
        if (-not (Test-Path -LiteralPath $Explicit -PathType Leaf)) { throw "Configured tool missing: $Explicit" }
        return (Resolve-Path -LiteralPath $Explicit).Path
    }
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return (Resolve-Path -LiteralPath $Candidate).Path }
    }
    if ($CommandName) { $Found = Get-Command $CommandName -ErrorAction SilentlyContinue; if ($Found) { return $Found.Source } }
    throw "Required tool missing: $CommandName. See docs/one-click-exe.md and pc-build.example.json."
}
$TaskPython = Find-BuildFile $TaskConfig.PythonPath @('E:\environment\miniconda3\envs\lumen\python.exe', (Join-Path $TaskRoot '.venv\Scripts\python.exe')) ''
$TaskCompiler = Find-BuildFile $TaskConfig.CompilerPath @((Join-Path $TaskRoot '.local\tools\innosetup\ISCC.exe'), (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'), (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')) 'ISCC.exe'
$TaskSevenZip = Find-BuildFile $TaskConfig.SevenZipPath @((Join-Path $TaskRoot '.local\tools\7zip\7z.exe'), (Join-Path $env:ProgramFiles '7-Zip\7z.exe')) '7z.exe'
if ($TaskConfig.FFmpegDirectory) {
    if (-not (Test-Path -LiteralPath $TaskConfig.FFmpegDirectory -PathType Container)) { throw 'FFmpegDirectory does not exist' }
    $env:PATH = $TaskConfig.FFmpegDirectory + ';' + $env:PATH
} elseif (Test-Path -LiteralPath 'E:\environment\ffmpeg\bin\ffmpeg.exe') {
    $env:PATH = 'E:\environment\ffmpeg\bin;' + $env:PATH
}
$env:PATH = (Split-Path $TaskSevenZip -Parent) + ';' + $env:PATH
if ($TaskConfig.PipIndexUrl) {
    if ($TaskConfig.PipIndexUrl -notmatch '^https://') { throw 'PipIndexUrl must use HTTPS' }
    $env:PIP_INDEX_URL = $TaskConfig.PipIndexUrl
}
$TaskFfmpeg = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
$TaskFfprobe = (Get-Command ffprobe.exe -ErrorAction Stop).Source
& $TaskPython -c 'import sys; assert sys.version_info[:2]==(3,12) and sys.maxsize>2**32'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 preflight failed' }
Write-Host "Python: $TaskPython"
Write-Host "Compiler: $TaskCompiler"
Write-Host "7-Zip: $TaskSevenZip"
Write-Host "FFmpeg: $TaskFfmpeg"
Write-Host "FFprobe: $TaskFfprobe"
if ($CheckOnly) {
    $TaskStatus.status = 'preflight_passed'; $TaskStatus.completed = (Get-Date).ToString('o')
    $TaskStatus | ConvertTo-Json | Set-Content -LiteralPath $TaskStatusPath -Encoding UTF8
    Write-Host 'Preflight passed. No package generated.'; exit 0
}
$TaskStatus.status = 'running'
$TaskStatus | ConvertTo-Json | Set-Content -LiteralPath $TaskStatusPath -Encoding UTF8
    $TaskAcceptance = Join-Path $TaskLogs 'acceptance.json'
    & (Join-Path $PSScriptRoot 'build-windows.ps1') -PythonPath $TaskPython
    Copy-Item -LiteralPath '.local/pc-acceptance.json' -Destination $TaskAcceptance -Force
    & (Join-Path $PSScriptRoot 'build-installer-windows.ps1') -CompilerPath $TaskCompiler
    & (Join-Path $PSScriptRoot 'verify-installer-windows.ps1') -PythonPath $TaskPython
    $TaskInstaller = Join-Path $TaskRoot 'dist\installer\Lumen-Setup-x64.exe'
    if (-not (Test-Path -LiteralPath $TaskInstaller)) { throw 'Installer output missing' }
    & $TaskPython -m lumen.release_acceptance finish --report $TaskAcceptance --installer $TaskInstaller
    if ($LASTEXITCODE -ne 0) { throw 'Automated acceptance failed' }
    $TaskStatus.acceptance = $TaskAcceptance
    $TaskStatus.status = 'success'; $TaskStatus.completed = (Get-Date).ToString('o')
    $TaskStatus.installer = $TaskInstaller
    $TaskStatus.sha256 = (Get-FileHash -LiteralPath $TaskInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
    $TaskStatus | ConvertTo-Json | Set-Content -LiteralPath $TaskStatusPath -Encoding UTF8
    Write-Host "SUCCESS: $TaskInstaller"
    Write-Host 'UI, playback runtime, plugin worker, installation and uninstallation verified.'
    Write-Host 'Human acceptance (audio, fullscreen, DPI, upgrade, live plugins) remains unverified. See docs/release-acceptance.md.'
} catch {
    $TaskStatus.status = 'failed'; $TaskStatus.error = $_.Exception.Message
    $TaskStatus | ConvertTo-Json | Set-Content -LiteralPath $TaskStatusPath -Encoding UTF8
    Write-Host ("FAILED: " + $_.Exception.Message)
    Write-Host ("Log: " + $TaskStatus.log)
    exit 1
} finally { Stop-Transcript | Out-Null }
