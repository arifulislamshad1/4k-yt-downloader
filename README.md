# 4K YT Downloader

![License](https://img.shields.io/badge/license-MIT-blue)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6)
![Chrome extension](https://img.shields.io/badge/Chrome%20extension-Manifest%20V3-4285F4)
![Version](https://img.shields.io/badge/version-1.0.0.0-2ea44f)

A Chromium extension (Manifest V3) with a local helper application that downloads videos in up to 4K from YouTube and from any other site supported by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

Created by **Md Ariful Islam Shad**.

> Use this software only for content you own or have permission to download. See [Legal notice](#legal-notice).

## Features

- Download button directly under YouTube videos and under videos on other websites
- Real resolution detection per video (Best available, 4K, 1440p, 1080p, 720p, 480p) and MP3 audio extraction
- Playlist support, with one queue entry per video
- Download manager window: live size, speed and ETA, pause, resume, retry, cancel and bulk actions
- Configurable download folder, remembered between sessions
- Automatic helper start from the extension, with no manual launch required
- Automatic yt-dlp update and retry when a site changes its player
- Right-click menu on pages, videos and links
- Per-user Windows installer, no administrator rights required

## How it works

```
Browser extension  --HTTP GET (127.0.0.1:9777)-->  Helper application
(popup, page button, context menu)                 (yt-dlp, ffmpeg, deno)
                                                          |
                                                   Downloads\YT\*.mkv, *.mp3
```

Browser extensions cannot merge separate video and audio streams or solve YouTube's player challenges, which is required for 1080p and above. The extension therefore delegates the work to a small local helper that runs yt-dlp and ffmpeg.

## Requirements

- Windows 10 or 11
- Google Chrome or Microsoft Edge
- Python 3.9 or newer (only when running from source or building)

## Installation

### Option A: Installer

1. Download `YTDownloaderHelper-Setup.exe` from the Releases page, or build it yourself (see [Building](#building)).
2. Run the installer. Optionally enable "Start the helper automatically when I sign in".
3. Open `chrome://extensions`, enable **Developer mode**, click **Load unpacked** and select  
   `%LOCALAPPDATA%\Programs\YTDownloaderHelper\extension`.
4. Reload the extension once so that auto-start is active.

### Option B: Run from source

```
py -m pip install -r requirements.txt
winget install Gyan.FFmpeg
winget install DenoLand.Deno
```

Restart the terminal, then:

1. Run `scripts\start.bat` (or `py helper\server.py`).
2. Load the `extension` folder through `chrome://extensions` as described above.
3. Optional, to enable auto-start: run `py scripts\register_host.py` once and reload the extension. Use `--remove` to undo.

## Usage

- **YouTube:** use the control under the video, next to Like and Share. Hover it to load the available resolutions.
- **Other sites:** a Download button appears below each video. Click it to list the available qualities.
- **Toolbar popup:** works on any http or https page.
- **Context menu:** right-click a page, video or link and choose *Download with 4K YT Downloader*.

Files are saved to `Downloads\YT` by default. Playlists are saved to `<folder>\<playlist title>\001 - title [id].mkv`.

### Helper window

| Action | Description |
|---|---|
| Change folder | Sets the download folder. New downloads use it; resumed jobs keep their original folder. |
| Add download | Paste a URL, choose a quality, optionally tick *Whole playlist*. |
| Pause / Resume | Stops yt-dlp and keeps the partial file; resume continues from it. |
| Retry | Restarts a failed or cancelled download. |
| Cancel | Stops the download; partial files remain on disk. |
| Bulk actions | Tick rows (or use *Select all*) and apply Pause, Resume, Retry or Cancel. |
| Details | Double-click a row to view the full log. |

Up to two downloads run in parallel; the remainder are queued.

### Command-line options

| Option | Effect |
|---|---|
| `--nogui` | Run without a window |
| `--minimized` | Start with the window minimized |

Settings are stored in `%APPDATA%\YTDownloaderHelper\config.json`.

### Quality selection

Downloads use the format selector `bv*[height<=Q]+ba/b[height<=Q]` and are merged into `.mkv`. If a video has no stream at the requested resolution, the best available quality below it is used.

## Building

Requirements: Python 3.9+ and [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).

Run `scripts\build.bat`. It generates the branding assets, downloads yt-dlp, ffmpeg and deno, builds the helper with PyInstaller and compiles `installer_output\YTDownloaderHelper-Setup.exe`. Without Inno Setup the application is still produced in `dist\YTDownloaderHelper`.

Pushing a tag such as `v1.0.0.0` runs the Release workflow, which builds the installer on GitHub and attaches it, together with a ZIP of the extension, to a GitHub release.

## Branding

Edit `branding/branding.json` (application name, creator, Facebook, GitHub, WhatsApp number, version) and optionally replace `branding/logo.png` with a square PNG (512 x 512 recommended). Then run:

```
py scripts\make_assets.py
```

This regenerates the extension icons, `extension/branding.js`, the executable icon and the installer settings. `scripts\build.bat` runs it automatically. Generated files `branding/logo.ico` and `installer/branding.iss` are not tracked in Git. Empty links are hidden. The WhatsApp value is converted to `https://wa.me/<digits>`, so use the full international number.

The `key` field in `extension/manifest.json` keeps the extension ID stable. The native messaging manifest `native/com.ytdl.helper.json` allows exactly that ID. If you fork the project and generate a new key, update `allowed_origins` accordingly.

## Project structure

```
.github/          Issue templates, pull request template, CI and release workflows
branding/         Branding configuration and logo files
extension/        Browser extension (manifest, background, content scripts, popup)
helper/           Helper application (server.py) and native messaging host
installer/        Inno Setup installer definition
native/           Native messaging host manifest
scripts/          Build, asset generation and host registration scripts
```

## Security

- The helper listens on `127.0.0.1` only.
- Requests must carry a custom header and a valid `Host` header; no CORS preflight is ever approved, so web pages cannot call the helper.
- URLs must be http or https; localhost and private network addresses are rejected.
- Quality values are validated and URLs are passed to yt-dlp after `--`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "ffmpeg was not found" | Run `winget install Gyan.FFmpeg` and reopen the terminal. The installer bundles ffmpeg. |
| "yt-dlp was not found" | Run `py -m pip install -U "yt-dlp[default]"`. Installer users should reinstall. |
| "auto-start is not set up" | Reinstall, or run `py scripts\register_host.py`, then reload the extension. |
| "Helper not running" | Start the application. Opening `http://127.0.0.1:9777/ping` should show `ok`. |
| "Port 9777 already running" | Another instance is open. Use it or end it in Task Manager. |
| Only up to 1080p, or "Requested format is not available" | Click **Update yt-dlp** and make sure Deno is available. |
| HTTP 403 or "Sign in to confirm you're not a bot" | Update yt-dlp. For videos you can access, `--cookies-from-browser chrome` can be added to `build_cmd` in `helper/server.py`. |
| SmartScreen warning on the installer | The installer is unsigned. Choose *More info*, then *Run anyway*, or sign the build. |
| Button missing under a video | Refresh the page. The toolbar popup works as an alternative. |

## Limitations

DRM-protected streams (for example Netflix and Disney+) and content that requires a login are not supported.

## Legal notice

This software is provided for downloading content that you own or are explicitly permitted to download. You are responsible for complying with the terms of service of the websites you use and with applicable copyright law. The author accepts no liability for misuse.

## Third-party software

The build downloads [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), [FFmpeg](https://ffmpeg.org/) (GPL build from BtbN) and [Deno](https://deno.com/) (MIT). Review their licenses before redistributing a built installer.

## License

Released under the [MIT License](LICENSE).

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first. Security issues should be reported as described in [SECURITY.md](SECURITY.md). Changes are listed in [CHANGELOG.md](CHANGELOG.md).
