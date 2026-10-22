$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 first' }
    & .venv\Scripts\python.exe -m pip install -e .
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
}
Get-Command ffmpeg.exe -ErrorAction Stop | Out-Null
Get-Command ffprobe.exe -ErrorAction Stop | Out-Null
& .venv\Scripts\python.exe -m lumen
exit $LASTEXITCODE
