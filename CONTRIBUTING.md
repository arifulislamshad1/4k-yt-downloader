# Contributing

Thank you for your interest in improving 4K YT Downloader.

## Development setup

```
py -m pip install -r requirements.txt
winget install Gyan.FFmpeg
winget install DenoLand.Deno
py helper\server.py
```

Load the `extension` folder through `chrome://extensions` with **Developer mode** enabled.

## Guidelines

- The helper uses only the Python standard library. Please do not add runtime dependencies.
- Keep changes focused and avoid unrelated formatting changes.
- Add comments only where the code is not self-explanatory.
- Branding and version values live in `branding/branding.json`. After changing them run `py scripts\make_assets.py`.
- Do not add features that circumvent DRM or other access controls. Such pull requests will be declined.

## Before opening a pull request

Run the same checks as the CI workflow:

```
py -m compileall -q helper scripts
node --check extension\background.js
node --check extension\content.js
node --check extension\content_any.js
node --check extension\popup.js
```

Then test manually on a YouTube video and on at least one other site, add an entry to `CHANGELOG.md` and describe your change in the pull request.
