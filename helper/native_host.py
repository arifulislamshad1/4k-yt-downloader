"""Native messaging host that starts the helper application on request from the browser extension."""
import json
import os
import struct
import subprocess
import sys
import time
import urllib.request

PORT = 9777
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))


def read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    n = struct.unpack("<I", raw)[0]
    return json.loads(sys.stdin.buffer.read(n).decode("utf-8"))


def send_message(obj):
    data = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
    sys.stdout.buffer.flush()


def alive():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/ping", timeout=1) as r:
            return r.read().strip() == b"ok"
    except Exception:
        return False


def helper_command():
    if FROZEN:
        exe = os.path.normpath(os.path.join(HERE, "..", "YTDownloaderHelper.exe"))
        return [exe, "--minimized"], os.path.dirname(exe)
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    if os.name == "nt" and os.path.isfile(pyw):
        py = pyw
    return [py, os.path.join(HERE, "server.py"), "--minimized"], HERE


def launch():
    cmd, cwd = helper_command()
    if not os.path.isfile(cmd[0]):
        raise FileNotFoundError(cmd[0])
    env = os.environ.copy()
    for k in list(env):
        if k.startswith("_PYI") or k == "_MEIPASS2":
            del env[k]
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    kw = dict(cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        DETACHED, NEW_GROUP, BREAKAWAY = 0x00000008, 0x00000200, 0x01000000
        try:
            subprocess.Popen(cmd, creationflags=DETACHED | NEW_GROUP | BREAKAWAY, **kw)
        except OSError:
            subprocess.Popen(cmd, creationflags=DETACHED | NEW_GROUP, **kw)
    else:
        subprocess.Popen(cmd, start_new_session=True, **kw)


def main():
    msg = read_message()
    if msg is None:
        return
    if alive():
        send_message({"ok": True, "started": False})
        return
    try:
        launch()
    except Exception as e:
        send_message({"ok": False, "error": f"could not start helper: {e}"})
        return
    for _ in range(40):
        if alive():
            send_message({"ok": True, "started": True})
            return
        time.sleep(0.5)
    send_message({"ok": False, "error": "helper did not start in time"})


if __name__ == "__main__":
    main()
