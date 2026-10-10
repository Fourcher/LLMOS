"""The system's own panels, built from the machine itself (no model involved), so they open in an instant:
what is running (a task manager), drives (USB sticks: open, eject), displays (a second screen: extend, mirror),
Bluetooth (pair, connect), printers (add, test) and "about this computer". Each returns a window spec; the actions
are short phrases the desk handles itself (desk.Desk.shortcut).
"""
import json
import os
import re
import shutil
import subprocess
import time

from . import config, system, version_line

FRIENDLY = {"llama-server": "the on-device model", "WebKitWebProcess": "the desk (screen)", "WebKitWebProces": "the desk (screen)",
            "WebKitNetworkProcess": "the desk (network)", "WebKitNetworkPr": "the desk (network)", "labwc": "windows",
            "python3": "LLM OS", "firefox": "Firefox", "firefox-esr": "Firefox", "foot": "Terminal", "mpv": "media player",
            "thunar": "Files", "Thunar": "Files", "mousepad": "Text editor", "abiword": "AbiWord", "gnumeric": "Gnumeric",
            "whisper-cli": "speech to text", "tor": "Tor", "pipewire": "sound", "wireplumber": "sound", "cupsd": "printing",
            "bluetoothd": "Bluetooth"}
PROTECTED = {"labwc", "python3", "WebKitWebProces", "WebKitNetworkPr", "seatd", "dbus-daemon", "init", "llama-server", "pipewire", "wireplumber", "pipewire-pulse", "at-spi-bus-laun", "at-spi2-registr"}


def _run(argv, timeout=10):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "it took too long to answer"
    except OSError:
        return 1, "", "this system doesn't have " + argv[0] + " installed"
    except subprocess.SubprocessError as e:
        return 1, "", str(e)


def _human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


# ---- what is running

def _procs():
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as f:
                st = f.read()
            comm = st[st.index("(") + 1:st.rindex(")")]
            fields = st[st.rindex(")") + 2:].split()
            ticks = int(fields[11]) + int(fields[12])
            with open(f"/proc/{d}/statm") as f:
                rss = int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
            out[int(d)] = (comm, ticks, rss)
        except (OSError, ValueError, IndexError):
            continue
    return out


def processes(limit=14):
    a = _procs()
    t0 = time.time()
    time.sleep(0.6)
    b = _procs()
    dt = (time.time() - t0) * os.sysconf("SC_CLK_TCK")
    ncpu = os.cpu_count() or 1
    rows = []
    for pid, (comm, ticks, rss) in b.items():
        if rss < 4 * 1024 * 1024:
            continue
        cpu = max(0.0, (ticks - a.get(pid, (comm, ticks, rss))[1]) / dt * 100 / ncpu) if dt else 0
        rows.append((rss, cpu, pid, comm))
    rows.sort(reverse=True)
    try:
        with open("/proc/meminfo") as f:
            mi = {ln.split(":")[0]: int(ln.split()[1]) * 1024 for ln in f}
        used = mi["MemTotal"] - mi.get("MemAvailable", mi.get("MemFree", 0))
        mem = f"{_human(used)} of {_human(mi['MemTotal'])} in use"
    except (OSError, KeyError, ValueError):
        mem = ""
    # one row per thing a person knows ("sound", "LLM OS", "Firefox"), its processes added up
    groups = {}
    for rss, cpu, pid, comm in rows:
        name = FRIENDLY.get(comm, comm)
        g = groups.setdefault(name, {"rss": 0, "cpu": 0.0, "pids": [], "comms": set()})
        g["rss"] += rss
        g["cpu"] += cpu
        g["pids"].append(pid)
        g["comms"].add(comm)
    items = []
    for name, g in sorted(groups.items(), key=lambda kv: -kv[1]["rss"])[:limit]:
        protected = bool(g["comms"] & PROTECTED)
        acts = [] if protected else [{"label": "End", "say": f"end process {g['pids'][0]}", "danger": True}] if len(g["pids"]) == 1 else \
            [{"label": "End", "say": "force quit " + next(iter(g["comms"])), "danger": True}]
        note = " (most of it is the model file, shared and freed when needed)" if "llama-server" in g["comms"] else ""
        items.append({"title": name, "subtitle": f"{_human(g['rss'])} memory{note} · {g['cpu']:.0f}% processor",
                      "actions": acts})
    return {"id": "panel-processes", "replace": True, "title": "What's running", "size": "m", "slot": "side", "blocks": [
        {"type": "text", "text": mem, "dim": True},
        {"type": "list", "items": items},
        {"type": "buttons", "items": [{"label": "Refresh", "say": "task manager"}]}]}


def end_process(pid):
    try:
        with open(f"/proc/{pid}/comm") as f:
            comm = f.read().strip()
    except OSError:
        return False, "that program has already ended"
    if comm in PROTECTED:
        return False, f"{FRIENDLY.get(comm, comm)} is part of the system and keeps running"
    try:
        os.kill(int(pid), 15)
        for _ in range(20):
            time.sleep(0.1)
            if not os.path.exists(f"/proc/{pid}"):
                return True, f"ended {FRIENDLY.get(comm, comm)}"
        os.kill(int(pid), 9)
        return True, f"ended {FRIENDLY.get(comm, comm)} (it did not respond, so it was stopped)"
    except OSError as e:
        return False, str(e)


def friendly_name(pid):
    try:
        with open(f"/proc/{pid}/comm") as f:
            c = f.read().strip()
        return FRIENDLY.get(c, c)
    except OSError:
        return str(pid)


# ---- drives (USB sticks, SD cards, external disks)

def _blk():
    rc, out, _ = _run(["lsblk", "-J", "-b", "-o", "NAME,PATH,SIZE,TYPE,RM,HOTPLUG,TRAN,LABEL,FSTYPE,MOUNTPOINT,MODEL,VENDOR"])
    if rc:
        return []
    try:
        return json.loads(out).get("blockdevices", [])
    except ValueError:
        return []


def removable():
    """[{path, label, size, fstype, mountpoint, disk}] for partitions on removable/USB disks."""
    out = []
    root = os.path.realpath(_run(["findmnt", "-no", "SOURCE", "/"])[1].strip() or "/")
    for d in _blk():
        if d.get("type") != "disk" or not (d.get("rm") or d.get("hotplug") or d.get("tran") == "usb"):
            continue
        name = " ".join(x for x in ((d.get("vendor") or "").strip(), (d.get("model") or "").strip()) if x) or d.get("name")
        parts = d.get("children") or [d]
        for p in parts:
            if not p.get("fstype") or p.get("path") == root or p.get("fstype") in ("iso9660", "squashfs"):
                continue
            out.append({"path": p["path"], "label": p.get("label") or name, "size": _human(int(p.get("size") or 0)),
                        "fstype": p["fstype"], "mountpoint": p.get("mountpoint") or "", "disk": d["path"]})
    return out


def mount(dev):
    if shutil.which("udisksctl"):
        rc, out, err = _run(["udisksctl", "mount", "-b", dev, "--no-user-interaction"], 30)
        m = re.search(r" at (.+?)\.?$", out.strip())
        if rc == 0 and m:
            return True, m.group(1)
    mp = os.path.join("/media", os.path.basename(dev))
    os.makedirs(mp, exist_ok=True)
    rc, out, err = _run(["mount", dev, mp], 30)
    return (rc == 0, mp if rc == 0 else (err.strip() or "could not open the drive"))


def eject(dev):
    """Unmount every partition of the drive and power it off: safe to pull out."""
    disk = next((x["disk"] for x in removable() if x["path"] == dev or x["disk"] == dev), dev)
    _run(["sync"], 60)
    busy = []
    for x in removable():
        if x["disk"] == disk and x["mountpoint"]:
            rc, _, err = _run(["umount", x["mountpoint"]], 30)
            if rc:
                busy.append(x["mountpoint"])
    if busy:
        rc, out, _ = _run(["fuser", "-m"] + busy, 10)
        return False, "still in use: close the files or programs using it, then eject again"
    if shutil.which("udisksctl"):
        _run(["udisksctl", "power-off", "-b", disk, "--no-user-interaction"], 20)
    return True, "safe to remove"


def drives():
    ds = removable()
    if not ds:
        blocks = [{"type": "text", "text": "No USB stick or external drive is plugged in."}]
    else:
        blocks = [{"type": "list", "items": [{"title": d["label"], "subtitle": f"{d['size']} · {d['fstype']}" + (" · open" if d["mountpoint"] else ""),
                                              "actions": [{"label": "Open", "say": f"open drive {d['path']}", "primary": True},
                                                          {"label": "Eject", "say": f"eject drive {d['path']}"}]} for d in ds]}]
    blocks.append({"type": "buttons", "items": [{"label": "Refresh", "say": "drives"}]})
    return {"id": "panel-drives", "replace": True, "title": "Drives", "size": "s", "slot": "side", "blocks": blocks}


# ---- displays

def _outputs():
    if not shutil.which("wlr-randr"):
        return None
    rc, out, _ = _run(["wlr-randr", "--json"])
    if rc:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def displays():
    outs = _outputs()
    if outs is None:
        return {"id": "panel-displays", "replace": True, "title": "Displays", "size": "s", "slot": "side",
                "blocks": [{"type": "text", "text": "The display settings tool is not available on this system."}]}
    items = []
    for o in outs:
        cur = next((m for m in o.get("modes", []) if m.get("current")), {})
        items.append({"title": o.get("description") or o.get("name"), "subtitle": f"{o.get('name')} · {cur.get('width', '?')}×{cur.get('height', '?')}"
                      + ("" if o.get("enabled", True) else " · off")})
    blocks = [{"type": "list", "items": items}]
    for o in outs[:2]:
        modes = sorted({(m["width"], m["height"]) for m in o.get("modes", []) if m.get("width")}, reverse=True)[:6]
        if len(modes) > 1:
            blocks += [{"type": "heading", "text": f"Resolution: {o.get('name')}"},
                       {"type": "buttons", "items": [{"label": f"{w}×{h}", "say": f"set resolution {o['name']} {w}x{h}"} for w, h in modes]}]
    if len(outs) > 1:
        blocks.append({"type": "buttons", "items": [{"label": "Extend", "say": "extend the displays", "primary": True},
                                                    {"label": "Mirror", "say": "mirror the displays"},
                                                    {"label": "Only this screen", "say": "use only the main display"},
                                                    {"label": "Only the projector / TV", "say": "use only the projector"}]})
    else:
        blocks.append({"type": "text", "text": "Plug in a second screen and it appears here.", "dim": True})
    return {"id": "panel-displays", "replace": True, "title": "Displays", "size": "s", "slot": "side", "blocks": blocks}


def arrange(how):
    outs = [o for o in (_outputs() or [])]
    if len(outs) < 2:
        return False, "there is only one screen"
    main, rest = outs[0], outs[1:]
    if how == "projector":
        for o in rest:
            _run(["wlr-randr", "--output", o["name"], "--on", "--pos", "0,0"])
        _run(["wlr-randr", "--output", main["name"], "--off"])
        return True, "only the second screen (the projector or TV) is on; say \u201cuse both screens\u201d to bring this one back"
    cur = next((m for m in main.get("modes", []) if m.get("current")), {"width": 1920})
    x = int(cur.get("width", 1920))
    for o in rest:
        if how == "mirror":
            # the same picture: a resolution both screens have, or else the second screen scaled to show the whole first one
            sizes = lambda out: {(int(m["width"]), int(m["height"])) for m in out.get("modes", []) if m.get("width")}
            common = sorted(sizes(main) & sizes(o), key=lambda wh: -wh[0] * wh[1])
            if common:
                w, h = common[0]
                _run(["wlr-randr", "--output", main["name"], "--mode", f"{w}x{h}"])
                _run(["wlr-randr", "--output", o["name"], "--on", "--pos", "0,0", "--mode", f"{w}x{h}", "--scale", str(main.get("scale", 1) or 1)])
            else:
                om = next((m for m in o.get("modes", []) if m.get("current") or m.get("preferred")), None) or {"width": x}
                sc = max(0.5, min(4.0, int(om["width"]) / max(1, x / float(main.get("scale", 1) or 1))))
                _run(["wlr-randr", "--output", o["name"], "--on", "--pos", "0,0", "--scale", f"{sc:.3f}"])
        elif how == "only":
            _run(["wlr-randr", "--output", o["name"], "--off"])
        elif how == "projector":
            _run(["wlr-randr", "--output", o["name"], "--on", "--pos", "0,0"])
        else:
            _run(["wlr-randr", "--output", o["name"], "--on", "--pos", f"{x},0"])
            m = next((m for m in o.get("modes", []) if m.get("current")), {"width": 1920})
            x += int(m.get("width", 1920))
    if how == "projector":
        return True, "only the second screen (the projector or TV) is on"
    return True, {"mirror": "the screens show the same picture", "only": "only the main screen is on"}.get(how, "the screens are side by side")


# ---- Bluetooth

def _btctl(*args, timeout=15):
    return _run(["bluetoothctl", *args], timeout)


def bluetooth(scan=False):
    import glob
    if not glob.glob("/sys/class/bluetooth/hci*"):                 # no adapter: say so at once (bluetoothctl would wait)
        return {"id": "panel-bluetooth", "replace": True, "title": "Bluetooth", "size": "s", "slot": "side",
                "blocks": [{"type": "text", "text": "This computer has no Bluetooth adapter (or it is switched off in the firmware)."}]}
    if not shutil.which("bluetoothctl"):
        return {"id": "panel-bluetooth", "replace": True, "title": "Bluetooth", "size": "s", "slot": "side",
                "blocks": [{"type": "text", "text": "Bluetooth is not available on this system."}]}
    rc, out, _ = _btctl("show")
    if rc or "Controller" not in out:
        return {"id": "panel-bluetooth", "replace": True, "title": "Bluetooth", "size": "s", "slot": "side",
                "blocks": [{"type": "text", "text": "This computer has no Bluetooth adapter (or it is switched off in the firmware)."}]}
    powered = "Powered: yes" in out
    if scan and powered:
        _run(["bluetoothctl", "--timeout", "8", "scan", "on"], 15)
    rc, devs, _ = _btctl("devices")
    rc2, paired, _ = _btctl("devices", "Paired")
    paired_ids = set(re.findall(r"Device ([0-9A-F:]{17})", paired))
    items = []
    for mac, name in re.findall(r"Device ([0-9A-F:]{17}) (.+)", devs):
        info = _btctl("info", mac)[1]
        conn = "Connected: yes" in info
        acts = ([{"label": "Disconnect", "say": f"bluetooth disconnect {mac}"}] if conn else
                [{"label": "Connect" if mac in paired_ids else "Pair", "say": f"bluetooth connect {mac}", "primary": True}])
        if mac in paired_ids:
            acts.append({"label": "Forget", "say": f"bluetooth forget {mac}", "danger": True})
        items.append({"title": name, "subtitle": ("connected" if conn else "paired" if mac in paired_ids else "nearby"), "actions": acts})
    blocks = [{"type": "toggle", "label": "Bluetooth", "on": powered, "say_on": "bluetooth on", "say_off": "bluetooth off"}]
    blocks.append({"type": "list", "items": items} if items else {"type": "text", "text": "No devices yet: put the device in pairing mode and press Search.", "dim": True})
    blocks.append({"type": "buttons", "items": [{"label": "Search", "say": "bluetooth search", "primary": True}]})
    return {"id": "panel-bluetooth", "replace": True, "title": "Bluetooth", "size": "s", "slot": "side", "blocks": blocks}


def bt_action(act, mac=""):
    if act in ("on", "off"):
        import glob
        if not glob.glob("/sys/class/bluetooth/hci*"):
            return False, "this computer has no Bluetooth adapter"
        rc, out, err = _btctl("power", act, timeout=6)
        if rc != 0:
            return False, "couldn't switch Bluetooth " + act + ": " + (err or out).strip()[:120]
        return True, f"Bluetooth is {act}"
    if act == "connect":
        _btctl("trust", mac)
        info = _btctl("info", mac)[1]
        if "Paired: yes" not in info:
            rc, out, err = _btctl("pair", mac, timeout=30)
            if rc and "AlreadyExists" not in out + err:
                return False, "pairing failed: put the device in pairing mode and try again"
        rc, out, err = _btctl("connect", mac, timeout=30)
        return rc == 0 and "successful" in out.lower(), ("connected" if rc == 0 else "could not connect: is the device on and nearby?")
    if act == "disconnect":
        rc, out, err = _btctl("disconnect", mac)
        return rc == 0, "disconnected"
    if act == "forget":
        rc, out, err = _btctl("remove", mac)
        return rc == 0, "forgotten"
    return False, "unknown Bluetooth action"


# ---- printers (CUPS; modern printers print without a driver)

def printers():
    if not shutil.which("lpstat"):
        return {"id": "panel-printers", "replace": True, "title": "Printers", "size": "s", "slot": "side",
                "blocks": [{"type": "text", "text": "Printing is not available on this system."}]}
    rc, out, _ = _run(["lpstat", "-p", "-d"])
    default = (re.search(r"system default destination: (\S+)", out) or [None, ""])[1]
    items = [{"title": n + (" (default)" if n == default else ""), "subtitle": "ready" if "idle" in st else st.strip(),
              "actions": [{"label": "Test page", "say": f"print a test page on {n}"}] + ([] if n == default else [{"label": "Make default", "say": f"make {n} the default printer"}])}
             for n, st in re.findall(r"printer (\S+) (?:is )?(.+?)\.", out)]
    found = []
    if shutil.which("lpinfo"):
        rc, devs, _ = _run(["lpinfo", "--include-schemes", "ipp,ipps,dnssd,usb", "-v"], 25)
        found = [ln.split(None, 1)[1] for ln in devs.splitlines() if ln.startswith(("network", "direct")) and "://" in ln]
    known = {i["title"].split(" (")[0] for i in items}
    adds = [{"title": re.sub(r"%20", " ", re.sub(r"^\w+://", "", u)).split("/")[0][:60] or u, "subtitle": u[:80],
             "actions": [{"label": "Add", "say": f"add printer {u}", "primary": True}]} for u in found[:10]]
    blocks = [{"type": "list", "items": items} if items else {"type": "text", "text": "No printer is set up yet.", "dim": True}]
    if adds:
        blocks += [{"type": "heading", "text": "Found"}, {"type": "list", "items": [a for a in adds if a["title"] not in known]}]
    blocks.append({"type": "buttons", "items": [{"label": "Look for printers", "say": "printers"}]})
    return {"id": "panel-printers", "replace": True, "title": "Printers", "size": "s", "slot": "side", "blocks": blocks}


def add_printer(uri):
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", re.sub(r"^\w+://", "", uri).split("/")[0].split(".")[0])[:30] or "printer"
    rc, out, err = _run(["lpadmin", "-p", name, "-E", "-v", uri, "-m", "everywhere"], 60)
    if rc:
        return False, (err.strip() or "the printer could not be added")[:200]
    _run(["lpadmin", "-d", name])
    return True, f"{name} is set up and is the default printer"


def test_page(name):
    page = next((p for p in ("/usr/share/cups/data/testprint", "/usr/share/cups/data/default-testpage.pdf") if os.path.exists(p)), None)
    if not page:
        return False, "There is no test page on this system."
    rc, out, err = _run(["lp", "-d", name, page], 30)
    return (True, f"Sent a test page to {name}.") if rc == 0 else (False, (err.strip() or "It could not be printed.")[:200])


def default_printer(name):
    rc, out, err = _run(["lpadmin", "-d", name], 20)
    return (True, f"{name} is now the default printer.") if rc == 0 else (False, (err.strip() or "That did not work.")[:200])


# ---- about this computer

def about():
    rows = []
    try:
        with open("/sys/class/dmi/id/sys_vendor") as f:
            vendor = f.read().strip()
        with open("/sys/class/dmi/id/product_name") as f:
            rows.append(["Computer", f"{vendor} {f.read().strip()}".strip()])
    except OSError:
        pass
    cpu = ""
    try:
        with open("/proc/cpuinfo") as f:
            for ln in f:
                if ln.startswith(("model name", "Model")):
                    cpu = ln.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    rows.append(["Processor", f"{cpu or os.uname().machine} · {os.cpu_count()} cores"])
    try:
        with open("/proc/meminfo") as f:
            total = int(f.readline().split()[1]) * 1024
        rows.append(["Memory", _human(total)])
    except (OSError, ValueError):
        pass
    du = shutil.disk_usage("/")
    rows.append(["Disk", f"{_human(du.free)} free of {_human(du.total)}"])
    rows.append(["System", version_line()])
    rows.append(["Linux", os.uname().release])
    return {"id": "panel-about", "replace": True, "title": "About this computer", "size": "s", "slot": "side",
            "blocks": [{"type": "kv", "rows": rows}]}


# ---- keyboard and mouse (applied by the desk to the compositor: desk.Desk.apply_input)

LAYOUTS = {"us": "English (US)", "gb": "English (UK)", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
           "pt": "Portuguese", "br": "Portuguese (Brazil)", "nl": "Dutch", "be": "Belgian", "ch": "Swiss", "se": "Swedish",
           "no": "Norwegian", "dk": "Danish", "fi": "Finnish", "pl": "Polish", "cz": "Czech", "hu": "Hungarian", "ro": "Romanian",
           "gr": "Greek", "tr": "Turkish", "ru": "Russian", "ua": "Ukrainian", "il": "Hebrew", "ara": "Arabic", "in": "Hindi",
           "jp": "Japanese", "kr": "Korean", "cn": "Chinese", "latam": "Spanish (Latin America)", "ca": "French (Canada)"}
_ALIASES = {"american": "us", "usa": "us", "english": "us", "british": "gb", "uk": "gb", "england": "gb", "german": "de", "germany": "de",
            "french": "fr", "france": "fr", "spanish": "es", "spain": "es", "italian": "it", "portuguese": "pt", "brazilian": "br",
            "dutch": "nl", "swiss": "ch", "swedish": "se", "norwegian": "no", "danish": "dk", "finnish": "fi", "polish": "pl",
            "czech": "cz", "hungarian": "hu", "romanian": "ro", "greek": "gr", "turkish": "tr", "russian": "ru", "ukrainian": "ua",
            "hebrew": "il", "arabic": "ara", "hindi": "in", "japanese": "jp", "korean": "kr", "chinese": "cn", "latin american": "latam",
            "canadian": "ca", "canadian french": "ca", "azerty": "fr", "qwertz": "de", "qwerty": "us"}


def layout_code(words):
    w = re.sub(r"\b(an?|the|keyboard|layout|please|instead)\b", " ", str(words).lower())
    w = re.sub(r"[()]", " ", w)
    w = " ".join(w.split())
    if w in LAYOUTS:
        return w
    if w in _ALIASES:
        return _ALIASES[w]
    for code, name in LAYOUTS.items():
        if w and w == " ".join(re.sub(r"[()]", " ", name.lower()).split()):
            return code
    return None


def input_panel():
    inp = config.settings.get("input", {}) or {}
    cur = inp.get("layout", "us")
    common = ["us", "gb", "de", "fr", "es", "it", "pt", "br", "nl", "se", "pl", "ru", "jp", "latam", "ca", "ch"]
    sp = float(inp.get("pointer_speed", 0))
    blocks = [{"type": "heading", "text": "Keyboard layout"},
              {"type": "choices", "selected": LAYOUTS.get(cur, cur),
               "items": [{"label": LAYOUTS[c], "say": f"keyboard layout {c}"} for c in common]},
              {"type": "text", "text": "Another one: say \"use a Greek keyboard\".", "dim": True},
              {"type": "heading", "text": "Key repeat"},
              {"type": "buttons", "items": [{"label": "Slower", "say": "key repeat slower"}, {"label": "Normal", "say": "key repeat normal"},
                                            {"label": "Faster", "say": "key repeat faster"}]},
              {"type": "heading", "text": "Mouse and touchpad"},
              {"type": "kv", "rows": [["Pointer speed", "normal" if sp == 0 else f"{'+' if sp > 0 else ''}{int(sp * 100)}%"]]},
              {"type": "buttons", "items": [{"label": "Slower", "say": "mouse slower"}, {"label": "Normal", "say": "mouse normal speed"},
                                            {"label": "Faster", "say": "mouse faster"}]},
              {"type": "toggle", "label": "Natural scrolling (touchpad)", "on": bool(inp.get("natural_scroll", True)),
               "say_on": "natural scrolling on", "say_off": "natural scrolling off"},
              {"type": "toggle", "label": "Tap to click", "on": bool(inp.get("tap", True)), "say_on": "tap to click on", "say_off": "tap to click off"},
              {"type": "toggle", "label": "Left-handed buttons", "on": bool(inp.get("left_handed")),
               "say_on": "left handed mouse on", "say_off": "left handed mouse off"}]
    return {"id": "panel-input", "replace": True, "title": "Keyboard and mouse", "size": "m", "slot": "side", "blocks": blocks}


def set_mode(output, mode):
    if not shutil.which("wlr-randr"):
        return False, "the display settings tool is not available"
    outs = {o["name"].lower(): o["name"] for o in (_outputs() or [])}
    name = outs.get(output.lower())
    if not name:
        return False, f"no screen called {output}"
    rc, out, err = _run(["wlr-randr", "--output", name, "--mode", mode])
    return rc == 0, (f"{name} is now {mode}" if rc == 0 else (err.strip() or "that resolution did not work"))


def rotate(how, output=None):
    """Turn the picture: 'left' (90), 'right' (270), 'upside down' (180), 'normal'."""
    if not shutil.which("wlr-randr"):
        return False, "the display settings tool is not available"
    outs = _outputs() or []
    if not outs:
        return False, "no screen found"
    o = next((x for x in outs if output and x["name"].lower() == output.lower()), outs[0])
    t = {"left": "90", "right": "270", "upside down": "180", "normal": "normal"}.get(how, "normal")
    rc, out, err = _run(["wlr-randr", "--output", o["name"], "--transform", t])
    return rc == 0, ("Rotated the screen." if t != "normal" else "The screen is the right way up.") if rc == 0 else (err.strip() or "that did not work")


def first_output():
    outs = _outputs() or []
    return outs[0]["name"] if outs else None


def sleep():
    """Suspend to RAM (the vault stays as it is; the screen asks for nothing extra on waking)."""
    system.power("suspend")


# ---- storage: what fills the disk, and what can go

def _du(path):
    total = 0
    for d, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(d, f)).st_size
            except OSError:
                pass
    return total


def storage():
    du = shutil.disk_usage("/")
    home = config.home()
    parts = []
    for name in ("Documents", "Downloads", "Pictures", "Music", "Videos", "Desktop", "Apps"):
        p = os.path.join(home, name)
        if os.path.isdir(p):
            parts.append([name, _human(_du(p))])
    trash = os.path.join(home, ".Trash")
    caches = [os.path.join(home, ".cache"), "/var/cache/apk", "/var/cache/llmos/mesa"]
    t_size, c_size = _du(trash) if os.path.isdir(trash) else 0, sum(_du(c) for c in caches if os.path.isdir(c))
    models_dir = "/var/lib/llmos/models"
    m_size = _du(models_dir) if os.path.isdir(models_dir) else 0
    blocks = [{"type": "stat", "label": "Disk", "value": f"{_human(du.free)} free of {_human(du.total)}", "fraction": round(1 - du.free / du.total, 3)},
              {"type": "kv", "rows": parts + [["On-device models", _human(m_size)], ["Trash", _human(t_size)], ["Caches", _human(c_size)]]}]
    acts = []
    if t_size:
        acts.append({"label": f"Empty the trash ({_human(t_size)})", "say": "empty the trash", "danger": True})
    if c_size > 1024 * 1024:
        acts.append({"label": f"Clear caches ({_human(c_size)})", "say": "clear the caches"})
    acts.append({"label": "Models", "say": "models"})
    blocks.append({"type": "buttons", "items": acts})
    return {"id": "panel-storage", "replace": True, "title": "Storage", "size": "s", "slot": "side", "blocks": blocks}


def clear_caches():
    freed = 0
    for c in (os.path.join(config.home(), ".cache"), "/var/cache/apk"):
        if not os.path.isdir(c):
            continue
        for n in os.listdir(c):
            p = os.path.join(c, n)
            try:
                size = _du(p) if os.path.isdir(p) else os.lstat(p).st_size
                shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.unlink(p)
                freed += size
            except OSError:
                pass
    return f"cleared {_human(freed)} of caches"


# ---- updates (Alpine's signed package repositories)

def updates_check():
    rc, out, err = _run(["apk", "update"], 120)
    if rc:
        return None, (err.strip() or "could not reach the update server (is the internet on?)")[:200]
    rc, out, err = _run(["apk", "upgrade", "--simulate"], 120)
    pk = re.findall(r"Upgrading (\S+) \((\S+) -> (\S+)\)", out)
    return pk, ""


def updates_panel():
    pk, err = updates_check()
    if pk is None:
        blocks = [{"type": "text", "text": err}]
    elif not pk:
        blocks = [{"type": "text", "text": "Everything is up to date."}]
    else:
        blocks = [{"type": "text", "text": f"{len(pk)} update(s) available."},
                  {"type": "list", "items": [{"title": n, "subtitle": f"{a} → {b}"} for n, a, b in pk[:40]]},
                  {"type": "buttons", "items": [{"label": "Install the updates", "say": "install the updates", "primary": True}]}]
    return {"id": "panel-updates", "replace": True, "title": "Updates", "size": "m", "slot": "side", "blocks": blocks}


def updates_apply():
    rc, out, err = _run(["apk", "upgrade", "--no-interactive"], 1800)
    if rc:
        return False, (err.strip() or out.strip())[-300:]
    kernel = "linux" in out or "vmlinuz" in out
    return True, "updates installed" + ("; restart to use the new system kernel" if kernel else "")


# ---- sound outputs (speakers, headphones, HDMI / TV, Bluetooth) and inputs (microphones)

def _wpenv():
    from . import media
    return dict(os.environ, **(media.desk_env() or {}))


def audio_devices(kind="Sinks"):
    """[(id, name, is_default)] from `wpctl status` (PipeWire): kind 'Sinks' (outputs) or 'Sources' (microphones)."""
    if not shutil.which("wpctl"):
        return []
    try:
        out = subprocess.run(["wpctl", "status"], capture_output=True, text=True, timeout=5, env=_wpenv()).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    devs, inside = [], False
    for ln in out.splitlines():
        if re.search(r"^\s*[\u2502|]?\s*[\u251c\u2514]\u2500\s*" + kind + ":", ln) or re.search(r"\b" + kind + r":\s*$", ln):
            inside = True
            continue
        if inside:
            m = re.search(r"(\*)?\s*(\d+)\.\s+(.+?)(?:\s+\[vol:.*)?$", ln)
            if not m or re.search(r"[\u251c\u2514]\u2500", ln):
                if devs or re.search(r"[\u251c\u2514]\u2500", ln):
                    break
                continue
            devs.append((m.group(2), m.group(3).strip(), bool(m.group(1))))
    return devs


def set_audio_default(dev_id):
    if not shutil.which("wpctl") or not re.fullmatch(r"\d+", str(dev_id)):
        return False
    return subprocess.run(["wpctl", "set-default", str(dev_id)], capture_output=True, timeout=5, env=_wpenv()).returncode == 0
