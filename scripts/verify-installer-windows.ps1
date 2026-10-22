$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$InstallDir = Join-Path (Get-Location) ('.local\installer-test-' + [Guid]::NewGuid().ToString('N'))
$Installer = Join-Path (Get-Location) 'dist\installer\Lumen-Setup-x64.exe'
$Log = Join-Path (Get-Location) '.local\installer-test.log'
$Installed = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', "/DIR=`"$InstallDir`"", "/LOG=`"$Log`"") -Wait -PassThru
if ($Installed.ExitCode -ne 0) { throw "Installer failed: $($Installed.ExitCode)" }
$Executable = Join-Path $InstallDir 'Lumen.exe'
try {
    if (-not (Test-Path $Executable)) { throw 'Installed executable missing.' }
    & '.venv\Scripts\python.exe' scripts/verify-package.py $Executable
    if ($LASTEXITCODE -ne 0) { throw 'Installed UI / plugin worker verification failed.' }
} finally {
    $Uninstaller = Join-Path $InstallDir 'unins000.exe'
    if (Test-Path $Uninstaller) {
        $Removed = Start-Process -FilePath $Uninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
        if ($Removed.ExitCode -ne 0) { throw 'Uninstaller verification failed.' }
    }
}
if (Test-Path $Executable) { throw 'Uninstaller did not remove the application.' }
Write-Host 'Installer, installed application and uninstaller checks passed.'
