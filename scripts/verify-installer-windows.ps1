param([string]$PythonPath = '.venv\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
$VerificationStarted = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
Set-Location (Join-Path $PSScriptRoot '..')
$VerificationId = [Guid]::NewGuid().ToString('N')
$InstallDir = Join-Path (Get-Location) ('.local\installer-test-' + $VerificationId)
$Installer = Join-Path (Get-Location) 'dist\installer\Lumen-Setup-x64.exe'
$VerificationHash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
$Log = Join-Path (Get-Location) '.local\installer-test.log'
$Installed = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/NOICONS', '/NOCLOSEAPPLICATIONS', "/GROUP=LumenVerification-$VerificationId", "/LumenVerification=$VerificationId", "/DIR=`"$InstallDir`"", "/LOG=`"$Log`"") -WindowStyle Hidden -Wait -PassThru
if ($Installed.ExitCode -ne 0) { throw "Installer failed: $($Installed.ExitCode)" }
$Executable = Join-Path $InstallDir 'Lumen.exe'
try {
    if (-not (Test-Path $Executable)) { throw 'Installed executable missing.' }
    & $PythonPath scripts/verify-package.py $Executable
    if ($LASTEXITCODE -ne 0) { throw 'Installed UI / plugin worker verification failed.' }
} finally {
    $Uninstaller = Join-Path $InstallDir 'unins000.exe'
    if (Test-Path $Uninstaller) {
        $Removed = Start-Process -FilePath $Uninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -WindowStyle Hidden -Wait -PassThru
        if ($Removed.ExitCode -ne 0) { throw 'Uninstaller verification failed.' }
    }
}
if (Test-Path $Executable) { throw 'Uninstaller did not remove the application.' }
if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $VerificationHash) { throw 'Installer changed during verification' }
$VerificationProof = @{ started_epoch = $VerificationStarted; sha256 = $VerificationHash; installed_ui = $true; mpv_runtime = $true; plugin_worker = $true; uninstall = $true }
$VerificationProof | ConvertTo-Json | Set-Content -LiteralPath '.local/installer-verification.json' -Encoding UTF8
if (Test-Path -LiteralPath '.local/pc-acceptance.json') {
    & $PythonPath -m lumen.release_acceptance finish --report .local/pc-acceptance.json --installer $Installer
    if ($LASTEXITCODE -ne 0) { throw 'Acceptance evidence did not match this build' }
    Copy-Item -LiteralPath '.local/pc-acceptance.json' -Destination 'dist/installer/acceptance.json' -Force
}
Write-Host 'Installer, installed application and uninstaller checks passed.'
