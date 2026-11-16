"""4K YT Downloader helper: local HTTP service and download manager built on yt-dlp and ffmpeg."""
import collections
import glob
import importlib.util
import ipaddress
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HOST, PORT = "127.0.0.1", 9777
FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(APP_DIR, "bin")
DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "Downloads", "YT")
CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config"),
    "YTDownloaderHelper")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CFG = {"out": DEFAULT_OUT}
ALLOWED_HOST_HEADERS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

IS_WIN = os.name == "nt"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HEADLESS = "--nogui" in sys.argv
MAX_PARALLEL = 2

QUALITY_LABELS = [("Best available", "4320"), ("4K (2160p)", "2160"), ("1440p", "1440"), ("1080p", "1080"),
                  ("720p", "720"), ("480p", "480"), ("MP3 only", "mp3")]

QUEUED, RUNNING, PAUSED, DONE, FAILED, CANCELLED = (
    "queued", "running", "paused", "done", "failed", "cancelled")

YTDLP = None
FFDIR = None
HAS_DENO = False
JOBS = []
LOCK = threading.RLock()
SLOTS = threading.Semaphore(MAX_PARALLEL)


def log(*a):
    try:
        print(*a, flush=True)
    except Exception:
        pass


BRAND_DIR = os.path.join(APP_DIR, "branding")
BRAND = {
    "app_name": "4K YT Downloader",
    "creator": "Md Ariful Islam Shad",
    "facebook": "",
    "github": "",
    "whatsapp": "+8801975669946",
    "version": "1.0.0.0",
}


def load_brand():
    try:
        with open(os.path.join(BRAND_DIR, "branding.json"), encoding="utf-8") as f:
            data = json.load(f)
        for k in BRAND:
            if isinstance(data.get(k), str):
                BRAND[k] = data[k].strip()
    except (OSError, ValueError):
        pass


def brand_links():
    links = []
    for label, key in (("Facebook", "facebook"), ("GitHub", "github")):
        u = BRAND.get(key, "")
        if u.startswith("http") and "YOUR_" not in u:
            links.append((label, u))
    digits = re.sub(r"\D", "", BRAND.get("whatsapp", "")).lstrip("0")
    if digits:
        links.append(("WhatsApp", f"https://wa.me/{digits}"))
    return links


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        out = data.get("out")
        if isinstance(out, str) and out:
            CFG["out"] = out
    except (OSError, ValueError):
        pass


def save_config():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(CFG, f)
    except OSError:
        log(traceback.format_exc())


def set_out(path):
    path = os.path.normpath(path)
    os.makedirs(path, exist_ok=True)
    CFG["out"] = path
    save_config()


def _glob_first(pats, label):
    for pat in pats:
        hits = glob.glob(pat, recursive=True)
        if hits:
            log(f"{label} found:", hits[0])
            return os.path.dirname(hits[0])
    return None


def find_ffmpeg():
    exe = "ffmpeg.exe" if IS_WIN else "ffmpeg"
    if os.path.isfile(os.path.join(BIN_DIR, exe)):
        return BIN_DIR
    p = shutil.which("ffmpeg")
    if p:
        return os.path.dirname(p)
    if IS_WIN:
        la = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", "")
        pf86 = os.environ.get("ProgramFiles(x86)", "")
        home = os.path.expanduser("~")
        pats = []
        if la:
            pats += [
                os.path.join(la, "Microsoft", "WinGet", "Links", "ffmpeg.exe"),
                os.path.join(la, "Microsoft", "WinGet", "Packages", "**", "ffmpeg.exe"),
            ]
        for base in (pf, pf86):
            if base:
                pats.append(os.path.join(base, "ffmpeg*", "**", "ffmpeg.exe"))
        pats += [
            r"C:\ffmpeg\**\ffmpeg.exe",
            os.path.join(home, "Downloads", "ffmpeg*", "**", "ffmpeg.exe"),
        ]
        return _glob_first(pats, "ffmpeg")
    return None


def find_deno():
    exe = "deno.exe" if IS_WIN else "deno"
    if os.path.isfile(os.path.join(BIN_DIR, exe)):
        return BIN_DIR
    p = shutil.which("deno")
    if p:
        return os.path.dirname(p)
    if IS_WIN:
        la = os.environ.get("LOCALAPPDATA", "")
        home = os.path.expanduser("~")
        pats = []
        if la:
            pats += [
                os.path.join(la, "Microsoft", "WinGet", "Links", "deno.exe"),
                os.path.join(la, "Microsoft", "WinGet", "Packages", "**", "deno.exe"),
            ]
        pats += [
            os.path.join(home, ".deno", "bin", "deno.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "deno", "deno.exe"),
        ]
        return _glob_first(pats, "deno")
    return None


def find_ytdlp():
    exe = os.path.join(BIN_DIR, "yt-dlp.exe" if IS_WIN else "yt-dlp")
    if os.path.isfile(exe):
        return [exe]
    if not FROZEN and importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    p = shutil.which("yt-dlp")
    return [p] if p else None


def fatal(msg):
    log("[ERROR]", msg)
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(BRAND["app_name"] + " Helper", msg)
        r.destroy()
    except Exception:
        pass
    try:
        if sys.stdin and sys.stdin.isatty():
            input("Press Enter to close...")
    except Exception:
        pass
    sys.exit(1)


def to_int(x):
    try:
        return int(float(str(x).strip()))
    except (ValueError, TypeError):
        return 0


def fmt_size(n):
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:100] or "playlist"


def kill_tree(proc):
    if proc is None or proc.poll() is not None:
        return
    if IS_WIN:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, creationflags=NO_WINDOW)
    else:
        proc.terminate()


def child_env():
    env = os.environ.copy()
    for k in list(env):
        if k.startswith("_PYI") or k == "_MEIPASS2":
            del env[k]
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


class Job:
    _ids = itertools.count(1)

    def __init__(self, url, mode, playlist=False, outdir=None, subdir="", index=0, title=None):
        self.id = next(Job._ids)
        self.url, self.mode, self.playlist = url, mode, playlist
        self.outdir = outdir or CFG["out"]
        self.subdir, self.index = subdir, index
        self.named = bool(title)
        self.title = title or url
        self.state = QUEUED
        self.status = "Queued"
        self.percent = 0.0
        self.speed = ""
        self.eta = ""
        self.done_bytes = 0
        self.total_bytes = 0
        self.final_size = 0
        self.error = ""
        self.part = 0
        self.item = ""
        self.path = ""
        self.proc = None
        self.stop = None
        self.gen = 0
        self.checked = False
        self.auto_tried = False
        self.started_at = 0.0
        self.log = collections.deque(maxlen=40)

    def size_text(self):
        if self.final_size:
            return fmt_size(self.final_size)
        if self.total_bytes:
            return f"{fmt_size(self.done_bytes)} / {fmt_size(self.total_bytes)}"
        if self.done_bytes:
            return fmt_size(self.done_bytes)
        return ""

    def to_dict(self):
        return {"id": self.id, "title": self.title, "state": self.state,
                "status": self.status, "percent": round(self.percent, 1),
                "size": self.size_text(), "speed": self.speed,
                "eta": self.eta, "error": self.error}


def build_cmd(job):
    target = os.path.join(job.outdir, job.subdir) if job.subdir else job.outdir
    cmd = list(YTDLP) + [
        "-P", target, "--newline", "--color", "never",
        "--ffmpeg-location", FFDIR,
        "--socket-timeout", "30", "--retries", "20", "--fragment-retries", "20",
        "--extractor-retries", "5", "-N", "4", "--continue",
        "--progress-template",
        "download:PROG|%(progress._percent_str)s|%(progress.downloaded_bytes)s"
        "|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s"
        "|%(progress._speed_str)s|%(progress._eta_str)s",
    ]
    cmd += ["--windows-filenames", "--replace-in-metadata", "title", r"[\r\n\t]+", " "]
    cmd += ["--yes-playlist"] if job.playlist else ["--no-playlist"]
    if job.playlist:
        cmd += ["-o", "%(playlist_title).60s/%(playlist_index)03d - %(title).90s [%(id)s].%(ext)s"]
    elif job.subdir and job.index:
        cmd += ["-o", f"{job.index:03d} - %(title).90s [%(id)s].%(ext)s"]
    else:
        cmd += ["-o", "%(title).90s [%(id)s].%(ext)s"]
    if job.mode == "mp3":
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        q = job.mode
        cmd += ["-f", f"bv*[height<=?{q}]+ba/b[height<=?{q}]", "--merge-output-format", "mkv"]
    cmd += ["--", job.url]
    return cmd


def clean_name(path):
    name = os.path.basename(path)
    return re.sub(r"\.f\d+(-\w+)?(?=\.\w+$)", "", name)


def handle_line(job, line):
    line = line.rstrip()
    if not line or job.stop:
        return
    if line.startswith("PROG|"):
        p = line.split("|")
        if len(p) >= 7:
            try:
                job.percent = float(p[1].strip().rstrip("%"))
            except ValueError:
                pass
            done, total, est = to_int(p[2]), to_int(p[3]), to_int(p[4])
            job.done_bytes = done
            job.total_bytes = total or est
            if job.total_bytes and done:
                job.percent = min(100.0, done * 100.0 / job.total_bytes)
            sp, et = p[5].strip(), p[6].strip()
            job.speed = "" if ("N/A" in sp or "Unknown" in sp or sp == "NA") else sp
            job.eta = "" if ("N/A" in et or "Unknown" in et or et == "NA") else et
            base = f"Downloading item {job.item}" if job.item else "Downloading"
            job.status = f"{base} (part {job.part})" if job.part > 1 else base
        return

    job.log.append(line)
    log(f"[{job.id}] {line}")

    m = re.match(r"\[download\] Downloading item (\d+) of (\d+)", line)
    if m:
        job.item, job.part, job.percent = f"{m.group(1)}/{m.group(2)}", 0, 0.0
        return
    m = re.match(r"\[download\] Destination: (.+)", line)
    if m:
        job.part += 1
        job.path = m.group(1)
        if not job.named:
            job.title = clean_name(m.group(1))
        return
    m = re.match(r"\[download\] (.+) has already been downloaded", line)
    if m:
        job.path = m.group(1)
        job.status = "Already downloaded"
        return
    m = re.search(r'Merging formats into "(.+)"', line)
    if m:
        job.path = m.group(1)
        job.title = os.path.basename(m.group(1))
        job.status, job.percent, job.speed, job.eta = "Merging with ffmpeg", 100.0, "", ""
        return
    m = re.match(r"\[ExtractAudio\] Destination: (.+)", line)
    if m:
        job.path = m.group(1)
        job.title = os.path.basename(m.group(1))
        job.status, job.percent, job.speed, job.eta = "Converting to MP3", 100.0, "", ""
        return
    if line.startswith("[ExtractAudio]"):
        job.status, job.percent, job.speed, job.eta = "Converting to MP3", 100.0, "", ""
    elif line.startswith("[youtube]") or line.startswith("[info]"):
        job.status = "Fetching video info"
    elif line.startswith("ERROR:"):
        job.error = line[6:].strip()


def _finish(job, rc):
    job.proc = None
    job.speed = job.eta = ""
    if job.stop == "cancel":
        job.state, job.status = CANCELLED, "Cancelled"
    elif job.stop == "pause":
        job.state, job.status = PAUSED, "Paused (partial file kept)"
    elif rc == 0:
        job.state, job.status, job.percent = DONE, "Done", 100.0
        if not job.playlist and job.path and os.path.isfile(job.path):
            try:
                job.final_size = os.path.getsize(job.path)
            except OSError:
                pass
    else:
        err = job.error or (job.log[-1] if job.log else f"exit code {rc}")
        job.state, job.status = FAILED, "Failed: " + err[:100]


def run_job(job, gen):
    SLOTS.acquire()
    want_fix = False
    try:
        with LOCK:
            if gen != job.gen or job.state != QUEUED:
                return
            job.state, job.status = RUNNING, "Starting"
            job.error = ""
            job.started_at = time.time()
        try:
            cmd = build_cmd(job)
            log("RUN:", " ".join(cmd))
            proc = subprocess.Popen(
                cmd, env=child_env(), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=NO_WINDOW,
            )
            with LOCK:
                job.proc = proc
                stop = job.stop
            if stop:
                kill_tree(proc)
            for line in proc.stdout:
                handle_line(job, line)
            rc = proc.wait()
            with LOCK:
                _finish(job, rc)
                if job.state == FAILED and not job.auto_tried and looks_fixable(job):
                    job.auto_tried = want_fix = True
                    job.status = "Updating yt-dlp, then retrying..."
        except Exception:
            job.error = traceback.format_exc()
            log(job.error)
            with LOCK:
                _finish(job, 1)
                if job.state == FAILED:
                    job.status = "Failed (see console)"
    finally:
        SLOTS.release()
    if want_fix:
        threading.Thread(target=auto_fix_and_retry, args=(job,), daemon=True).start()


AUTOFIX_HINTS = ("403", "sign in", "requested format", "unable to extract", "nsig", "signature",
                 "po token", "challenge", "player response", "http error 403", "not a bot")
_fix_lock = threading.Lock()
_last_update = 0.0
SELFTEST = {"msg": ""}


def update_ytdlp_blocking():
    try:
        if YTDLP and len(YTDLP) == 1:
            cmd = YTDLP + ["-U"]
        else:
            cmd = [sys.executable, "-m", "pip", "install", "-U", "yt-dlp[default]"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL,
                           creationflags=NO_WINDOW, timeout=300, env=child_env())
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-700:] or "Done."
    except Exception as e:
        return False, str(e)


def looks_fixable(job):
    text = (job.error + " " + " ".join(list(job.log)[-5:])).lower()
    return "pyi-" not in text and any(h in text for h in AUTOFIX_HINTS)


def auto_fix_and_retry(job):
    global _last_update
    retry = False
    with _fix_lock:
        if _last_update >= job.started_at:
            retry = True
        elif time.time() - _last_update > 3600:
            ok, msg = update_ytdlp_blocking()
            _last_update = time.time()
            log("[auto-update]", "ok" if ok else "failed", msg[-200:])
            retry = ok
    if retry:
        job_restart(job, (FAILED,))
    else:
        with LOCK:
            if job.state == FAILED:
                job.status = "Failed: " + (job.error or "see details")[:100]


def enqueue(job):
    with LOCK:
        job.stop = None
        job.state, job.status = QUEUED, "Queued"
        job.gen += 1
        gen = job.gen
    threading.Thread(target=run_job, args=(job, gen), daemon=True).start()


def job_pause(job):
    proc = None
    with LOCK:
        if job.state == QUEUED:
            job.gen += 1
            job.state, job.status = PAUSED, "Paused"
        elif job.state == RUNNING and not job.stop:
            job.stop, job.status = "pause", "Pausing..."
            proc = job.proc
        else:
            return
    kill_tree(proc)


def job_cancel(job):
    proc = None
    with LOCK:
        if job.state in (QUEUED, PAUSED):
            job.gen += 1
            job.state, job.status = CANCELLED, "Cancelled"
            job.speed = job.eta = ""
        elif job.state == RUNNING and job.stop != "cancel":
            job.stop, job.status = "cancel", "Cancelling..."
            proc = job.proc
        else:
            return
    kill_tree(proc)


def job_restart(job, allowed):
    with LOCK:
        if job.state not in allowed:
            return False
        job.error = ""
        job.percent = job.percent if job.state == PAUSED else 0.0
    enqueue(job)
    return True


def add_job(job):
    with LOCK:
        JOBS.append(job)


def expand_playlist(ph):
    entries = []
    try:
        cmd = list(YTDLP) + [
            "--flat-playlist", "--yes-playlist", "--ignore-errors", "--no-warnings",
            "--color", "never", "--socket-timeout", "30",
            "--print", "%(playlist_title)s<<>>%(id)s<<>>%(title)s<<>>%(url)s", "--", ph.url]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL,
                           creationflags=NO_WINDOW, timeout=240, env=child_env())
        for line in r.stdout.splitlines():
            parts = line.split("<<>>")
            if len(parts) != 4:
                continue
            ptitle, vid, title, eurl = (x.strip() for x in parts)
            if not eurl.startswith("http"):
                if re.fullmatch(r"[\w-]{11}", vid) and "youtu" in ph.url:
                    eurl = f"https://www.youtube.com/watch?v={vid}"
                else:
                    continue
            entries.append((ptitle, vid, title, eurl))
    except Exception:
        log(traceback.format_exc())

    with LOCK:
        if ph.state != QUEUED:
            return
        if not entries:
            ph.title = ph.url
            fallback = True
        else:
            fallback = False
            ptitle = entries[0][0]
            subdir = "" if ptitle in ("", "NA", "None") else sanitize(ptitle)
            new_jobs = []
            for i, (_, vid, title, eurl) in enumerate(entries, 1):
                new_jobs.append(Job(
                    eurl, ph.mode, False, ph.outdir,
                    subdir, i if subdir else 0,
                    title if title not in ("", "NA", "None") else vid))
            if ph in JOBS:
                k = JOBS.index(ph)
                JOBS[k:k + 1] = new_jobs
            else:
                JOBS.extend(new_jobs)
    if fallback:
        enqueue(ph)
    else:
        for j in new_jobs:
            enqueue(j)


FORMATS_CACHE = {}
FORMATS_SEM = threading.Semaphore(2)


def probe_formats(url):
    hit = FORMATS_CACHE.get(url)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    with FORMATS_SEM:
        r = subprocess.run(
            list(YTDLP) + ["--no-playlist", "--skip-download", "--dump-single-json", "--no-warnings",
                           "--color", "never", "--socket-timeout", "20", "--extractor-retries", "2",
                           "--", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=90, env=child_env())
    if r.returncode != 0 or not r.stdout.strip():
        lines = (r.stderr or "").strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "yt-dlp could not read this page")
    info = json.loads(r.stdout)
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
        if not entries:
            raise RuntimeError("no video found on this page")
        info = entries[0]
    found = {}
    for f in info.get("formats") or []:
        h, w = f.get("height"), f.get("width")
        if isinstance(h, int) and h >= 100 and f.get("vcodec") != "none":
            found[h] = min(h, w) if isinstance(w, int) and w > 0 else h
    if not found and isinstance(info.get("height"), int):
        found[info["height"]] = info["height"]
    data = {"title": (info.get("title") or "")[:120],
            "formats": [{"h": h, "p": found[h]} for h in sorted(found, reverse=True)]}
    FORMATS_CACHE[url] = (time.time(), data)
    while len(FORMATS_CACHE) > 200:
        FORMATS_CACHE.pop(next(iter(FORMATS_CACHE)))
    return data


def submit(url, mode, playlist):
    if not YTDLP or not FFDIR:
        raise RuntimeError("yt-dlp or ffmpeg is missing")
    with LOCK:
        for j in JOBS:
            if j.url == url and j.mode == mode and j.playlist == playlist \
                    and j.state in (QUEUED, RUNNING, PAUSED):
                return j
    if playlist:
        ph = Job(url, mode, True, CFG["out"], title="Reading playlist...")
        ph.status = "Reading playlist"
        add_job(ph)
        threading.Thread(target=expand_playlist, args=(ph,), daemon=True).start()
        return ph
    job = Job(url, mode, False, CFG["out"])
    add_job(job)
    enqueue(job)
    return job


def validate(url, mode):
    try:
        u = urlparse(url)
        host = (u.hostname or "").lower()
    except ValueError:
        return False
    if u.scheme not in ("http", "https") or not host or len(url) > 4000:
        return False
    if host == "localhost" or host.endswith((".local", ".internal")):
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        pass
    return mode == "mp3" or re.fullmatch(r"[0-9]{3,4}", mode) is not None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, text, ctype="text/plain; charset=utf-8"):
        data = text.encode("utf-8", "replace")
        self.send_response(code)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(403, "forbidden")

    def do_GET(self):
        try:
            if (self.headers.get("Host") or "").lower() not in ALLOWED_HOST_HEADERS:
                self._send(403, "forbidden host")
                return
            u = urlparse(self.path)
            if u.path == "/ping":
                self._send(200, "ok")
                return
            if self.headers.get("X-YTDL") != "1":
                self._send(403, "forbidden")
                return
            if u.path == "/status":
                with LOCK:
                    data = [j.to_dict() for j in JOBS]
                self._send(200, json.dumps(data), "application/json")
                return

            q = parse_qs(u.query)
            url = q.get("url", [""])[0]
            if u.path == "/formats":
                if not YTDLP or not validate(url, "mp3"):
                    self._send(400, "bad request")
                    return
                try:
                    self._send(200, json.dumps(probe_formats(url)), "application/json")
                except Exception as e:
                    self._send(502, "could not read formats: " + str(e)[:300])
                return
            mode = q.get("q", ["2160"])[0]
            playlist = q.get("pl", ["0"])[0] == "1"
            if not validate(url, mode):
                self._send(400, "bad request")
                return
            job = submit(url, mode, playlist)
            self._send(200, ("playlist queued" if playlist else "started") + f" #{job.id}")
        except Exception:
            err = traceback.format_exc()
            log(err)
            self._send(500, "SERVER ERROR:\n" + err)


def open_folder():
    try:
        os.makedirs(CFG["out"], exist_ok=True)
        if IS_WIN:
            os.startfile(CFG["out"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", CFG["out"]])
        else:
            subprocess.Popen(["xdg-open", CFG["out"]])
    except Exception:
        log(traceback.format_exc())


def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    import webbrowser

    root = tk.Tk()
    root.title(f"{BRAND['app_name']} Helper  -  by {BRAND['creator']}")
    root.geometry("1040x640")
    root.minsize(860, 440)
    if "--minimized" in sys.argv:
        root.iconify()

    imgs = {}

    def load_img(name):
        try:
            return tk.PhotoImage(file=os.path.join(BRAND_DIR, name))
        except Exception:
            return None

    icon = load_img("logo_64.png")
    if icon:
        imgs["icon"] = icon
        try:
            root.iconphoto(True, icon)
        except Exception:
            pass
    header = ttk.Frame(root)
    header.pack(fill="x", padx=10, pady=(10, 0))
    logo = load_img("logo_48.png")
    if logo:
        imgs["logo"] = logo
        ttk.Label(header, image=logo).pack(side="left", padx=(0, 10))
    htext = ttk.Frame(header)
    htext.pack(side="left")
    ttk.Label(htext, text=BRAND["app_name"] + " Helper", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    ttk.Label(htext, text=f"Created by {BRAND['creator']}", foreground="#555555").pack(anchor="w")
    hlinks = ttk.Frame(header)
    hlinks.pack(side="right")
    for label, url in brand_links():
        lb = tk.Label(hlinks, text=label, fg="#0b57d0", cursor="hand2",
                      font=("Segoe UI", 10, "underline"))
        lb.pack(side="left", padx=8)
        lb.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))
    root.imgs = imgs

    top = ttk.Frame(root)
    top.pack(fill="x", padx=10, pady=(10, 0))
    ttk.Label(top, text="Save to:").pack(side="left")
    out_var = tk.StringVar(value=CFG["out"])
    ttk.Entry(top, textvariable=out_var, state="readonly").pack(
        side="left", fill="x", expand=True, padx=6)

    def change_folder():
        d = filedialog.askdirectory(initialdir=CFG["out"], parent=root,
                                    title="Choose the download folder")
        if d:
            try:
                set_out(d)
                out_var.set(CFG["out"])
            except OSError as e:
                messagebox.showerror("Download folder", str(e))

    ttk.Button(top, text="Change folder...", command=change_folder).pack(side="left")
    ttk.Button(top, text="Open folder", command=open_folder).pack(side="left", padx=(6, 0))

    add = ttk.Frame(root)
    add.pack(fill="x", padx=10, pady=(8, 0))
    ttk.Label(add, text="Video / playlist URL:").pack(side="left")
    url_var = tk.StringVar()
    url_entry = ttk.Entry(add, textvariable=url_var)
    url_entry.pack(side="left", fill="x", expand=True, padx=6)
    labels = [l for l, _ in QUALITY_LABELS]
    q_var = tk.StringVar(value=labels[0])
    ttk.Combobox(add, textvariable=q_var, values=labels, state="readonly", width=12).pack(side="left")
    pl_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(add, text="Whole playlist", variable=pl_var).pack(side="left", padx=8)

    def add_download():
        url = url_var.get().strip()
        mode = dict(QUALITY_LABELS)[q_var.get()]
        if not validate(url, mode):
            messagebox.showwarning("Add download", "Paste a valid video page link first.")
            return
        try:
            submit(url, mode, pl_var.get())
            url_var.set("")
        except Exception as e:
            messagebox.showerror("Add download", str(e))

    ttk.Button(add, text="Add download", command=add_download).pack(side="left")
    url_entry.bind("<Return>", lambda _e: add_download())

    if not HAS_DENO:
        ttk.Label(root, foreground="#a56a00",
                  text="Warning: Deno was not found. Some YouTube formats (including 4K) may be missing."
                  ).pack(anchor="w", padx=10, pady=(6, 0))

    selftest_var = tk.StringVar()
    ttk.Label(root, textvariable=selftest_var, foreground="#c00000", wraplength=980,
              ).pack(anchor="w", padx=10)

    def selftest():
        try:
            r = subprocess.run(list(YTDLP) + ["--version"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                               creationflags=NO_WINDOW, timeout=90, env=child_env())
            if r.returncode != 0:
                SELFTEST["msg"] = "yt-dlp cannot start: " + (r.stdout + r.stderr).strip()[-300:]
        except Exception as e:
            SELFTEST["msg"] = "yt-dlp cannot start: " + str(e)
    threading.Thread(target=selftest, daemon=True).start()

    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True, padx=10, pady=8)
    cols = ("sel", "title", "status", "pct", "size", "speed", "eta")
    tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended")
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    for c, text, w, anchor in (("sel", "All", 44, "center"), ("title", "Title", 300, "w"),
                               ("status", "Status", 190, "w"), ("pct", "Progress", 70, "e"),
                               ("size", "Size", 170, "w"), ("speed", "Speed", 90, "w"),
                               ("eta", "ETA", 65, "w")):
        tree.heading(c, text=text)
        tree.column(c, width=w, anchor=anchor, stretch=(c == "title"))
    tree.tag_configure("failed", foreground="#c00000")
    tree.tag_configure("done", foreground="#0a7a0a")
    tree.tag_configure("paused", foreground="#a56a00")
    tree.tag_configure("cancelled", foreground="#888888")
    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    def set_all(value):
        with LOCK:
            for j in JOBS:
                j.checked = value

    def toggle_all():
        with LOCK:
            value = not (JOBS and all(j.checked for j in JOBS))
        set_all(value)

    tree.heading("sel", text="All", command=toggle_all)

    def on_click(event):
        if tree.identify_region(event.x, event.y) != "cell":
            return None
        if tree.identify_column(event.x) != "#1":
            return None
        iid = tree.identify_row(event.y)
        if iid:
            with LOCK:
                for j in JOBS:
                    if str(j.id) == iid:
                        j.checked = not j.checked
                        break
        return "break"

    tree.bind("<Button-1>", on_click)

    def on_double(event):
        iid = tree.identify_row(event.y)
        with LOCK:
            job = next((j for j in JOBS if str(j.id) == iid), None)
            if not job:
                return
            text = f"{job.title}\n{job.url}\n\nStatus: {job.status}\n\n" + "\n".join(job.log)
        win = tk.Toplevel(root)
        win.title("Download details")
        win.geometry("760x420")
        box = tk.Text(win, wrap="word")
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True)

    tree.bind("<Double-1>", on_double)

    def targets():
        with LOCK:
            jobs = [j for j in JOBS if j.checked]
            if not jobs:
                sel = set(tree.selection())
                jobs = [j for j in JOBS if str(j.id) in sel]
        return jobs

    def do_pause():
        for j in targets():
            job_pause(j)

    def do_resume():
        for j in targets():
            job_restart(j, (PAUSED,))

    def do_retry():
        for j in targets():
            job_restart(j, (FAILED, CANCELLED))

    def do_cancel():
        ts = [j for j in targets() if j.state in (QUEUED, RUNNING, PAUSED)]
        if not ts:
            return
        if len(ts) > 1 and not messagebox.askyesno("Cancel", f"Cancel {len(ts)} downloads?"):
            return
        for j in ts:
            job_cancel(j)

    def clear_finished():
        with LOCK:
            JOBS[:] = [j for j in JOBS if j.state not in (DONE, CANCELLED)]

    def update_ytdlp():
        def work():
            ok, msg = update_ytdlp_blocking()
            root.after(0, lambda: messagebox.showinfo("yt-dlp update", msg))
        threading.Thread(target=work, daemon=True).start()

    def show_about():
        lines = [f"{BRAND['app_name']} Helper  v{BRAND['version']}", "",
                 f"Created by {BRAND['creator']}"]
        if BRAND["whatsapp"]:
            lines.append(f"WhatsApp: {BRAND['whatsapp']}")
        for label, url in brand_links():
            if label != "WhatsApp":
                lines.append(f"{label}: {url}")
        lines += ["", "Use only for videos you own or have permission to download."]
        messagebox.showinfo("About", "\n".join(lines))

    bar = ttk.Frame(root)
    bar.pack(fill="x", padx=10, pady=(0, 4))
    for text, fn in (("Pause", do_pause), ("Resume", do_resume), ("Retry", do_retry),
                     ("Cancel", do_cancel)):
        ttk.Button(bar, text=text, command=fn).pack(side="left", padx=(0, 6))
    ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
    for text, fn in (("Select all", lambda: set_all(True)), ("Select none", lambda: set_all(False)),
                     ("Clear finished", clear_finished), ("Update yt-dlp", update_ytdlp),
                     ("About", show_about)):
        ttk.Button(bar, text=text, command=fn).pack(side="left", padx=(0, 6))

    summary = tk.StringVar()
    ttk.Label(root, textvariable=summary, foreground="#555555").pack(anchor="w", padx=10, pady=(0, 8))

    def refresh():
        selftest_var.set(SELFTEST["msg"])
        with LOCK:
            jobs = list(JOBS)
        wanted = {str(j.id) for j in jobs}
        for iid in tree.get_children():
            if iid not in wanted:
                tree.delete(iid)
        have = set(tree.get_children())
        for j in jobs:
            vals = ("[x]" if j.checked else "[ ]", j.title, j.status,
                    f"{j.percent:.1f}%", j.size_text(), j.speed, j.eta)
            iid = str(j.id)
            if iid in have:
                tree.item(iid, values=vals, tags=(j.state,))
            else:
                tree.insert("", "end", iid=iid, values=vals, tags=(j.state,))
        count = collections.Counter(j.state for j in jobs)
        summary.set(f"Running: {count[RUNNING]}   Queued: {count[QUEUED]}   Paused: {count[PAUSED]}"
                    f"   Done: {count[DONE]}   Failed: {count[FAILED]}")
        root.after(500, refresh)

    def on_close():
        with LOCK:
            active = [j for j in JOBS if j.state in (QUEUED, RUNNING)]
        if active and not messagebox.askyesno(
                "Quit", f"{len(active)} download(s) still running. Stop them and quit?\n"
                        "(Partial files are kept, so you can resume later.)"):
            return
        for j in active:
            job_cancel(j)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh()
    root.mainloop()


def main():
    global YTDLP, FFDIR, HAS_DENO
    load_brand()
    load_config()
    try:
        os.makedirs(CFG["out"], exist_ok=True)
    except OSError:
        CFG["out"] = DEFAULT_OUT
        os.makedirs(CFG["out"], exist_ok=True)
    if os.path.isdir(BIN_DIR):
        os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")

    YTDLP = find_ytdlp()
    if not YTDLP:
        fatal("yt-dlp was not found.\n\nRun:  py -m pip install -U \"yt-dlp[default]\"\n"
              "(If you installed the app, reinstall it: bin\\yt-dlp.exe is missing.)")

    FFDIR = find_ffmpeg()
    if not FFDIR:
        fatal("ffmpeg was not found.\n\nRun:  winget install Gyan.FFmpeg\n"
              "then close and reopen this terminal. (The installed app bundles ffmpeg.)")

    deno_dir = find_deno()
    HAS_DENO = deno_dir is not None
    if HAS_DENO:
        os.environ["PATH"] = deno_dir + os.pathsep + os.environ.get("PATH", "")
    else:
        log("[WARN] Deno not found. Install it with: winget install DenoLand.Deno "
            "(yt-dlp needs a JavaScript runtime for full YouTube support).")
    os.environ["PATH"] = FFDIR + os.pathsep + os.environ.get("PATH", "")

    try:
        httpd = ThreadingHTTPServer((HOST, PORT), H)
    except OSError as e:
        fatal(f"Could not listen on {HOST}:{PORT} ({e}).\n"
              "The helper is probably already running (check the taskbar/tray).")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    log(f"Server running: http://{HOST}:{PORT}\nDownload folder: {CFG['out']}\nPress Ctrl+C to stop.")

    if not HEADLESS:
        try:
            run_gui()
            return
        except Exception:
            log("GUI unavailable, running headless:\n" + traceback.format_exc())
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
