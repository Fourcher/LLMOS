#!/usr/bin/env python3
"""LLM OS Exporter: one window, no dependencies beyond Python 3.

Shows the current LLM OS version, lets the owner save the bootable ISO, write
it to a USB stick (with size and type recommendations), read the install /
dual-boot steps for their machine, or start the VM launcher. It is a tiny
local web app: this file serves ./index.html on 127.0.0.1 and opens it in
the default browser. Nothing leaves the machine.

Run it from the launcher next to it ("LLM OS Exporter.command" on macOS,
".bat" on Windows, ".sh" on Linux) or with `python3 exporter.py`.
"""
import hashlib
import http.server
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.dirname(HERE)
SYSTEM = platform.system()          # Darwin | Windows | Linux
STATE = {"phase": "idle", "done": 0, "total": 0, "message": "", "error": "", "started": 0}
LOCK = threading.Lock()
TOKEN = ""     # per launch; the page sends it back with every request, so another site cannot drive this app

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
                removable = str(d.get("rm")) in ("1", "True", "true") or str(d.get("hotplug")) in ("1", "True", "true") or d.get("tran") == "usb"
                if not removable:
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
        set_state(phase="write", done=0, total=size, message=f"Writing {name} to {drive['name']} ({drive['id']})", error="", started=time.time())
        if SYSTEM == "Darwin":
            cmd = (f"diskutil unmountDisk force {drive['id']} && dd if={shlex_q(src)} of={drive['raw']} bs=4m && sync && diskutil eject {drive['id']}")
            r = subprocess.run(["osascript", "-e", f'do shell script "{cmd}" with administrator privileges'], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip()[-300:] or "the write was cancelled")
        elif SYSTEM == "Linux":
            cmd = f"for p in {drive['id']}?*; do umount $p 2>/dev/null; done; if grep -q '^{drive['id']}' /proc/mounts; then echo 'still mounted' >&2; exit 3; fi; dd if={shlex_q(src)} of={drive['raw']} bs=4M conv=fsync status=progress"
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

def open_target(what):
    try:
        if what == "folder":
            if SYSTEM == "Darwin":
                subprocess.Popen(["open", DIST])
            elif SYSTEM == "Windows":
                os.startfile(DIST)  # noqa
            else:
                subprocess.Popen(["xdg-open", DIST])
        elif what == "vm":
            if SYSTEM == "Darwin":
                launcher = os.path.join(DIST, "run-llmos.sh")
                subprocess.Popen(["open", "-a", "Terminal", launcher])
            else:
                return {"ok": False, "error": "the VM launcher is for macOS; on Linux run: qemu-system-x86_64 -m 4096 -enable-kvm -cdrom llmos-x86_64.iso"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ----------------------------------------------------------------- http

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def same_origin(self):
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
        ok_host = host in (f"127.0.0.1:{self.server.server_address[1]}", f"localhost:{self.server.server_address[1]}")
        ok_origin = (not origin) or origin.startswith(f"http://{host}")
        return ok_host and ok_origin

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if not self.same_origin():
            return self.send_json({"error": "forbidden"}, 403)
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                body = f.read().replace(b"__TOKEN__", TOKEN.encode())
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/status":
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
        if not self.same_origin() or self.headers.get("X-LLMOS-Token", "") != TOKEN:
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
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"LLM OS Exporter: {url}  (close this window or press Ctrl+C to quit)")
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
