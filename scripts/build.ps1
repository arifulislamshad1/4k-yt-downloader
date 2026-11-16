$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$bin = Join-Path $root "build\bin"
New-Item -ItemType Directory -Force $bin | Out-Null

py -3 scripts\make_assets.py
if ($LASTEXITCODE -ne 0) { throw "scripts\make_assets.py failed" }

function Get-File($url, $out) {
    Write-Host "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
}

if (-not (Test-Path "$bin\yt-dlp.exe")) {
    Get-File "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" "$bin\yt-dlp.exe"
}

if (-not (Test-Path "$bin\ffmpeg.exe")) {
    $zip = "build\ffmpeg.zip"
    Get-File "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip" $zip
    $tmp = "build\ffmpeg_tmp"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive $zip $tmp -Force
    Get-ChildItem $tmp -Recurse -Include ffmpeg.exe, ffprobe.exe | Copy-Item -Destination $bin -Force
    Remove-Item $tmp -Recurse -Force
    Remove-Item $zip -Force
}

if (-not (Test-Path "$bin\deno.exe")) {
    $zip = "build\deno.zip"
    Get-File "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" $zip
    Expand-Archive $zip $bin -Force
    Remove-Item $zip -Force
}

py -3 -m pip install -U pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
py -3 -m PyInstaller --noconfirm --clean --onedir --noconsole --noupx --icon "branding\logo.ico" --name YTDownloaderHelper helper\server.py
if ($LASTEXITCODE -ne 0) { throw "helper build failed" }

py -3 -m PyInstaller --noconfirm --clean --onefile --console --noupx --name YTDLHost --distpath dist_host --workpath build\host helper\native_host.py
if ($LASTEXITCODE -ne 0) { throw "native host build failed" }

$dist = "dist\YTDownloaderHelper"
New-Item -ItemType Directory -Force "$dist\bin" | Out-Null
Copy-Item "$bin\*" "$dist\bin" -Force
if (Test-Path "$dist\branding") { Remove-Item "$dist\branding" -Recurse -Force }
Copy-Item "branding" "$dist\branding" -Recurse
if (Test-Path "$dist\extension") { Remove-Item "$dist\extension" -Recurse -Force }
Copy-Item "extension" "$dist\extension" -Recurse

New-Item -ItemType Directory -Force "$dist\native" | Out-Null
Copy-Item "dist_host\YTDLHost.exe" "$dist\native" -Force
Copy-Item "native\com.ytdl.helper.json" "$dist\native" -Force

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($iscc) {
    & $iscc "installer\installer.iss"
    Write-Host "`nDone: installer_output\YTDownloaderHelper-Setup.exe"
} else {
    Write-Host "`nInno Setup not found. Install it with:  winget install JRSoftware.InnoSetup"
    Write-Host "Then run scripts\build.bat again. The app itself is already in dist\YTDownloaderHelper\"
}
