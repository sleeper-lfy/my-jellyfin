$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$ManifestPath = Join-Path $PSScriptRoot 'windows-package.json'
if (-not (Test-Path $ManifestPath)) { throw 'Windows package is not available yet. Wait for the Windows build to succeed, then download target again.' }
$Package = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$OutputPath = Join-Path $PSScriptRoot 'Lumen-windows-x64.zip'
$TemporaryPath = "$OutputPath.partial"
if (Test-Path $TemporaryPath) { throw 'An unfinished .partial file already exists. Rename it before retrying.' }
foreach ($Part in $Package.parts) {
    if ($Part.name -notmatch '^Lumen-windows-x64\.zip\.part\d{3}$') { throw 'Invalid package part name' }
    $PartPath = Join-Path $PSScriptRoot $Part.name
    if (-not (Test-Path $PartPath)) { throw "Missing part: $($Part.name)" }
    if ((Get-Item $PartPath).Length -ne $Part.bytes -or (Get-FileHash $PartPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Part.sha256) { throw "Part checksum mismatch: $($Part.name)" }
}
$Output = [System.IO.File]::Open($TemporaryPath, [System.IO.FileMode]::CreateNew)
try {
    foreach ($Part in $Package.parts) {
        $InputFile = [System.IO.File]::OpenRead((Join-Path $PSScriptRoot $Part.name))
        try { $InputFile.CopyTo($Output) } finally { $InputFile.Dispose() }
    }
} finally { $Output.Dispose() }
if ((Get-Item $TemporaryPath).Length -ne $Package.bytes -or (Get-FileHash $TemporaryPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Package.sha256) { throw 'Package checksum mismatch' }
Move-Item $TemporaryPath $OutputPath -Force
$UnpackPath = Join-Path $PSScriptRoot ('windows-' + $Package.source_commit.Substring(0,12))
if (Test-Path $UnpackPath) { throw "Output directory already exists: $UnpackPath" }
Expand-Archive -LiteralPath $OutputPath -DestinationPath $UnpackPath
Write-Host "Ready: $UnpackPath\Lumen\Lumen.exe"
