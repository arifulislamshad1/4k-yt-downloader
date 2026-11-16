"""Registers the native messaging host for a source checkout on Windows. Use --remove to undo."""
import json
import os
import sys

NAME = "com.ytdl.helper"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYS = ("Software\\Google\\Chrome\\NativeMessagingHosts\\" + NAME,
        "Software\\Microsoft\\Edge\\NativeMessagingHosts\\" + NAME)


def main():
    if os.name != "nt":
        sys.exit("This script is for Windows.")
    import winreg
    if "--remove" in sys.argv:
        for k in KEYS:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, k)
            except OSError:
                pass
        print("Removed.")
        return
    with open(os.path.join(ROOT, "native", NAME + ".json"), encoding="utf-8") as f:
        m = json.load(f)
    m["path"] = os.path.join(ROOT, "native", "run_host.bat")
    out_dir = os.path.join(os.environ.get("APPDATA", ROOT), "YTDownloaderHelper")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, NAME + ".source.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)
    for k in KEYS:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, k) as h:
            winreg.SetValueEx(h, "", 0, winreg.REG_SZ, out)
    print("Registered. Reload the extension in chrome://extensions, then click Download in Chrome.")


if __name__ == "__main__":
    main()
