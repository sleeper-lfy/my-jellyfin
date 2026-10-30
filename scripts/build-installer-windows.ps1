param([string]$CompilerPath = '')
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$Bundle = Join-Path (Get-Location) 'dist\Lumen'
$Application = Join-Path $Bundle 'Lumen.exe'
if (-not (Test-Path $Application)) { throw 'Run scripts/build-windows.ps1 first.' }
$Header = [System.IO.File]::ReadAllBytes($Application)
if ($Header[0] -ne 0x4d -or $Header[1] -ne 0x5a) { throw 'The bundle is not a Windows executable.' }
$Compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $CompilerPath) { $CompilerPath = if ($Compiler) { $Compiler.Source } else { Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' } }
if (-not (Test-Path $CompilerPath)) { throw 'Install Inno Setup 6 (choco install innosetup -y), then retry.' }
$Output = Join-Path (Get-Location) 'dist\installer'
New-Item -ItemType Directory -Force $Output | Out-Null
$LumenVersion = (Select-String -Path 'pyproject.toml' -Pattern '^version = "([0-9.]+)"').Matches.Groups[1].Value
if (-not $LumenVersion) { throw 'Cannot read application version' }
& $CompilerPath "/DBundleDir=$Bundle" "/DOutputDir=$Output" "/DAppVersion=$LumenVersion" 'installer\Lumen.iss'
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
$Installer = Join-Path $Output 'Lumen-Setup-x64.exe'
if (-not (Test-Path $Installer)) { throw 'Installer output missing.' }
$Hash = (Get-FileHash $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText("$Installer.sha256", "$Hash  Lumen-Setup-x64.exe`n")
Write-Host "Installer created: $Installer"
