#!/usr/bin/env python3
"""LLM OS Setup: the first thing to open, on whatever computer you have. One window, no dependencies
beyond Python 3.

It recognises the computer (Mac with Apple Silicon or Intel, Windows, Linux; its memory) and recommends
the right way in: try LLM OS in a window (a virtual machine), make a bootable USB stick (with size and type
recommendations), install or dual boot, or just save the ISO. It is a tiny local web app: this file serves
./index.html on 127.0.0.1 and opens it in the default browser. Nothing leaves the machine.

Open it with the "1 - START HERE" file for your computer in the folder above, or `python3 llmos-setup.py`.
"""
import hashlib
import hmac
import http.server
import json
import os
import re
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.dirname(HERE)
SYSTEM = platform.system()          # Darwin | Windows | Linux
MACHINE = platform.machine().lower()  # arm64 / aarch64 on Apple Silicon and ARM PCs, x86_64 / amd64 otherwise


def _apple_silicon():
    """A Mac with Apple Silicon, even when this Python is an Intel build running under Rosetta (which reports
    x86_64): the chip, not the program, decides which ISO the Mac can run."""
    try:
        return subprocess.run(["sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True, timeout=5).stdout.strip() == "1"
    except Exception:
        return False


if SYSTEM == "Darwin" and MACHINE not in ("arm64", "aarch64") and _apple_silicon():
    MACHINE = "arm64"
ARM = MACHINE in ("arm64", "aarch64")
UTM_PAGE = "https://mac.getutm.app/"   # UTM: free, open-source virtual machines for the Mac
STATE = {"phase": "idle", "done": 0, "total": 0, "message": "", "error": "", "started": 0}
LOCK = threading.Lock()
TOKEN = ""     # per launch; the page sends it back with every request, so another site cannot drive this app


def _page_script_hash():
    """The CSP source for the page's one inline script (its SHA-256), so no other script can run in the page."""
    import base64
    import hashlib
    try:
        page = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
        code = page.split("<script>", 1)[1].split("</script>", 1)[0]
        return "'sha256-" + base64.b64encode(hashlib.sha256(code.encode("utf-8")).digest()).decode() + "'"
    except (OSError, IndexError):
        return "'none'"


PAGE_SCRIPT_HASH = _page_script_hash()

# ----------------------------------------------------------------- this computer

def host_ram_gb():
    try:
        if SYSTEM == "Darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout
            return int(out.strip()) / 1024 ** 3
        if SYSTEM == "Linux":
            with open("/proc/meminfo") as f:
                for ln in f:
                    if ln.startswith("MemTotal:"):
                        return int(ln.split()[1]) / 1024 ** 2
        if SYSTEM == "Windows":
            import ctypes

            class MemStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                           [(n, ctypes.c_ulonglong) for n in ("total", "avail", "tpage", "apage", "tvirt", "avirt", "aext")]
            m = MemStatus()
            m.dwLength = ctypes.sizeof(MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.total / 1024 ** 3
    except Exception:
        pass
    return 0


def _have(names, paths=()):
    return any(shutil.which(n) for n in names) or any(os.path.exists(p) for p in paths)


def host():
    """What this computer is, and what is already installed that the setup can use."""
    return {
        "system": SYSTEM, "machine": MACHINE, "arm": ARM, "apple_silicon": SYSTEM == "Darwin" and ARM,
        "ram_gb": round(host_ram_gb(), 1),
        "qemu": _have(["qemu-system-aarch64"], ["/opt/homebrew/bin/qemu-system-aarch64", "/usr/local/bin/qemu-system-aarch64"])
        if SYSTEM == "Darwin" else _have(["qemu-system-x86_64", "qemu-system-aarch64"]),
        "utm": SYSTEM == "Darwin" and os.path.isdir("/Applications/UTM.app"),
        "virtualbox": _have(["VBoxManage"], [r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe", "/Applications/VirtualBox.app"]),
    }


def recommend(h):
    """The right way in for this computer: which instructions come first, which ISO it needs, and why."""
    rec = {"iso": "llmos-arm64.iso" if h["arm"] else "llmos-x86_64.iso"}
    if h["apple_silicon"]:
        rec.update(section="apple-silicon", goal="vm", headline=(
            "This is a Mac with Apple Silicon. Run LLM OS in a window on this Mac: these Macs can't start it "
            "directly yet. The easiest way is the free app UTM."))
    elif SYSTEM == "Darwin":
        rec.update(section="intel-mac", goal="vm", headline=(
            "This is an Intel Mac. Try LLM OS in a window first (the free app UTM). It can also start from a USB "
            "stick and install next to macOS."))
    elif SYSTEM == "Windows":
        rec.update(section="pc", goal="usb", headline=(
            "This is a Windows PC. Make a USB stick and start the PC from it to try LLM OS — nothing on this PC "
            "changes. Or run it in a window with the free VirtualBox."))
    else:
        rec.update(section="pc", goal="vm", headline=(
            "This is a Linux computer. Run LLM OS in a window (QEMU or virt-manager), or make a USB stick for any PC."))
    if h["ram_gb"] and h["ram_gb"] < 8 and rec["goal"] == "vm":
        rec["note"] = (f"This computer has {h['ram_gb']:.0f} GB of memory and LLM OS in a window needs 4 GB of it, "
                       "so close other programs first; a USB stick on another PC avoids sharing memory.")
    return rec


# ----------------------------------------------------------------- release

def read_release():
    """What this folder contains: version, build date, images with sizes and checksums."""
    rel = {"version": "", "built": "", "images": []}
    p = os.path.join(DIST, "RELEASE.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                rel.update(json.load(f))
        except (OSError, ValueError):
            pass
    if not rel["version"]:
        for cand in (os.path.join(DIST, "VERSION"), os.path.join(os.path.dirname(DIST), "VERSION")):
            if os.path.exists(cand):
                rel["version"] = open(cand, encoding="utf-8").read().strip()
                break
    sums = {}
    sp = os.path.join(DIST, "SHA256SUMS")
    if os.path.exists(sp):
        for line in open(sp, encoding="utf-8"):
            parts = line.split()
            if len(parts) == 2:
                sums[parts[1].lstrip("*")] = parts[0]
    images = []
    for name in sorted(os.listdir(DIST)):
        if not name.endswith((".iso", ".qcow2")):
            continue
        path = os.path.join(DIST, name)
        arch = "x86_64" if "x86" in name else "arm64" if "arm64" in name else "?"
        images.append({"file": name, "kind": "iso" if name.endswith(".iso") else "vm", "arch": arch,
                       "size": os.path.getsize(path), "sha256": sums.get(name, ""),
                       "built": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))})
    rel["images"] = images
    rel["platform"] = SYSTEM
    rel["downloads"] = downloads_dir()
    rel["python"] = platform.python_version()
    rel["host"] = host()
    rel["recommend"] = recommend(rel["host"])
    return rel


def downloads_dir():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")

# ----------------------------------------------------------------- drives

def list_drives():
    """Removable drives the owner could write to. Internal / system disks are never listed."""
    drives = []
    try:
        if SYSTEM == "Darwin":
            out = subprocess.run(["diskutil", "list", "-plist", "external", "physical"], capture_output=True, timeout=20).stdout
            pl = plistlib.loads(out) if out else {}
            for d in pl.get("AllDisksAndPartitions", []):
                dev = d.get("DeviceIdentifier", "")
                size = int(d.get("Size", 0))
                info = subprocess.run(["diskutil", "info", "-plist", dev], capture_output=True, timeout=20).stdout
                pi = plistlib.loads(info) if info else {}
                if pi.get("Internal") or not pi.get("RemovableMediaOrExternalDevice", True):
                    continue
                name = pi.get("MediaName") or pi.get("IORegistryEntryName") or dev
                drives.append({"id": "/dev/" + dev, "raw": "/dev/r" + dev, "name": name, "size": size,
                               "bus": pi.get("BusProtocol", ""), "label": ", ".join(p.get("VolumeName", "") for p in d.get("Partitions", []) if p.get("VolumeName"))})
        elif SYSTEM == "Linux":
            out = subprocess.run(["lsblk", "-J", "-b", "-d", "-o", "NAME,SIZE,RM,MODEL,TRAN,TYPE,HOTPLUG"], capture_output=True, text=True, timeout=20).stdout
            for d in json.loads(out or "{}").get("blockdevices", []):
                if d.get("type") != "disk":
                    continue
                # removable means a USB transport or the removable flag: "hotplug" alone is set for a laptop's
                # built-in eMMC, which is often its system disk
                removable = str(d.get("rm")) in ("1", "True", "true") or d.get("tran") == "usb"
                if not removable or _linux_in_use(d["name"]):
                    continue
                drives.append({"id": "/dev/" + d["name"], "raw": "/dev/" + d["name"], "name": (d.get("model") or d["name"]).strip(),
                               "size": int(d.get("size") or 0), "bus": d.get("tran") or "", "label": ""})
        elif SYSTEM == "Windows":
            ps = ("Get-Disk | Where-Object { $_.BusType -in 'USB','SD','MMC' } | "
                  "Select-Object Number,FriendlyName,Size,BusType,IsSystem,IsBoot | ConvertTo-Json")
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30).stdout
            data = json.loads(out) if out.strip() else []
            if isinstance(data, dict):
                data = [data]
            for d in data:
                if d.get("IsSystem") or d.get("IsBoot"):
                    continue
                drives.append({"id": str(d["Number"]), "raw": r"\\.\PhysicalDrive%s" % d["Number"], "name": d.get("FriendlyName", ""),
                               "size": int(d.get("Size") or 0), "bus": d.get("BusType", ""), "label": ""})
    except Exception as e:  # listing must never crash the app
        return {"drives": [], "error": f"could not list drives: {e}"}
    return {"drives": drives}

_SYSTEM_MOUNTS = ("/", "/boot", "/boot/efi", "/efi", "/home", "/usr", "/var", "/opt", "/srv", "/nix", "/gnu")


def _linux_in_use(name):
    """Why this disk must not be written, or "": it holds part of the running system (a system mount point,
    swap) or an open encrypted / LVM / RAID volume. A stick the desktop mounted under /media or /run/media is
    fine: it is unmounted before writing."""
    try:
        out = subprocess.run(["lsblk", "-J", "-o", "NAME,TYPE,MOUNTPOINT", "/dev/" + name], capture_output=True, text=True, timeout=20).stdout
        tree = json.loads(out or "{}")
    except Exception:
        return "what is on it could not be checked"

    def walk(n):
        mp = n.get("mountpoint")
        if mp and (mp in _SYSTEM_MOUNTS or mp == "[SWAP]"):
            return f"it holds {mp} of this computer"
        if str(n.get("type", "")) in ("crypt", "lvm", "dm") or str(n.get("type", "")).startswith("raid"):
            return "it holds an open encrypted or LVM volume"
        for c in n.get("children") or []:
            r = walk(c)
            if r:
                return r
        return ""
    for d in tree.get("blockdevices", []):
        r = walk(d)
        if r:
            return r
    try:
        with open("/proc/swaps") as f:
            if re.search(r"^/dev/" + re.escape(name) + r"\S*\s", f.read(), re.M):
                return "it is used as swap"
    except OSError:
        pass
    return ""

# ----------------------------------------------------------------- long jobs

def set_state(**kw):
    with LOCK:
        STATE.update(kw)


def sha256_of(path, total, base_done=0, base_total=0):
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8 << 20)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            set_state(done=base_done + done, total=base_total or total)
    return h.hexdigest()


def job_save(name):
    set_state(phase="copy", done=0, total=0, message="Starting…", error="", started=time.time())
    src = os.path.join(DIST, name)
    rel = read_release()
    img = next((i for i in rel["images"] if i["file"] == name), None)
    ver = rel.get("version") or "current"
    dst = os.path.join(downloads_dir(), f"LLM-OS-{ver}-{name}")
    try:
        size = os.path.getsize(src)
        set_state(phase="copy", done=0, total=size, message=f"Saving {name} to {dst}", error="", started=time.time())
        with open(src, "rb") as s, open(dst, "wb") as d:
            done = 0
            while True:
                chunk = s.read(8 << 20)
                if not chunk:
                    break
                d.write(chunk)
                done += len(chunk)
                set_state(done=done)
        if img and img.get("sha256"):
            set_state(phase="verify", done=0, total=size, message="Checking the copy against its checksum")
            if sha256_of(dst, size) != img["sha256"]:
                raise RuntimeError("the saved file does not match the checksum; try again")
        set_state(phase="done", message=f"Saved: {dst}", done=size, total=size)
    except Exception as e:
        set_state(phase="error", error=str(e))


def _staged_source(src):
    """macOS blocks a root process (the privileged `dd`) from reading files on an external/removable volume, even
    when a normal read works -- "Operation not permitted". When the ISO is on a volume other than the startup disk,
    copy it to a temp file on the startup disk first and write from there. Returns (path, temp_or_None); the caller
    deletes the temp. Elsewhere, or when the ISO is already on the startup disk, nothing is copied."""
    if SYSTEM != "Darwin":
        return src, None
    try:
        if os.stat(src).st_dev == os.stat("/").st_dev:
            return src, None
    except OSError:
        return src, None
    need = os.path.getsize(src)
    st = os.statvfs("/private/tmp")
    if st.f_bavail * st.f_frsize < need + (256 << 20):
        raise RuntimeError("the ISO is on an external drive macOS won't let the writer read, and there isn't room "
                           "to copy it to the startup disk first. Move the LLM OS folder onto this Mac's own disk "
                           "(not Downloads/Desktop/Documents), or grant Terminal Full Disk Access in System "
                           "Settings > Privacy & Security, then try again.")
    set_state(phase="write", done=0, total=need, message="Preparing the image (copying it to the startup disk)...", error="", started=time.time())
    fd, tmp = tempfile.mkstemp(prefix="llmos-write-", suffix=".iso", dir="/private/tmp")
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as f:
            done = 0
            while True:
                chunk = f.read(16 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                set_state(done=done)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return tmp, tmp


def job_write(name, drive_id):
    set_state(phase="write", done=0, total=0, message="Checking the drive…", error="", started=time.time())
    src = os.path.join(DIST, name)
    drives = list_drives().get("drives", [])
    drive = next((d for d in drives if d["id"] == drive_id), None)
    if not drive:
        set_state(phase="error", error="that drive is no longer listed; unplug and replug it, then refresh")
        return
    size = os.path.getsize(src)
    if drive["size"] and drive["size"] < size:
        set_state(phase="error", error=f"{drive['name']} is too small ({drive['size'] // 10**9} GB) for this image")
        return
    try:
        read_from, staged = _staged_source(src)
        try:
            set_state(phase="write", done=0, total=size, message=f"Writing {name} to {drive['name']} ({drive['id']})", error="", started=time.time())
            if SYSTEM == "Darwin":
                cmd = (f"diskutil unmountDisk force {drive['id']} && dd if={shlex_q(read_from)} of={drive['raw']} bs=4m && sync && diskutil eject {drive['id']}")
                r = subprocess.run(["osascript", "-e", f'do shell script "{cmd}" with administrator privileges'], capture_output=True, text=True)
                if r.returncode != 0:
                    err = r.stderr.strip()
                    if "not permitted" in err.lower():
                        err = ("macOS blocked reading the image. Move the LLM OS folder onto this Mac's own disk "
                               "(not Downloads/Desktop/Documents), or grant Terminal Full Disk Access in System "
                               "Settings > Privacy & Security, then try again.")
                    raise RuntimeError(err[-300:] or "the write was cancelled")
            elif SYSTEM == "Linux":
                busy = _linux_in_use(os.path.basename(drive["id"]))
                if busy:
                    raise RuntimeError(f"{drive['name']} is not written: {busy}")
                cmd = f"for p in {drive['id']}?*; do umount $p 2>/dev/null; done; if grep -q '^{drive['id']}' /proc/mounts; then echo 'still mounted' >&2; exit 3; fi; dd if={shlex_q(read_from)} of={drive['raw']} bs=4M conv=fsync status=progress"
                runner = "pkexec" if shutil.which("pkexec") else "sudo"
                p = subprocess.Popen([runner, "sh", "-c", cmd], stderr=subprocess.PIPE, text=True)
                buf = ""
                while True:
                    ch = p.stderr.read(1)
                    if not ch:
                        break
                    buf += ch
                    if ch in "\r\n":
                        m = buf.strip().split(" bytes")[0]
                        if m.isdigit():
                            set_state(done=min(int(m), size))
                        buf = ""
                if p.wait() != 0:
                    raise RuntimeError("the write failed or was cancelled (is the stick still plugged in?)")
            elif SYSTEM == "Windows":
                write_windows(src, drive, size)
            set_state(phase="done", done=size, total=size, message=f"Done. {drive['name']} now boots LLM OS; you can unplug it.")
        finally:
            if staged:
                try:
                    os.unlink(staged)
                except OSError:
                    pass
    except Exception as e:
        set_state(phase="error", error=str(e))


def shlex_q(s):
    return "'" + s.replace("'", "'\\''") + "'"


def write_windows(src, drive, size):
    """Raw write on Windows: needs administrator rights, so the app relaunches itself elevated
    for the write step and watches a progress file."""
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        prog = os.path.join(os.environ.get("TEMP", HERE), "llmos-write-progress.txt")
        try:
            os.remove(prog)
        except OSError:
            pass
        params = f'"{os.path.abspath(__file__)}" --write "{src}" {drive["id"]} "{prog}"'
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 0)
        if rc <= 32:
            raise RuntimeError("Windows did not allow the elevated write (needs an administrator account). "
                               "Alternative: write the ISO with Rufus or balenaEtcher.")
        waited = 0
        while True:
            time.sleep(1)
            waited += 1
            if waited > 1800:
                raise RuntimeError("the elevated writer did not report back (was the prompt cancelled?)")
            try:
                with open(prog, encoding="utf-8") as f:
                    line = f.read().strip()
            except OSError:
                continue
            if line.startswith("DONE"):
                return
            if line.startswith("ERROR"):
                raise RuntimeError(line[6:])
            if line.isdigit():
                set_state(done=min(int(line), size))
        return
    # elevated instance: clear the disk's volumes, then stream the image onto the physical drive
    script = os.path.join(os.environ.get("TEMP", HERE), "llmos-diskpart.txt")
    with open(script, "w", encoding="utf-8") as f:
        f.write(f"select disk {drive['id']}\nclean\nrescan\n")
    subprocess.run(["diskpart", "/s", script], capture_output=True)
    time.sleep(2)
    with open(src, "rb") as s, open(drive["raw"], "r+b", buffering=0) as d:
        done = 0
        while True:
            chunk = s.read(4 << 20)
            if not chunk:
                break
            if len(chunk) % 512:
                chunk += b"\0" * (512 - len(chunk) % 512)
            d.write(chunk)
            done += len(chunk)
            set_state(done=min(done, size))
            yield_progress(done)


_PROGRESS_FILE = None


def yield_progress(n):
    if _PROGRESS_FILE:
        try:
            with open(_PROGRESS_FILE, "w", encoding="utf-8") as f:
                f.write(str(n))
        except OSError:
            pass

# ----------------------------------------------------------------- other actions

def _reveal(path):
    """Show a file selected in Finder / Explorer / the file manager."""
    if SYSTEM == "Darwin":
        subprocess.Popen(["open", "-R", path])
    elif SYSTEM == "Windows":
        subprocess.Popen(f'explorer /select,"{path}"')
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def open_target(what):
    """The page's buttons. Only fixed targets: this folder, the ISO this computer needs, the launcher in this
    folder, or the free virtual-machine apps' own download pages."""
    h = host()
    rec = recommend(h)
    try:
        if what == "folder":
            if SYSTEM == "Darwin":
                subprocess.Popen(["open", DIST])
            elif SYSTEM == "Windows":
                os.startfile(DIST)  # noqa
            else:
                subprocess.Popen(["xdg-open", DIST])
        elif what == "iso":
            path = os.path.join(DIST, rec["iso"])
            if not os.path.exists(path):
                return {"ok": False, "error": f"{rec['iso']} is not in this folder"}
            _reveal(path)
        elif what == "utm":
            webbrowser.open(UTM_PAGE)
        elif what == "virtualbox":
            webbrowser.open("https://www.virtualbox.org/wiki/Downloads")
        elif what == "vm":
            # The launcher in this folder is for Apple Silicon and needs QEMU; otherwise guide to a free app.
            # (A .sh file double-clicked in Finder opens in a text editor, so it is started in Terminal here.)
            if h["apple_silicon"] and h["qemu"]:
                subprocess.Popen(["open", "-a", "Terminal", os.path.join(DIST, "run-llmos.sh")])
                return {"ok": True, "message": "LLM OS is starting from a new Terminal window; its own window opens in a moment."}
            if SYSTEM == "Darwin":
                return {"ok": False, "guide": "utm", "error": (
                    f"The easiest way: install the free app UTM (button below), then follow “Try it in a window” "
                    f"with {rec['iso']}." + (" If you use Homebrew, `brew install qemu` and press this button again "
                                             "to use the built-in launcher instead." if h["apple_silicon"] else ""))}
            if SYSTEM == "Windows":
                return {"ok": False, "guide": "virtualbox", "error": (
                    f"Install the free VirtualBox (button below), then follow “Try it in a window” with {rec['iso']}.")}
            return {"ok": False, "guide": "qemu", "error": (
                f"Open {rec['iso']} in GNOME Boxes or virt-manager, or run: "
                f"qemu-system-x86_64 -enable-kvm -m 4096 -smp 4 -cdrom {rec['iso']}")}
        else:
            return {"ok": False, "error": "unknown action"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ----------------------------------------------------------------- http

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # Security headers sent on every response. frame-ancestors / X-Frame-Options stop another site from
    # framing this app (clickjacking); nosniff and no-store keep the token-bearing page out of caches and
    # content-type guessing; the CSP pins the self-contained page to its own origin.
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": ("default-src 'none'; style-src 'unsafe-inline'; script-src %s; "
                                    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
    }

    def _secure(self):
        for k, v in self.SECURITY_HEADERS.items():
            self.send_header(k, v % PAGE_SCRIPT_HASH if k == "Content-Security-Policy" else v)

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._secure()
        self.end_headers()
        self.wfile.write(body)

    def authorized(self, need_token):
        """CSRF / cross-origin gate. The Host must be our own loopback address (blocks DNS rebinding, where a
        hostile domain resolves to 127.0.0.1). Any Origin/Referer that is present must be our own origin
        (blocks a cross-site fetch, form or img). Every /api call must also carry the per-launch token in a
        custom header: a cross-origin page cannot read the token (same-origin policy) and cannot set a custom
        header without a CORS preflight this server never approves, so the token is the primary CSRF defense.
        The compare is constant-time."""
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False
        origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if origin and not (origin == f"http://{host}" or origin.startswith(f"http://{host}/")):
            return False
        if need_token:
            sent = self.headers.get("X-LLMOS-Token", "")
            if not TOKEN or not hmac.compare_digest(sent, TOKEN):
                return False
        return True

    def do_OPTIONS(self):
        # Refuse CORS preflight outright (no Access-Control-Allow-* headers), so any cross-origin call that
        # would need one is blocked by the browser before it reaches an action.
        self.send_json({"error": "forbidden"}, 403)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        # the page itself carries no token (it reads it from the address's #fragment), so it needs only same-origin;
        # every /api endpoint, read-only ones included, requires the token like the POST actions do.
        if path in ("/", "/index.html"):
            if not self.authorized(need_token=False):
                return self.send_json({"error": "forbidden"}, 403)
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._secure()
            self.end_headers()
            self.wfile.write(body)
            return
        if not self.authorized(need_token=True):
            return self.send_json({"error": "forbidden"}, 403)
        if path == "/api/status":
            self.send_json(read_release())
        elif path == "/api/drives":
            self.send_json(list_drives())
        elif path == "/api/progress":
            with LOCK:
                st = dict(STATE)
            st["elapsed"] = int(time.time() - st["started"]) if st["started"] else 0
            self.send_json(st)
        elif path == "/api/instructions":
            with open(os.path.join(HERE, "instructions.json"), encoding="utf-8") as f:
                self.send_json(json.load(f))
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if not self.authorized(need_token=True):
            return self.send_json({"error": "forbidden"}, 403)
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            data = {}
        name = os.path.basename(str(data.get("file", "")))
        if path in ("/api/save", "/api/write"):
            if not name or not os.path.exists(os.path.join(DIST, name)) or not name.endswith((".iso", ".qcow2")):
                return self.send_json({"ok": False, "error": "no such image in this folder"})
            with LOCK:
                busy = STATE["phase"] in ("copy", "verify", "write")
            if busy:
                return self.send_json({"ok": False, "error": "another job is still running"})
            if path == "/api/save":
                threading.Thread(target=job_save, args=(name,), daemon=True).start()
            else:
                drive = str(data.get("drive", ""))
                if not drive:
                    return self.send_json({"ok": False, "error": "pick a drive first"})
                threading.Thread(target=job_write, args=(name, drive), daemon=True).start()
            return self.send_json({"ok": True})
        if path == "/api/open":
            return self.send_json(open_target(str(data.get("what", ""))))
        if path == "/api/quit":
            self.send_json({"ok": True})
            threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
            return
        self.send_json({"error": "not found"}, 404)


def main():
    global _PROGRESS_FILE, TOKEN
    import secrets
    TOKEN = secrets.token_hex(16)
    if len(sys.argv) >= 5 and sys.argv[1] == "--write":      # the elevated Windows writer
        src, number, prog = sys.argv[2], sys.argv[3], sys.argv[4]
        _PROGRESS_FILE = prog
        try:
            drive = next(d for d in list_drives().get("drives", []) if d["id"] == number)
            write_windows(src, drive, os.path.getsize(src))
            with open(prog, "w", encoding="utf-8") as f:
                f.write("DONE")
        except Exception as e:
            with open(prog, "w", encoding="utf-8") as f:
                f.write("ERROR " + str(e))
        return
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/#{TOKEN}"
    print("LLM OS Setup is open in your web browser.")
    print(f"  If it did not open, paste this into the browser: {url}")
    print("  Keep this window open while you use it; close it (or press Ctrl+C) when you are done.")
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
