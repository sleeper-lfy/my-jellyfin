$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
# Fixed upstream build, regular x86_64 (does not require AVX2 / x86_64-v3).
$LumenMpvUrl = 'https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20261021/mpv-dev-x86_64-20261021-git-e471496c56.7z'
$LumenMpvHash = 'efc719eff3dc5954b4a5efc800632808bcec01cc9034940dd14e5eb7fe9ea633'
New-Item -ItemType Directory -Force '.local/mpv-download', '.local/mpv-bundle' | Out-Null
$LumenArchive = '.local/mpv-download/mpv-dev.7z'
if (-not (Test-Path $LumenArchive) -or (Get-FileHash $LumenArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $LumenMpvHash) {
    Invoke-WebRequest -Uri $LumenMpvUrl -OutFile $LumenArchive
}
if ((Get-FileHash $LumenArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $LumenMpvHash) { throw 'libmpv SHA256 mismatch' }
& 7z x $LumenArchive '-o.local/mpv-download/unpacked' -y | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'libmpv extraction failed' }
$LumenMpvDll = Get-ChildItem '.local/mpv-download/unpacked' -Filter 'libmpv-2.dll' -Recurse | Select-Object -First 1
if (-not $LumenMpvDll) { throw 'libmpv-2.dll missing' }
Copy-Item $LumenMpvDll.FullName '.local/mpv-bundle/libmpv-2.dll' -Force
@{ url=$LumenMpvUrl; sha256=$LumenMpvHash; mpv_commit='e471496c56'; architecture='x86_64' } | ConvertTo-Json | Set-Content '.local/mpv-bundle/build.json'
