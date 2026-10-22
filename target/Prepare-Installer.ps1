$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path 'windows-installer.json')) { throw 'Installer has not been published yet. Check the Windows workflow.' }
$Package = Get-Content 'windows-installer.json' -Raw | ConvertFrom-Json
$Destination = Join-Path $PSScriptRoot 'Lumen-Setup-x64.exe'
if ($Package.parts.Count -gt 0) {
    $Temporary = "$Destination.partial"
    if (Test-Path $Temporary) { throw 'A partial output already exists. Rename it before retrying.' }
    foreach ($Part in $Package.parts) {
        if ($Part.name -notmatch '^Lumen-Setup-x64\.exe\.part\d{3}$') { throw 'Invalid part name' }
        $Path = Join-Path $PSScriptRoot $Part.name
        if (-not (Test-Path $Path)) { throw "Missing part: $($Part.name)" }
        if ((Get-Item $Path).Length -ne $Part.bytes -or (Get-FileHash $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Part.sha256) { throw "Part checksum mismatch: $($Part.name)" }
    }
    $Output = [System.IO.File]::Open($Temporary, [System.IO.FileMode]::CreateNew)
    try {
        foreach ($Part in $Package.parts) {
            $InputFile = [System.IO.File]::OpenRead((Join-Path $PSScriptRoot $Part.name))
            try { $InputFile.CopyTo($Output) } finally { $InputFile.Dispose() }
        }
    } finally { $Output.Dispose() }
    if ((Get-Item $Temporary).Length -ne $Package.bytes -or (Get-FileHash $Temporary -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Package.sha256) { throw 'Installer checksum mismatch' }
    Move-Item $Temporary $Destination -Force
}
if ((Get-Item $Destination).Length -ne $Package.bytes -or (Get-FileHash $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Package.sha256) { throw 'Installer checksum mismatch' }
Write-Host "Verified installer ready. Double-click: $Destination"
