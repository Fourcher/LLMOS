#!/usr/bin/env python3
"""LLM OS Setup: makes a USB stick that starts LLM OS on a PC or an Intel Mac, from any Mac, Windows PC or
Linux computer, and shows how to try LLM OS in a window on this computer.

A tiny local web app: this file serves index.html on 127.0.0.1 to the default browser; nothing leaves this
computer. It needs only Python 3.8+ (the Start Here files find one, or fetch a private copy once).

Writing a stick
  macOS    The stick is opened with /usr/libexec/authopen: macOS shows its own password prompt, then hands this
           program an open device, and this program streams the image. (A password asked for with osascript's
           "with administrator privileges" runs the copy outside Terminal's privacy permissions, and macOS then
           refuses it with "Operation not permitted".)
  Windows, Linux
           A second copy of this program runs with administrator rights (the Windows "Yes" prompt, or polkit's
           pkexec) for the write and reports progress through a small file.
The image is written with its first 4 MiB last, so no operating system sees the new partition table before the
rest is in place, then read back and compared (SHA-256). Disks that hold this program's own files, Time Machine
backups, the system, or anything mounted from them, are never offered.
"""
import base64
import hashlib
import hmac
import http.server
import json
import mmap
import os
import platform
import plistlib
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))    # .../dist/setup
FILES = os.environ.get("LLMOS_SETUP_FILES") or os.path.dirname(HERE)   # .../dist: the images and checksums
OS = {"Darwin": "mac", "Windows": "windows"}.get(platform.system(), "linux")
USB_IMAGE = "llmos-x86_64.iso"     # starts PCs and Intel Macs: every computer that can boot from a USB stick
CHUNK = 4 << 20                    # 4 MiB, a multiple of every disk sector size
ALIGN = 4096                       # the last write is padded to a whole 4 KiB
MIN_STICK = 8 * 10**9
LARGE = 129 * 10**9                # bigger than a usual USB stick: listed, with a warning
AUTHOPEN = os.environ.get("LLMOS_SETUP_AUTHOPEN", "/usr/libexec/authopen")   # tests substitute a stand-in
UTM_URL = "https://mac.getutm.app/"
VBOX_URL = "https://www.virtualbox.org/wiki/Downloads"
BOXES_URL = "https://apps.gnome.org/Boxes/"
TOKEN = ""                         # per launch; every /api call must carry it (see Handler.authorized)
TEST_DEVICE = os.environ.get("LLMOS_SETUP_TEST_DEVICE", "")   # tests only: a device or file offered as "Test drive"


def log(msg):
    print("  " + msg, flush=True)


def run(args, timeout=60):
    """Run a command and return its CompletedProcess (text); a command that cannot run reads as failed."""
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(args, 127, "", str(e))


def gb(n):
    return f"{n / 1e9:.0f} GB" if n >= 10e9 else f"{n / 1e9:.1f} GB"

# ----------------------------------------------------------------- this computer

def _sysctl(name):
    return run(["sysctl", "-n", name], timeout=5).stdout.strip()


def native_arch():
    """The processor this computer has, not the one this Python was built for (an Intel Python under Rosetta,
    or an x64 Python on an ARM Windows PC, reports x86_64)."""
    if OS == "mac":
        return "arm64" if _sysctl("hw.optional.arm64") == "1" else "x86_64"
    if OS == "windows":
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            k32.IsWow64Process2.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ushort)]
            proc, native = ctypes.c_ushort(), ctypes.c_ushort()
            if k32.IsWow64Process2(k32.GetCurrentProcess(), ctypes.byref(proc), ctypes.byref(native)):
                return "arm64" if native.value == 0xAA64 else "x86_64"
        except (AttributeError, OSError):
            pass
        env = (os.environ.get("PROCESSOR_ARCHITEW6432", "") + os.environ.get("PROCESSOR_ARCHITECTURE", "")).upper()
        return "arm64" if "ARM64" in env else "x86_64"
    return "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"


ARCH = native_arch()


def ram_gb():
    try:
        if OS == "mac":
            return int(_sysctl("hw.memsize")) / 2**30
        if OS == "linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) / 2**20
        if OS == "windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                           [(n, ctypes.c_ulonglong) for n in ("total", "avail", "pagetotal", "pageavail", "virttotal", "virtavail", "extavail")]
            m = MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(m)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.total / 2**30
    except (OSError, ValueError, AttributeError):
        pass
    return 0


def host():
    chip = ""
    if OS == "mac":
        chip = "Apple silicon" if ARCH == "arm64" else "Intel"
    return {"os": OS, "arch": ARCH, "chip": chip, "ram_gb": round(ram_gb()),
            "kind": {"mac": "Mac", "windows": "PC"}.get(OS, "computer"),
            "boots_usb": ARCH == "x86_64"}    # can this computer itself start from the stick it makes


def version():
    for p in (os.path.join(FILES, "VERSION"), os.path.join(os.path.dirname(FILES), "VERSION")):
        try:
            with open(p, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return ""


def published_sha256(name):
    try:
        with open(os.path.join(FILES, "SHA256SUMS"), encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2 and parts[1].lstrip("*") == name:
                    return parts[0].lower()
    except OSError:
        pass
    return ""

# ----------------------------------------------------------------- is the image intact (checked once, in the background)

CHECK = {"state": "idle", "done": 0, "total": 0, "sha256": ""}      # idle | running | ok | bad | missing
_check_lock = threading.Lock()


def start_image_check():
    with _check_lock:
        if CHECK["state"] != "idle":
            return
        CHECK["state"] = "running"
    threading.Thread(target=_check_image, daemon=True).start()


def _check_image():
    path = os.path.join(FILES, USB_IMAGE)
    if not os.path.isfile(path):
        CHECK["state"] = "missing"
        return
    CHECK["total"] = os.path.getsize(path)
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(8 << 20), b""):
                h.update(block)
                CHECK["done"] += len(block)
    except OSError:
        CHECK["state"] = "bad"
        return
    want = published_sha256(USB_IMAGE)
    CHECK["sha256"] = h.hexdigest()
    CHECK["state"] = "ok" if not want or want == CHECK["sha256"] else "bad"

# ----------------------------------------------------------------- USB sticks

def _under(path, mount):
    path, mount = os.path.realpath(path), os.path.realpath(mount)
    return path == mount or path.startswith(mount.rstrip(os.sep) + os.sep)


def list_drives():
    """USB sticks and cards this computer could write. Never: the disk this program runs from, a Time Machine
    backup, an internal or system disk, or one holding a mounted system part."""
    try:
        drives = {"mac": _mac_drives, "windows": _win_drives}.get(OS, _linux_drives)()
    except Exception as e:      # listing must never take the page down
        return {"drives": [], "error": f"Couldn't list the drives: {e}"}
    if TEST_DEVICE:
        drives.append({"id": "test", "name": "Test drive", "labels": [], "bus": "test", "test": True,
                       "size": int(os.environ.get("LLMOS_SETUP_TEST_SIZE") or os.path.getsize(TEST_DEVICE))})
    for d in drives:
        d["too_small"] = 0 < d["size"] < MIN_STICK
        d["large"] = d["size"] > LARGE
    return {"drives": drives}


def _dplist(args):
    try:
        out = subprocess.run(["diskutil"] + args, capture_output=True, timeout=30).stdout
        return plistlib.loads(out) if out else {}
    except (OSError, subprocess.SubprocessError, ValueError, plistlib.InvalidFileException):
        return {}


def _mac_backup_mounts():
    out = run(["tmutil", "destinationinfo", "-X"], timeout=20).stdout
    try:
        info = plistlib.loads(out.encode()) if out.strip() else {}
    except (ValueError, plistlib.InvalidFileException):
        return []
    return [d.get("MountPoint") for d in info.get("Destinations", []) if d.get("MountPoint")]


def _mac_backup_disks(whole_of):
    """Physical disks holding an APFS volume whose role is Backup (Time Machine), mounted or not."""
    disks = set()
    for c in _dplist(["apfs", "list", "-plist"]).get("Containers", []):
        if any("Backup" in (v.get("Roles") or []) for v in c.get("Volumes", [])):
            for s in c.get("PhysicalStores", []):
                disks.add(whole_of.get(s.get("DeviceIdentifier"), ""))
    return disks


def _mac_drives():
    every = _dplist(["list", "-plist"]).get("AllDisksAndPartitions", [])
    external = _dplist(["list", "-plist", "external", "physical"]).get("WholeDisks", [])
    whole_of, mounts, labels = {}, {}, {}
    for d in every:
        w = d.get("DeviceIdentifier", "")
        for p in d.get("Partitions") or []:
            whole_of[p.get("DeviceIdentifier")] = w
            if p.get("MountPoint"):
                mounts.setdefault(w, []).append(p["MountPoint"])
            if p.get("VolumeName"):
                labels.setdefault(w, []).append(p["VolumeName"])
        if d.get("MountPoint"):
            mounts.setdefault(w, []).append(d["MountPoint"])
    for d in every:      # an APFS container is its own disk: credit its volumes to the physical disk under it
        for store in d.get("APFSPhysicalStores") or []:
            w = whole_of.get(store.get("DeviceIdentifier"), "")
            for v in d.get("APFSVolumes") or []:
                if v.get("MountPoint"):
                    mounts.setdefault(w, []).append(v["MountPoint"])
                if v.get("VolumeName"):
                    labels.setdefault(w, []).append(v["VolumeName"])
    backup_mounts, backup_disks = _mac_backup_mounts(), _mac_backup_disks(whole_of)
    drives = []
    for w in external:
        info = _dplist(["info", "-plist", w])
        if info.get("Internal") or info.get("VirtualOrPhysical") == "Virtual" or not info.get("WholeDisk", True):
            continue
        mps = mounts.get(w, [])
        if any(_under(FILES, m) or _under(HERE, m) for m in mps):
            continue                                  # this program's own drive
        if w in backup_disks or any(m in backup_mounts for m in mps):
            continue                                  # a Time Machine backup
        name = (info.get("MediaName") or info.get("IORegistryEntryName") or w).strip()
        vols = [v for v in labels.get(w, []) if v and v.upper() not in ("EFI", "RECOVERY")]
        drives.append({"id": w, "name": name, "size": int(info.get("Size") or info.get("TotalSize") or 0),
                       "labels": vols[:3], "bus": info.get("BusProtocol", "")})
    return drives


def _ps(script, timeout=60):
    return run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script], timeout)


def _win_self_disk_letter():
    drive = os.path.splitdrive(os.path.realpath(FILES))[0].rstrip(":\\/")
    return drive.upper() if len(drive) == 1 and drive.isalpha() else ""


def _win_drives():
    letter = _win_self_disk_letter()
    own = f"try {{ $own = (Get-Partition -DriveLetter '{letter}' -ErrorAction Stop).DiskNumber }} catch {{}}; " if letter else ""
    script = (
        "$own = -1; " + own +
        "@(Get-Disk | Where-Object { ($_.BusType -eq 'USB' -or $_.BusType -eq 'SD' -or $_.BusType -eq 'MMC') -and "
        "-not $_.IsSystem -and -not $_.IsBoot -and $_.Number -ne $own } | ForEach-Object { $n = $_.Number; "
        "$labels = @(Get-Partition -DiskNumber $n -ErrorAction SilentlyContinue | Get-Volume -ErrorAction SilentlyContinue | "
        "Where-Object { $_.FileSystemLabel } | ForEach-Object { $_.FileSystemLabel }); "
        "[pscustomobject]@{ Number = $n; Name = $_.FriendlyName; Size = [int64]$_.Size; Bus = [string]$_.BusType; Labels = $labels } }) "
        "| ConvertTo-Json -Compress -Depth 3")
    r = _ps(script)
    if r.returncode != 0 and not r.stdout.strip():
        raise RuntimeError((r.stderr or "PowerShell didn't answer").strip()[:200])
    data = json.loads(r.stdout) if r.stdout.strip() else []
    if isinstance(data, dict):
        data = [data]
    drives = []
    for d in data:
        labels = d.get("Labels") or []
        labels = [labels] if isinstance(labels, str) else [x for x in labels if x]
        drives.append({"id": str(d["Number"]), "name": (d.get("Name") or f"Disk {d['Number']}").strip(),
                       "size": int(d.get("Size") or 0), "labels": labels[:3], "bus": d.get("Bus", "")})
    return drives


_SYSTEM_MOUNTS = ("/", "/boot", "/boot/efi", "/efi", "/home", "/usr", "/var", "/opt", "/srv", "/nix", "/gnu")


def _lsblk(device=None):
    args = ["lsblk", "-J", "-b", "-o", "NAME,SIZE,RM,TRAN,TYPE,MODEL,VENDOR,LABEL,MOUNTPOINT"]
    out = run(args + ([device] if device else []), timeout=20).stdout
    try:
        return json.loads(out or "{}").get("blockdevices", [])
    except ValueError:
        return []


def _walk(node):
    yield node
    for child in node.get("children") or []:
        yield from _walk(child)


def _linux_blocker(disk):
    """Why this disk must not be written, or "": it holds part of the running system, swap, an open encrypted /
    LVM / RAID volume, or this program's own files. A stick mounted under /media is fine (it is unmounted first)."""
    for n in _walk(disk):
        mp = n.get("mountpoint")
        if mp and (mp in _SYSTEM_MOUNTS or mp == "[SWAP]"):
            return f"it holds {mp} of this computer"
        if mp and (_under(FILES, mp) or _under(HERE, mp)):
            return "LLM OS Setup itself runs from it"
        t = str(n.get("type", ""))
        if t in ("crypt", "lvm", "dm") or t.startswith("raid"):
            return "it holds an open encrypted or LVM volume"
    try:
        with open("/proc/swaps") as f:
            if re.search(r"^/dev/" + re.escape(disk["name"]) + r"\S*\s", f.read(), re.M):
                return "it is used as swap"
    except OSError:
        pass
    return ""


def _linux_drives():
    drives = []
    for d in _lsblk():
        removable = str(d.get("rm")).lower() in ("1", "true") or d.get("tran") == "usb"
        if d.get("type") != "disk" or not removable or _linux_blocker(d):
            continue
        name = " ".join(x for x in ((d.get("vendor") or "").strip(), (d.get("model") or "").strip()) if x) or d["name"]
        labels = [n.get("label") for n in _walk(d) if n.get("label")]
        drives.append({"id": "/dev/" + d["name"], "name": name, "size": int(d.get("size") or 0),
                       "labels": labels[:3], "bus": d.get("tran") or ""})
    return drives

# ----------------------------------------------------------------- writing (the part shared by every system)

def _aligned(n):
    return (n + ALIGN - 1) // ALIGN * ALIGN


def _fill(f, view):
    got = 0
    while got < len(view):
        n = f.readinto(view[got:])
        if not n:
            break
        got += n
    return got


def write_and_verify(path, size, expected, pwrite, pread, progress, flush=None):
    """Stream the image at `path` onto a device, then read it back and compare.

    pwrite(view, offset) must write all of view at offset; pread(view, offset) must fill view from offset.
    The first chunk is written last, so the device shows no partition table until everything after it is in
    place. progress(phase, bytes_done) reports "writing" and "verifying". flush() runs between the two.
    Raises RuntimeError when the image changes underneath or the device reads back differently."""
    buf = mmap.mmap(-1, CHUNK)             # page-aligned memory: raw disk devices want aligned buffers
    first = mmap.mmap(-1, CHUNK)
    view, first_view = memoryview(buf), memoryview(first)
    first_len = 0
    try:
        h = hashlib.sha256()
        off = 0
        with open(path, "rb", buffering=0) as f:
            while off < size:
                n = _fill(f, view[:min(CHUNK, size - off)])
                if n <= 0:
                    raise RuntimeError("The LLM OS image ended early. Get a fresh copy of the LLM OS folder.")
                h.update(view[:n])
                m = _aligned(n)
                if m > n:
                    view[n:m] = bytes(m - n)
                if off == 0:
                    first_view[:m] = view[:m]          # written last
                    first_len = m
                else:
                    pwrite(view[:m], off)
                off += n
                progress("writing", off)
        if expected and h.hexdigest() != expected:
            raise RuntimeError("The LLM OS image changed while it was being written. Try again.")
        pwrite(first_view[:first_len], 0)
        if flush:
            flush()
        check = hashlib.sha256()
        off = 0
        while off < size:
            n = min(CHUNK, size - off)
            pread(view[:_aligned(n)], off)
            check.update(view[:n])
            off += n
            progress("verifying", off)
        if check.digest() != h.digest():
            raise RuntimeError("The stick didn't read back correctly, so it may be faulty. Try another USB stick.")
        return h.hexdigest()
    finally:
        view.release()
        first_view.release()
        buf.close()
        first.close()


def _fd_io(fd):
    """pwrite/pread for a POSIX file descriptor (whole-buffer, retrying short transfers)."""
    def pwrite(view, offset):
        done = 0
        while done < len(view):
            n = os.pwrite(fd, view[done:], offset + done)
            if n <= 0:
                raise RuntimeError("The stick stopped accepting data. Is it still plugged in?")
            done += n

    def pread(view, offset):
        os.lseek(fd, offset, os.SEEK_SET)
        got = 0
        while got < len(view):
            n = os.readv(fd, [view[got:]])
            if n <= 0:
                raise RuntimeError("The stick stopped answering while it was being checked. Is it still plugged in?")
            got += n
    return pwrite, pread

# ----------------------------------------------------------------- the write job

STATE = {"phase": "idle", "done": 0, "total": 0, "drive": None, "error": "", "started": 0.0}
LOCK = threading.Lock()
_FINISHED = ("idle", "done", "error", "cancelled")


class Cancelled(Exception):
    pass


def set_state(**kw):
    with LOCK:
        STATE.update(kw)


def start_write(drive_id):
    """Start writing the USB image to the drive with this id; returns "" or the reason it can't start."""
    with LOCK:
        if STATE["phase"] not in _FINISHED:
            return "A stick is already being written."
    drive = next((d for d in list_drives().get("drives", []) if d["id"] == drive_id), None)
    if not drive:
        return "That stick isn't connected any more. Plug it in again and choose it."
    path = os.path.join(FILES, USB_IMAGE)
    if not os.path.isfile(path):
        return "This copy of LLM OS is missing its USB image. Get a fresh copy of the LLM OS folder."
    size = os.path.getsize(path)
    if drive["size"] and drive["size"] < max(size, MIN_STICK):
        return f"{drive['name']} is too small. Use a stick of 8 GB or more."
    set_state(phase="checking", done=0, total=size, drive=drive, error="", started=time.time())
    threading.Thread(target=_write_job, args=(drive, path, size), daemon=True).start()
    return ""


def _write_job(drive, path, size):
    try:
        start_image_check()                    # the image must be intact before anything is erased
        while CHECK["state"] == "running":
            set_state(phase="checking", done=CHECK["done"], total=CHECK["total"] or size)
            time.sleep(0.25)
        if CHECK["state"] == "missing":
            raise RuntimeError("This copy of LLM OS is missing its USB image. Get a fresh copy of the LLM OS folder.")
        if CHECK["state"] == "bad":
            raise RuntimeError("The LLM OS image in this folder is damaged. Get a fresh copy of the LLM OS folder "
                               "(download or copy it again), then try again. Your stick was not touched.")
        set_state(total=size, done=0, started=time.time())
        log(f"Writing {USB_IMAGE} to {drive['name']} ({drive['id']}, {gb(drive['size'])})")
        if OS == "mac":
            _mac_write(drive, path, size, CHECK["sha256"])
        elif drive.get("test"):
            fd = os.open(TEST_DEVICE, os.O_RDWR)
            try:
                write_and_verify(path, size, CHECK["sha256"], *_fd_io(fd), _progress)
            finally:
                os.close(fd)
        else:
            _elevated_write(drive, path, size, CHECK["sha256"])
        set_state(phase="done", done=size, total=size)
        log("Done: the stick is ready.")
    except Cancelled:
        set_state(phase="cancelled", error="")
        log("Cancelled: nothing was written.")
    except Exception as e:      # every failure ends in a readable message on the page
        set_state(phase="error", error=str(e) or e.__class__.__name__)
        log(f"Error: {e}")


def _progress(phase, done):
    set_state(phase=phase, done=done)

# ----------------------------------------------------------------- macOS

def _authopen(path, flags):
    """Open `path` through Apple's authopen: macOS asks for the password in its own window, then authopen hands
    this process the open descriptor over a socket (SCM_RIGHTS). Raises Cancelled when the prompt is cancelled."""
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        proc = subprocess.Popen([AUTHOPEN, "-stdoutpipe", "-o", str(flags), path],
                                stdin=subprocess.DEVNULL, stdout=child, stderr=subprocess.PIPE)
    finally:
        child.close()
    fds = []
    try:
        parent.settimeout(900)                 # time to type the password
        _msg, anc, _flags, _addr = parent.recvmsg(64, socket.CMSG_SPACE(struct.calcsize("i")))
        for level, kind, data in anc:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                whole = len(data) - len(data) % struct.calcsize("i")
                fds.extend(struct.unpack(f"{whole // struct.calcsize('i')}i", data[:whole]))
    except socket.timeout:
        proc.kill()
    finally:
        parent.close()
    err = proc.stderr.read().decode("utf-8", "replace").strip() if proc.stderr else ""
    proc.wait()
    if fds:
        for extra in fds[1:]:
            os.close(extra)
        return fds[0]
    low = err.lower()
    if not err or "cancel" in low or "-60006" in low:
        raise Cancelled()
    if "not permitted" in low or "-60005" in low or "denied" in low:
        raise RuntimeError("macOS didn't allow writing to the stick. Open System Settings > Privacy & Security > "
                           "Full Disk Access, turn on Terminal, then quit Terminal and start Setup again.")
    raise RuntimeError(f"macOS couldn't open the stick: {err}")


def _mac_write(drive, path, size, expected):
    dev, raw = "/dev/" + drive["id"], "/dev/r" + drive["id"]
    if drive.get("test"):
        dev = raw = TEST_DEVICE
    set_state(phase="preparing")
    r = run(["diskutil", "unmountDisk", "force", dev], timeout=90) if not drive.get("test") else run(["true"])
    if r.returncode != 0:
        why = (r.stderr or r.stdout).strip().splitlines()
        raise RuntimeError("Couldn't get the stick ready" + (f" ({why[-1]})" if why else "") +
                           ". Close any windows or apps using it and try again.")
    set_state(phase="password")
    fd = _authopen(raw, os.O_RDWR)
    try:
        pwrite, pread = _fd_io(fd)
        write_and_verify(path, size, expected, pwrite, pread, _progress)
    finally:
        os.close(fd)
    set_state(phase="finishing")
    if not drive.get("test"):
        run(["diskutil", "eject", dev], timeout=90)

# ----------------------------------------------------------------- Windows and Linux: an elevated helper

class _WinProcess:
    """The elevated helper on Windows, started with ShellExecuteExW("runas")."""

    def __init__(self, args):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes

        class SHELLEXECUTEINFOW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                        ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                        ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
        shell32.ShellExecuteExW.restype = wintypes.BOOL
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.k32.WaitForSingleObject.restype = wintypes.DWORD
        self.k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.k32.GetExitCodeProcess.restype = wintypes.BOOL
        self.k32.CloseHandle.argtypes = [wintypes.HANDLE]
        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(sei)
        sei.fMask = 0x00000040 | 0x00000400          # SEE_MASK_NOCLOSEPROCESS | SEE_MASK_FLAG_NO_UI
        sei.lpVerb = "runas"
        sei.lpFile = sys.executable
        sei.lpParameters = subprocess.list2cmdline(args)
        sei.nShow = 0                                 # SW_HIDE: progress shows on the page
        if not shell32.ShellExecuteExW(ctypes.byref(sei)):
            code = ctypes.get_last_error()
            if code == 1223:                          # ERROR_CANCELLED: "No" on the Windows prompt
                raise Cancelled()
            raise RuntimeError(f"Windows couldn't start the writer (error {code}). Use an administrator account.")
        self.handle = sei.hProcess

    def poll(self):
        if self.k32.WaitForSingleObject(self.handle, 0) != 0:      # WAIT_OBJECT_0 once it has exited
            return None
        code = self.wintypes.DWORD()
        self.k32.GetExitCodeProcess(self.handle, self.ctypes.byref(code))
        self.k32.CloseHandle(self.handle)
        return code.value


def _elevated_write(drive, path, size, expected):
    fd, progress = tempfile.mkstemp(prefix="llmos-setup-", suffix=".json")
    os.close(fd)
    args = [os.path.abspath(__file__), "--write-helper", path, drive["id"], progress, expected or "-"]
    set_state(phase="password")
    if OS == "windows":
        proc = _WinProcess(args)
    else:
        for n in _walk((_lsblk(drive["id"]) or [{}])[0]):      # let the desktop release an automounted stick
            if n.get("mountpoint") and n.get("name") and shutil.which("udisksctl"):
                run(["udisksctl", "unmount", "-b", "/dev/" + n["name"]], timeout=30)
        if shutil.which("pkexec"):
            proc = subprocess.Popen(["pkexec", sys.executable] + args, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:                                          # no polkit: sudo asks in the window Setup was started from
            log("Type your password here to let Setup write to the stick:")
            proc = subprocess.Popen(["sudo", sys.executable] + args)
    last, rc = {}, None
    try:
        while rc is None:
            time.sleep(0.4)
            rc = proc.poll()
            try:
                with open(progress, encoding="utf-8") as f:
                    last = json.loads(f.read() or "{}")
            except (OSError, ValueError):
                pass
            if last.get("phase") in ("preparing", "writing", "verifying"):
                set_state(phase=last["phase"], done=int(last.get("done") or 0))
    finally:
        try:
            os.remove(progress)
        except OSError:
            pass
    if last.get("phase") == "done":
        return
    if last.get("error"):
        raise RuntimeError(last["error"])
    if OS == "linux" and rc in (126, 127) and not last:
        raise Cancelled()
    raise RuntimeError("The writer stopped before it finished. Try again with the stick plugged straight into this computer.")


def helper_main(path, device, progress, expected):
    """The elevated part (Windows, Linux): write the image to `device` and report through `progress`."""
    expected = "" if expected == "-" else expected
    sent = [0.0]

    def report(force=False, **kw):
        if not force and time.time() - sent[0] < 0.25:
            return
        sent[0] = time.time()
        tmp = progress + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(kw, f)
        for _ in range(60):        # Windows refuses the swap while Setup has the file open to read it: try again
            try:
                os.replace(tmp, progress)
                return
            except PermissionError:
                time.sleep(0.05)

    try:
        size = os.path.getsize(path)
        report(force=True, phase="preparing")
        step = lambda phase, done: report(phase=phase, done=done)      # noqa: E731
        if OS == "windows":
            _win_helper_write(path, device, size, expected, step)
        else:
            _linux_helper_write(path, device, size, expected, step)
        report(force=True, phase="done")
        return 0
    except Exception as e:
        report(force=True, phase="error", error=str(e) or e.__class__.__name__)
        return 1


def _win_helper_write(path, number, size, expected, step):
    number = int(number)
    r = _ps(f"$d = Get-Disk -Number {number}; [pscustomobject]@{{ Bus = [string]$d.BusType; "
            "System = [bool]$d.IsSystem; Boot = [bool]$d.IsBoot }} | ConvertTo-Json -Compress")
    try:
        info = json.loads(r.stdout or "{}")
    except ValueError:
        info = {}
    if info.get("Bus") not in ("USB", "SD", "MMC") or info.get("System") or info.get("Boot"):
        raise RuntimeError("That disk isn't a USB stick, so it was not written.")
    fd, script = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write(f"select disk {number}\nclean\n")     # Windows lets go of the stick's drives
    try:
        r = run(["diskpart", "/s", script], timeout=180)
    finally:
        os.remove(script)
    if r.returncode != 0:
        lines = [x for x in (r.stdout or "").splitlines() if x.strip()]
        raise RuntimeError("Windows couldn't prepare the stick" + (f": {lines[-1].strip()}" if lines else "") +
                           ". Close any windows showing the stick and try again.")
    time.sleep(2)
    with open(rf"\\.\PhysicalDrive{number}", "r+b", buffering=0) as d:
        def pwrite(view, offset):
            d.seek(offset)
            done = 0
            while done < len(view):
                n = d.write(view[done:])
                if not n:
                    raise RuntimeError("The stick stopped accepting data. Is it still plugged in?")
                done += n

        def pread(view, offset):
            d.seek(offset)
            got = 0
            while got < len(view):
                n = d.readinto(view[got:])
                if not n:
                    raise RuntimeError("The stick stopped answering while it was being checked.")
                got += n
        write_and_verify(path, size, expected, pwrite, pread, step, flush=lambda: os.fsync(d.fileno()))


def _linux_helper_write(path, device, size, expected, step):
    if not re.fullmatch(r"/dev/[a-z0-9]+", device):
        raise RuntimeError("That isn't a whole disk, so it was not written.")
    disks = _lsblk(device)
    disk = disks[0] if disks else {}
    removable = str(disk.get("rm")).lower() in ("1", "true") or disk.get("tran") == "usb"
    if disk.get("type") != "disk" or not removable:
        raise RuntimeError("That disk isn't a USB stick, so it was not written.")
    why = _linux_blocker(disk)
    if why:
        raise RuntimeError(f"That disk was not written: {why}.")
    for n in _walk(disk):
        if n.get("mountpoint") and run(["umount", "/dev/" + n["name"]], timeout=60).returncode != 0:
            raise RuntimeError(f"Couldn't unmount {n['mountpoint']}. Close anything using the stick and try again.")
    fd = os.open(device, os.O_RDWR | os.O_EXCL | getattr(os, "O_CLOEXEC", 0))

    def flush():                   # to the stick, then out of the page cache so the check reads the stick itself
        os.fsync(fd)
        if hasattr(os, "posix_fadvise"):
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    try:
        pwrite, pread = _fd_io(fd)
        write_and_verify(path, size, expected, pwrite, pread, step, flush=flush)
    finally:
        os.close(fd)

# ----------------------------------------------------------------- trying it in a window

def vm_plan():
    image = "llmos-arm64.iso" if ARCH == "arm64" else "llmos-x86_64.iso"
    plan = {"image": image, "have_image": os.path.isfile(os.path.join(FILES, image)),
            "low_memory": 0 < ram_gb() < 7.5}
    if OS == "mac":
        launcher, disk = os.path.join(FILES, "run-llmos.sh"), os.path.join(FILES, "llmos-arm64.qcow2")
        qemu = shutil.which("qemu-system-aarch64") or next(
            (p for p in ("/opt/homebrew/bin/qemu-system-aarch64", "/usr/local/bin/qemu-system-aarch64") if os.path.exists(p)), None)
        if ARCH == "arm64" and qemu and os.path.isfile(launcher) and os.path.isfile(disk):
            plan["method"] = "launcher"
        else:
            plan.update(method="utm", installed=os.path.isdir("/Applications/UTM.app"))
    elif OS == "windows":
        if ARCH == "arm64":
            plan["method"] = "none"
        else:
            plan.update(method="virtualbox", installed=bool(shutil.which("VBoxManage")) or os.path.exists(
                os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Oracle", "VirtualBox", "VirtualBox.exe")))
    else:
        plan.update(method="boxes", installed=bool(shutil.which("gnome-boxes") or shutil.which("virt-manager")))
    return plan


def _reveal(path):
    if OS == "mac":
        subprocess.Popen(["open", "-R", path])
    elif OS == "windows":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def do_open(what):
    """The page's buttons: only these fixed actions exist."""
    plan = vm_plan()
    try:
        if what == "image":
            path = os.path.join(FILES, plan["image"])
            if not os.path.isfile(path):
                return {"ok": False, "error": "This copy of LLM OS doesn't include that file."}
            _reveal(path)
        elif what == "get-app":
            webbrowser.open({"utm": UTM_URL, "virtualbox": VBOX_URL, "boxes": BOXES_URL}.get(plan.get("method"), UTM_URL))
        elif what == "open-app":
            if OS == "mac" and plan.get("method") == "utm":
                subprocess.Popen(["open", "-a", "UTM"])
            elif OS == "windows":
                exe = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Oracle", "VirtualBox", "VirtualBox.exe")
                subprocess.Popen([exe] if os.path.exists(exe) else ["VirtualBox"])
            else:
                subprocess.Popen(["gnome-boxes"] if shutil.which("gnome-boxes") else ["virt-manager"])
        elif what == "start" and plan.get("method") == "launcher":
            launcher = os.path.join(FILES, "run-llmos.sh")
            run(["xattr", "-d", "com.apple.quarantine", launcher], timeout=10)   # a downloaded copy is quarantined
            subprocess.Popen(["open", "-a", "Terminal", launcher])
        else:
            return {"ok": False, "error": "Unknown action."}
        return {"ok": True}
    except OSError as e:
        return {"ok": False, "error": str(e)}

# ----------------------------------------------------------------- the local web app

def _page_script_hash():
    """The CSP source for the page's one inline script (its SHA-256), so no other script can run in the page."""
    try:
        with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
            code = f.read().split("<script>", 1)[1].split("</script>", 1)[0]
        return "'sha256-" + base64.b64encode(hashlib.sha256(code.encode("utf-8")).digest()).decode() + "'"
    except (OSError, IndexError):
        return "'none'"


PAGE_SCRIPT_HASH = _page_script_hash()


def status():
    start_image_check()
    return {"version": version(), "host": host(), "vm": vm_plan(),
            "usb": {"image": USB_IMAGE, "state": CHECK["state"]}}


def progress():
    with LOCK:
        st = {k: v for k, v in STATE.items()}
    st["elapsed"] = round(time.time() - st["started"], 1) if st["started"] else 0
    return st


class Handler(http.server.BaseHTTPRequestHandler):
    # Every response: no framing (clickjacking), no caching, no content sniffing, and a CSP that allows only this
    # page's own inline script (by hash) and requests back to this server.
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; script-src %s; "
                                    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
    }

    def log_message(self, *a):
        pass

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
        """CSRF / cross-origin gate. The Host must be this loopback address (blocks DNS rebinding); any Origin or
        Referer present must be this origin; every /api call must carry the per-launch token in a custom header,
        which another site can neither read nor send without a CORS preflight this server never approves."""
        port = self.server.server_address[1]
        host_hdr = self.headers.get("Host", "")
        if host_hdr not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False
        origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if origin and not (origin == f"http://{host_hdr}" or origin.startswith(f"http://{host_hdr}/")):
            return False
        if need_token:
            sent = self.headers.get("X-LLMOS-Token", "")
            if not TOKEN or not hmac.compare_digest(sent, TOKEN):
                return False
        return True

    def do_OPTIONS(self):
        self.send_json({"error": "forbidden"}, 403)       # no CORS, ever

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
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
            self.send_json(status())
        elif path == "/api/drives":
            self.send_json(list_drives())
        elif path == "/api/progress":
            self.send_json(progress())
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if not self.authorized(need_token=True):
            return self.send_json({"error": "forbidden"}, 403)
        try:
            length = min(int(self.headers.get("Content-Length", 0) or 0), 65536)
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if path == "/api/write":
            why = start_write(str(data.get("drive", "")))
            return self.send_json({"ok": not why, "error": why})
        if path == "/api/open":
            return self.send_json(do_open(str(data.get("what", ""))))
        if path == "/api/quit":
            self.send_json({"ok": True})
            threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
            return
        self.send_json({"error": "not found"}, 404)


def main():
    global TOKEN
    if len(sys.argv) >= 6 and sys.argv[1] == "--write-helper":
        sys.exit(helper_main(*sys.argv[2:6]))
    TOKEN = secrets.token_urlsafe(24)
    port = int(os.environ.get("LLMOS_SETUP_PORT", "0") or 0)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/#{TOKEN}"
    print("\n  LLM OS Setup is open in your web browser.")
    print("  Keep this window open while you use it. Close it when you're done.\n")
    print(f"  (If the browser didn't open, paste this address into it: {url})\n", flush=True)
    start_image_check()
    if not os.environ.get("LLMOS_SETUP_NO_BROWSER"):
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
