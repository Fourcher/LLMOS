"""The desk: LLM OS's graphical interface.

One full-screen WebKit view (inside the labwc compositor) renders the
interface the OS generates: windows made from block specs (see uispec.py), a
command bar the owner types or speaks into, the reply as it streams, and the
first-run / unlock screens. Everything is decided here in Python; the page
is a renderer. The two talk in-process (no sockets, no ports):

    page -> python   window.webkit.messageHandlers.llmos.postMessage({...})
    python -> page   llmos.receive({...})   (evaluate_javascript)

The agent runs in a worker thread; every update to the page is marshalled
through GLib.idle_add. Confirmations block that worker on an Event until
the owner answers on screen.

A root-only control socket (/run/llmos/desk.sock) lets `llmos say "..."`
drive the desk from the text console -- that is how the automated tests
exercise the graphical interface.
"""
import glob
import json
import os
import queue
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

from . import clip, record, folderlock, everyday, reset, agent, apps, programs, config, conversation, syspanels, wm, i18n, intent, llm, themes, media, models, store, system, tools, ui, uispec, vault, voice, devices, version_line, waits, replytr

T = i18n.t
PAGE = os.path.join(config.SHARE, "desk", "index.html")
# app-ids testreset must never force-quit, even if someone adds them to wm.PROCS later
NEVER_KILL = {"org.llmos.desk", "python3", "python", "llama-server", "llmos"}
# what the page may send while each screen other than the desk is showing: nothing typed or spoken on the
# lock screen, the first-run wizard or the boot screen may reach the assistant (anything else is dropped)
SCREEN_MESSAGES = {
    "boot": {"ready", "active"},
    "bye": {"ready", "active"},
    "lock": {"ready", "active", "unlock", "cancel"},
    "wizard": {"ready", "active", "wizard", "tz.search", "wifi.scan", "dialog", "cancel", "signin"},
}
_MEDIUM_Q = re.compile(r"\b(?:(?:is|am)\s+(?:this|it|i|llm\s*os)\s+(?:running|booted|working)?\s*(?:off|from|on)\s+(?:the\s+|a\s+)?(?:usb|stick|flash\s*drive|thumb\s*drive|pen\s*drive)|"
                       r"(?:is|was)\s+(?:it|this|llm\s*os)\s+installed|did\s+it\s+install|will\s+(?:my\s+)?(?:stuff|files|things|changes|settings|work|data)\s+(?:be\s+)?(?:saved|kept)|"
                       r"(?:can|what happens if)\s+i\s+(?:unplug|remove|take\s+out)\s+(?:the\s+)?(?:usb|stick|flash\s*drive)|"
                       r"how\s+(?:do|can)\s+i\s+keep\s+(?:this|it|everything|llm\s*os|my\s+(?:stuff|files|things))(?:\s+going)?\s+(?:without|after\s+(?:removing|unplugging))\s+(?:the\s+)?(?:usb|stick|flash\s*drive))", re.I)
_TIME_Q = re.compile(r"(?:what(?:'s| is) the (?:time|date)(?: (?:now|today))?|what time is it(?: now)?|whats the (?:time|date)|whats today(?:'?s date)?|what(?:'s| is) today(?:'s date)?|"
                     r"what day is (?:it|today)|what(?:'s| is) the day today|what is the date today|time|date|today)[?.!]*")
_BATTERY_Q = re.compile(r"(?:how much|what(?:'s| is)(?: my| the)?) battery(?: (?:do i have|is left|level|life|left|percentage))?[?.!]*|"
                        r"(?:what(?:'s| is) (?:my |the )?)?battery(?: level| life| percentage| left)?[?.!]*|how(?:'s| is) (?:my |the )?battery[?.!]*|am i charging[?.!]*|is it charging[?.!]*")
_CLIP_Q = re.compile(r"(?P<what>what(?:'s| is| did i| have i)? (?:on (?:my |the )?clipboard|i copied|did i (?:just )?copy|copied)|what(?:'s| is) (?:in )?(?:my |the )?clipboard|"
                     r"paste what i copied|show (?:me )?(?:what i copied|(?:my |the )?clipboard))|"
                     r"(?P<hist>(?:show |open )?(?:my |the )?clipboard(?: history| manager)?|copy history|(?:my )?copied (?:things|stuff|items))|"
                     r"(?P<clear>clear (?:my |the )?clipboard(?: history)?|empty (?:my |the )?clipboard|forget what i copied)|"
                     r"copy clip (?P<item>\d+)[?.!]*")
_DEV_Q = re.compile(r"(?P<cam>(?:is |test |check |try |show )?(?:my |the )?(?:web ?cam|camera)(?: working| work| test| check)?|"
                    r"(?:does|is) (?:my |the )?(?:web ?cam|camera) work(?:ing)?|test (?:my |the )?(?:web ?cam|camera)|"
                    r"my (?:web ?cam|camera) (?:is ?n[o']?t|isnt|doesn'?t|won'?t) (?:working|work|show(?:ing)?)(?: in the call)?)|"
                    r"(?P<mic>(?:test|check|try) (?:my |the )?(?:mic|microphone)|(?:is |does )?(?:my |the )?(?:mic|microphone)(?: working| work| test| check)?|"
                    r"can you hear me|they can'?t hear me|my (?:mic|microphone) (?:is ?n[o']?t|isnt|doesn'?t) work(?:ing)?)[?.!]*")
_LOCK_WORDS = {"lock", "lock the screen", "lock screen", "lock the computer", "lock my computer", "lock it", "lock the pc",
               "i'm stepping away", "im stepping away", "lock up", "lock it up"} | \
              {p + w + s for w in ("sign out", "log out", "sign me out", "log me out", "sign off") for p in ("", "please ")
               for s in ("", " please", " now", " please now")}
SOCK = os.path.join(config.RUN, "desk.sock")
DISPLAY_ENV = os.path.join(config.RUN, "display.env")
def _lock_tip_take():
    """True once: the 'keep the password somewhere safe' sentence is due. Taking it stores tips.lock_password_shown so it is
    not repeated on every lock (repeating it is nagging). If the settings store cannot be written, the sentence may show
    again next time; the lock still happens."""
    if config.settings.get("tips.lock_password_shown"):
        return False
    try:
        config.settings.set("tips.lock_password_shown", True)
    except Exception as e:
        sys.stderr.write(f"desk: could not save the lock tip flag: {e}\n")
    return True


def _wallpaper():
    """The wallpaper file: private data, so inside the vault when there is one."""
    return config.data("wallpaper.img")



# strings the page needs (everything else is rendered in Python)
_PAGE_KEYS = ("hint", "d_muted", "d_show_task", "d_queue_next", "d_queue_remove", "d_mode_do", "d_mode_ask", "d_mode_do_tip", "d_mode_ask_tip", "while_away", "passphrase", "wrong_passphrase", "unlocking", "locked", "welcome",
              "ask_language", "ask_name", "ask_timezone", "ask_autonomy", "ask_internet", "ask_tor",
              "ask_passphrase", "ask_passphrase_again", "passphrase_mismatch", "creating_vault", "onboard_done",
              "v_hands-off", "v_balanced", "v_hands-on", "v_yes", "v_no", "v_ask", "listening", "heard",
              "no_mic", "stopped", "error", "model_down", "loading_model", "shutting_down", "restarting",
              "allow", "d_stop", "d_history", "d_close", "d_minimize", "d_maximize", "d_window", "d_next", "d_back", "d_skip", "d_done",
              "d_unlock", "d_working", "d_apps", "d_close_app", "d_conversation", "d_you", "d_dont",
              "d_other_language", "d_open", "d_pause", "d_resume", "d_volume", "d_now_playing", "d_yes_start",
              "d_no_thanks", "d_type_language", "d_keep", "d_send", "d_clear", "d_shortcuts", "d_empty",
              "settings", "models", "tasks", "memory", "audit", "help_1", "help_2",
              "w_title", "w_text", "w_begin", "w_step", "w_recommended", "w_tz_search", "w_tz_hint", "w_net_title",
              "w_net_yes", "w_net_yes_d", "w_net_tor", "w_net_tor_d", "w_net_no", "w_net_no_d", "w_wifi_title",
              "w_wifi_none", "w_wifi_scan", "w_wifi_pass", "w_wifi_connect", "w_wifi_skip", "w_wifi_ok",
              "w_auto_off_d", "w_auto_bal_d", "w_auto_on_d", "w_pass_hint", "w_show", "w_hide", "w_done_title",
              "w_done_text", "w_finish", "d_try", "d_try_btn", "g_ex1", "g_ex2", "g_ex3", "g_ex4", "g_ex5", "g_ex6", "g_ex7", "g_ex8", "g_ex9", "g_ex10", "g_ex11", "g_ex12", "g_ex13", "g_ex14",
              "d_thinking", "d_writing", "d_listening", "d_speaking", "d_waiting", "d_morning", "d_afternoon", "d_evening", "d_idle_hint",
              "vault_exists", "passphrase_empty", "vault_made", "lock_failed", "d_host_gpu", "locked_short", "d_lock_tip", "d_reminder",
              "w_quiz_title", "w_quiz_text", "q_autonomy", "q_autonomy_0", "q_autonomy_1", "q_autonomy_2", "q_internet", "q_internet_0",
              "q_internet_1", "q_internet_2", "q_brain", "q_brain_0", "q_brain_1", "q_brain_2", "q_brain_offline", "q_capability",
              "q_capability_0", "q_capability_1", "q_capability_2", "q_guidance", "q_guidance_0", "q_guidance_1", "q_motion", "q_motion_0",
              "q_motion_1", "q_motion_2", "w_quiz_model", "w_quiz_download", "w_quiz_ram", "w_cloud_title", "w_cloud_text", "w_cloud_skip",
              "q_autonomy_0_s", "q_autonomy_1_s", "q_autonomy_2_s", "q_internet_0_s", "q_internet_1_s", "q_internet_2_s",
              "q_brain_0_s", "q_brain_1_s", "q_brain_2_s", "q_capability_0_s", "q_capability_1_s", "q_capability_2_s",
              "q_guidance_0_s", "q_guidance_1_s", "q_motion_0_s", "q_motion_1_s", "q_motion_2_s",
              "w_sys", "w_sys_mem", "w_sys_cores", "w_sys_gpu", "w_sys_gpu_basic", "w_model_need", "w_model_ready", "w_model_dl",
              "w_rec_this", "w_rec_other", "w_model_none", "w_model_tight", "w_model_slow", "w_more_models", "w_cloud_signin", "w_cloud_signin_how", "w_cloud_waiting", "w_cloud_none",
              "w_cloud_ok", "w_cloud_paste", "w_cloud_done", "w_cloud_other", "d_signin_none",
              "d_live_chip", "d_live_title", "d_chat_ph", "d_network", "d_sound", "d_power", "d_battery", "d_myapps",
              "w_cloud_check", "w_cloud_checking", "w_cloud_key", "w_cloud_model", "w_cloud_url", "w_cloud_key_where", "w_cloud_none_note",
              "w_done_choices", "v_brain_local", "v_brain_ask", "v_brain_cloud", "v_guidance_owner", "v_guidance_standard", "v_not_set_up",
              "d_brain_chip_ask", "d_online_tag", "v_yes", "v_ask", "v_no", "v_hands-off", "v_balanced", "v_hands-on",
              "d_usually", "d_left", "d_start_files", "d_shutdown_item", "models", "memory", "tasks", "d_history", "d_lists", "d_clock_title", "d_sure", "s_brain", "d_slow_turn")

FWCFG = "/sys/firmware/qemu_fw_cfg/by_name/opt/llmos"


def _fwcfg(key):
    try:
        with open(os.path.join(FWCFG, key, "raw")) as f:
            return re.sub(r"[^A-Za-z0-9/_:.+-]", "", f.read())[:80]
    except OSError:
        return ""


def _online():
    """Is there a route out (Wi-Fi/Ethernet up)?"""
    try:
        with open("/proc/net/route") as f:
            return any(ln.split()[1] == "00000000" for ln in f.readlines()[1:] if len(ln.split()) > 1)
    except OSError:
        return False


def _wifi_device():
    try:
        return next((d for d in sorted(os.listdir("/sys/class/net")) if d.startswith(("wlan", "wlp", "wlo", "wlx"))), None)
    except OSError:
        return None


def _wifi_scan():
    """Networks in range via iwd: [{ssid, secured, signal}]."""
    dev = _wifi_device()
    if not dev:
        return []
    def read():
        p = subprocess.run(["iwctl", "station", dev, "get-networks"], capture_output=True, text=True, timeout=30)
        nets, seen = [], set()
        for ln in re.sub(r"\x1b\[[0-9;]*m", "", p.stdout).splitlines():
            m = re.match(r"\s*(?:>\s*)?(.+?)\s{2,}(psk|open|8021x|wep)\s+(\**)", ln.strip(), re.I)
            if m and m.group(1).strip() not in seen and not m.group(1).startswith("-"):
                seen.add(m.group(1).strip())
                nets.append({"ssid": m.group(1).strip(), "secured": m.group(2).lower() != "open", "signal": len(m.group(3))})
        return nets
    # read the list before scanning, so a stale (cached) list is not taken as the new result
    try:
        before = read()
    except Exception:
        before = None
    subprocess.run(["iwctl", "station", dev, "scan"], capture_output=True, timeout=30)
    # poll every 0.25 s until networks are listed and the list has stopped changing (old fixed wait: 3 s)
    return waits.scan_settled(read, limit=3.0, step=0.25, default=[], before=before)


def _wifi_connect(ssid, password):
    dev = _wifi_device()
    if not dev:
        return False, "no Wi-Fi adapter"
    cmd = ["iwctl"] + (["--passphrase", password] if password else []) + ["station", dev, "connect", ssid]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        return False, (p.stderr or p.stdout).strip()[:200] or "could not connect"
    if waits.wait_until(_online, total=15.0, step=0.25):   # 60 checks, 0.25 s apart
        return True, ""
    return True, "connected, waiting for an address"


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb)


def _best_text(hexcol):
    """#111111 or #ffffff, whichever has the higher WCAG contrast ratio against hexcol (text on an accent or danger fill)."""
    def lum(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    h = hexcol.lstrip("#")
    l = 0.2126 * lum(int(h[0:2], 16)) + 0.7152 * lum(int(h[2:4], 16)) + 0.0722 * lum(int(h[4:6], 16))

    def ratio(other):
        hi, lo = max(l, other), min(l, other)
        return (hi + 0.05) / (lo + 0.05)
    return "#111111" if ratio(lum(0x11)) > ratio(1.0) else "#ffffff"


def _software_gpu():
    """True when there is no hardware 3D (a VM): render everything on the CPU."""
    try:
        drv = os.path.basename(os.readlink("/sys/class/drm/card0/device/driver"))
    except OSError:
        try:
            drv = os.path.basename(os.readlink("/sys/class/drm/card1/device/driver"))
        except OSError:
            return True
    return drv in ("virtio_gpu", "virtio-pci", "bochs-drm", "cirrus", "vmwgfx", "simple-framebuffer", "")


def _display_scale(monitor):
    """How much to enlarge everything on this screen, the way PCs pick their default: from its pixels per inch,
    100% up to 120, 125% up to 144, 150% up to 192, then 200%. 100% when the screen does not report a believable
    size (virtual machines, many projectors and TVs). Sizes in the compositor's pixels, so a compositor that already
    scales is not scaled twice."""
    try:
        mm, px = monitor.get_width_mm(), monitor.get_geometry().width
    except Exception:
        return 1.0
    if not (150 <= mm <= 1000) or px <= 0:
        return 1.0
    ppi = px / (mm / 25.4)
    return 2.0 if ppi >= 192 else 1.5 if ppi >= 144 else 1.25 if ppi >= 120 else 1.0


_CHROMIUM_APPS = ("com.visualstudio.code", "com.discordapp.Discord", "com.slack.Slack", "md.obsidian.Obsidian", "org.signal.Signal",
                  "com.github.IsmaelMartinez.teams_for_linux", "com.spotify.Client", "com.brave.Browser", "com.rtosta.zapzap")


def _root_ok(argv):
    """Everything here runs as the one owner account, root; Chromium-based programs refuse that unless told
    (--no-sandbox), and VS Code also wants its own data folder named."""
    base = os.path.basename(argv[0]) if argv else ""
    if base in ("chromium", "chromium-browser") and "--no-sandbox" not in argv:
        return argv + ["--no-sandbox"]
    if base == "flatpak" and "run" in argv:
        app = next((a for a in argv[argv.index("run") + 1:] if not a.startswith("-")), "")
        if app in _CHROMIUM_APPS and "--no-sandbox" not in argv:
            extra = ["--no-sandbox"] + (["--user-data-dir=" + os.path.join(config.home(), ".config", "Code")] if app == "com.visualstudio.code" else [])
            i = argv.index(app) + 1
            return argv[:i] + extra + argv[i:]
    return argv


def _wifi_radio_on(v):
    """'wifi on' -> radio on (unblock); 'wifi off' -> radio off (block)."""
    return v == "on"


def _airplane_radio_on(v):
    """Airplane mode on -> every radio off (block), so the radio's on flag is False; airplane off -> on flag True."""
    return v != "on"


def _airplane():
    """Every radio (Wi-Fi, Bluetooth) switched off."""
    try:
        p = subprocess.run(["rfkill", "-n", "-o", "SOFT"], capture_output=True, text=True, timeout=5)
        states = p.stdout.split()
        return bool(states) and all(x == "blocked" for x in states)
    except (OSError, subprocess.SubprocessError):
        return False


def _battery():
    """{"pct", "charging"} for a laptop's battery, None on a desktop."""
    base = "/sys/class/power_supply"
    try:
        for n in sorted(os.listdir(base)):
            p = os.path.join(base, n)
            try:
                with open(os.path.join(p, "type")) as f:
                    if f.read().strip() != "Battery":
                        continue
                with open(os.path.join(p, "capacity")) as f:
                    pct = int(f.read().strip())
                with open(os.path.join(p, "status")) as f:
                    st = f.read().strip()
                return {"pct": pct, "charging": st in ("Charging", "Full")}
            except (OSError, ValueError):
                continue
    except OSError:
        pass
    return None


def _wifi_now():
    """The Wi-Fi network this computer is on, or ''."""
    dev = _wifi_device()
    if not dev:
        return ""
    try:
        p = subprocess.run(["iwctl", "station", dev, "show"], capture_output=True, text=True, timeout=10)
        m = re.search(r"Connected network\s+(.+)", re.sub(r"\x1b\[[0-9;]*m", "", p.stdout))
        return m.group(1).strip() if m else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _live():
    """Running from the USB stick / ISO (a RAM overlay): nothing is kept after the computer turns off."""
    try:
        with open("/etc/llmos-release") as f:
            return "MEDIUM=live" in f.read()
    except OSError:
        return False


def _system_check():
    """What this computer has, for the set-up's recommendations: memory, processor cores, graphics."""
    cpu = ""
    try:
        with open("/proc/cpuinfo") as f:
            for ln in f:
                if ln.startswith("model name"):
                    cpu = ln.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    vendor = ""
    for card in ("card0", "card1"):
        try:
            with open(f"/sys/class/drm/{card}/device/vendor") as f:
                vendor = {"0x8086": "Intel", "0x1002": "AMD", "0x10de": "NVIDIA"}.get(f.read().strip(), "")
        except OSError:
            continue
        if vendor:
            break
    accel = not _software_gpu()
    ram = models.ram_gb()
    import math
    return {"ram_gb": math.ceil(ram) if ram else 0, "ram_real": round(ram, 1), "cores": os.cpu_count() or 0,
            "cpu": cpu, "gpu": vendor if accel else "", "accel": accel}


def _model_tiers(allow_download):
    """The on-device models behind Fast / Balanced / Most capable on this computer: those that fit its memory
    (1 GB left for the system); offline, only those already here. Fast is the smallest (or an installed quick one in the
    same size band), Balanced the largest of the other quick ones, Most capable the largest. A tier that would repeat a model is dropped."""
    ram = models.ram_gb()
    inst = {m["id"] for m in models.installed()}
    fits = [m for m in models.catalog() if m["ram_gb"] <= ram - 1 and (allow_download or m["id"] in inst)]
    fits.sort(key=lambda m: round(m["size"] / 1e9, 1))
    if not fits:
        # too little memory for any of them: the smallest one is still offered, one stop, labelled as running from disk (slow)
        small = sorted((m for m in models.catalog() if allow_download or m["id"] in inst), key=lambda m: m["size"])
        return [{"tier": "fast", "id": m["id"], "name": m["name"], "need_gb": m["ram_gb"], "size_gb": round(m["size"] / 1e9, 1),
                 "installed": m["id"] in inst, "bigger": True} for m in small[:1]]
    quick = [m for m in fits if m.get("speed") in ("fast", "fastest")]
    # Fast is the smallest; but an installed quick model no bigger than 1.5x the smallest is the same band, and it is
    # ready at once, so it is Fast instead (a bigger installed model keeps its place in the order)
    fast = next((m for m in quick if m["id"] in inst and m["size"] <= fits[0]["size"] * 1.5), fits[0])
    rest = [m for m in fits if m is not fast]
    rest_quick = [m for m in quick if m is not fast]
    out, seen = [], set()
    for tier, m in (("fast", fast), ("balanced", (rest_quick or rest or [fast])[-1]), ("capable", fits[-1])):
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        out.append({"tier": tier, "id": m["id"], "name": m["name"], "need_gb": m["ram_gb"],
                    "size_gb": round(m["size"] / 1e9, 1), "installed": m["id"] in inst})
    return out


def _model_all(allow_download):
    """Every on-device model the owner can pick (the same installed / downloadable rule as the tiers). Those that fit the
    memory come first, then the ones that run from disk ("bigger", slow); each group by size. Nothing is blocked by memory."""
    ram = models.ram_gb()
    inst = {m["id"] for m in models.installed()}
    allowed = sorted((m for m in models.catalog() if allow_download or m["id"] in inst),
                     key=lambda m: (m["ram_gb"] > ram - 1, m["size"]))
    return [{"id": m["id"], "name": m["name"], "need_gb": m["ram_gb"], "size_gb": round(m["size"] / 1e9, 1),
             "installed": m["id"] in inst, "bigger": m["ram_gb"] > ram - 1} for m in allowed]


def _recommend(sysinfo, tiers):
    """The choices this computer's specs suggest: models run on the processor, so Balanced only with 8+ cores and
    16 GB; the most capable is slow on a processor and is never the default. Lively motion only with hardware
    graphics (software rendering stutters)."""
    have = {t["tier"] for t in tiers}
    cap = "balanced" if sysinfo["cores"] >= 8 and sysinfo["ram_real"] >= 15 and "balanced" in have else "fast"
    return {"capability": cap if cap in have else (tiers[0]["tier"] if tiers else ""), "motion": 2 if sysinfo["accel"] else 1}


def _nothing_open_reply(text):
    """Reply for 'click X' when nothing is open. Names X in the owner's own case; empty X keeps the old sentence."""
    m = re.fullmatch(r"(?:please )?(?:click|tap|press)(?: on)?(?: the)? (?P<target>.+)", text.strip().rstrip(".!"), re.IGNORECASE)
    target = re.sub(r"^(?:the|on)(?:\s+|$)", "",m.group("target").strip(), flags=re.IGNORECASE).strip() if m else ""
    return f"Nothing is open to click {target} in." if target else "Nothing is open to click on."


# --------------------------------------------------------------- ctx

class DeskCtx:
    """Bridges the agent to the desk: streaming, tool feedback, confirmations,
    windows, media, apps."""
    headless = False

    def __init__(self, desk):
        self.d = desk
        self.after_turn = None
        self.current_request = ""
        self.cancel = threading.Event()
        self._net_ok = set()

    def new_stream(self):
        self._watch_last, self._watch_t = None, 0.0
        return object()

    def watch(self, kind, *data):
        """What the model is doing right now, shown under the request: how far it has read it, its thinking, and the
        action it is writing (llm.chat's watch). Lines of one kind update in place; a few per second at most."""
        now = time.time()
        if kind == "reading":
            done, total = data
            if done < total and now - getattr(self, "_watch_t", 0) < 0.4:
                return
            self._watch_t = now
            self.d.emit({"t": "progress", "label": T("d_reading_request"), "done": done, "total": total})
            return
        if kind == "thinking":
            self._thought = (getattr(self, "_thought", "") + data[0])[-400:]
            text = T("d_thinking_now") + " " + " ".join(self._thought.split())[-160:]
        elif kind == "tool":
            name, raw = data
            try:
                args = json.loads(raw)
                text = T("d_about_to") + " " + self.d.describe_tool(name, args)
            except (ValueError, TypeError, AttributeError):
                text = T("d_about_to") + " " + name.replace("_", " ") + " …"
        else:
            return
        if kind == getattr(self, "_watch_last", None) and now - getattr(self, "_watch_t", 0) < 0.3:
            return
        self.d.emit({"t": "activity", "text": text, "replace": kind == getattr(self, "_watch_last", None),
                     "chat": getattr(self, "chat_id", "main")})
        self._watch_last, self._watch_t = kind, now

    def on_text(self, stream, text):
        if self.cancel.is_set():
            raise agent.Cancelled()
        if not text:
            return
        self.d.emit({"t": "reply.delta", "text": text, "chat": getattr(self, "chat_id", "main")})

    def end_stream(self, stream):
        pass

    def status(self, text):
        # a progress line from inside a tool updates that tool's activity line in place; other notes append
        self.d.emit({"t": "activity", "text": str(text), "replace": bool(getattr(self, "_tool_open", False)), "chat": getattr(self, "chat_id", "main")})

    def begin_tool(self, tool, args, risk):
        self._watch_last = None
        self._tool_open = True
        self._cur_tool = (getattr(tool, "name", ""), dict(args) if isinstance(args, dict) else {}, risk)
        self.d.emit({"t": "activity", "text": self.d.describe_tool(tool, args), "chat": getattr(self, "chat_id", "main")})

    def end_tool(self, tool, result):
        self._tool_open = False
        cur, self._cur_tool = getattr(self, "_cur_tool", None), None
        # something changed: the windows that show it (files, models, inbox, sound...) show it at once
        if cur and cur[2] in (tools.CHANGE, tools.DESTRUCTIVE, tools.SECURITY) and not str(result).startswith("error"):
            self.d.refresh_windows()

    def progress(self, phase, done, total):
        self.d.emit({"t": "progress", "label": {"download": "downloading", "verify": "verifying"}.get(phase, phase),
                     "done": int(done), "total": int(total)})

    def background(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def confirm_network(self, name, args):
        if name in self._net_ok:
            return True
        host = str(args.get("url", "") or args.get("query", ""))[:80]
        label = {"read_webpage": "open a web page", "web_search": "search the web", "find_by_meaning": "get the search model",
                 "check_site": "check a website", "add_model": "download a model", "download_model": "download a model"}.get(name)
        if label is None:
            label = "use your mail" if name.startswith("mail_") else name.replace("_", " ")
        text = label[:1].upper() + label[1:] + (f" — {host}" if host else "")
        ok = self.d.ask({"title": T("s_internet", area="settings"), "text": text, "danger": False}, consent=True)
        if ok:
            self._net_ok.add(name)
        return ok

    def confirm_action(self, tool, args, risk):
        a = args if isinstance(args, dict) else {}
        if tool.name == "change_setting" and a.get("setting") == "autonomy" and "off" in str(a.get("value", "")).lower():
            # the one question full trust asks: this is the owner's consent, given once, for everything after it
            return self.d.ask({"title": T("d_full_trust_title"), "text": T("d_full_trust_text"), "danger": True,
                               "yes": T("d_full_trust_yes"), "no": T("d_full_trust_no")}, consent=True)
        # (the agent asks only when a setting the owner chose says to: their autonomy level, or the check on
        # instructions from web pages, files and emails)
        text = self.d.describe_args(tool, args)
        if getattr(self, "confirm_tainted", False):      # agent.py sets this on this same DeskCtx for the web-page check
            text = text + "\n\n" + T("d_guard_tainted")
        return self.d.ask({"title": self.d.describe_tool(tool, args, confirm=True),
                           "text": text, "danger": risk in ("destructive", "security"),
                           "mono": tool.name in ("run_command", "install_app", "write_file")}, consent=True)

    def confirm_online(self, text, reason):
        """'ask' brain mode: one dialog before a request leaves this computer, saying what goes."""
        label = llm.cloud_label()
        why = T("d_online_failed") if reason == "failed" else T("d_online_big")
        return self.d.ask({"title": T("d_online_title", model=label), "text": why + "\n\n" + T("d_online_shares"),
                           "danger": False, "yes": T("d_online_yes", model=label), "no": T("d_online_no")}, consent=True)

    def brain(self, online, label):
        self.d.emit({"t": "reply.brain", "online": bool(online), "label": label})

    def expect(self, seconds, step):
        self.d.emit({"t": "reply.eta", "seconds": float(seconds), "step": int(step)})

    @staticmethod
    def _provider(name):
        n = str(name or "").strip().lower()
        if n in ("claude", "anthropic"):
            return "anthropic"
        if n in ("chatgpt", "openai", "gpt"):
            return "chatgpt"
        return n if n in llm.CLOUD_PROVIDERS else ""

    def show_app(self, app):
        self.d.show_app(app)

    def show_apps(self):
        self.d.show_apps()

    def reload_apps(self):
        """Open app windows show their new look (their page is loaded again; their saved state stays)."""
        for wid, spec in list(self.d.windows.items()):
            if spec.get("kind") == "app":
                spec["src"] = spec["src"].split("?")[0] + "?v=" + str(int(time.time()))
                self.d.emit({"t": "window", "id": wid, "spec": spec})

    def close_window(self, wid):
        self.d.close_window(wid)

    def open_mail_setup(self):
        self.d.mail_form()

    def app_press(self, text):
        """An open app's control pressed by its label: {"ok", "page"} or None when no app is open."""
        return self.d.app_call("press", text)

    def app_read(self):
        """An open app's page: {"text", "controls"} or None when no app is open."""
        return self.d.app_call("read")

    def signin(self, provider=None):
        """"sign in to Claude / ChatGPT": the service's key page in a window; the copied key comes in by itself."""
        pid = self._provider(provider) or "anthropic"
        if not (llm.CLOUD_PROVIDERS.get(pid) or {}).get("signin"):
            return self.setup_cloud(pid)
        self.d.GLib.idle_add(self.d._signin_open, pid)
        return (f"a sign-in window for {llm.CLOUD_PROVIDERS[pid]['name']} is open: you sign in, create a key and "
                "presses Copy; the window then closes by itself and the key is checked automatically. Say one sentence at most.")

    def setup_cloud(self, provider=None):
        """"set up the online model": the connect panel (sign in to a service, nothing to type); for another
        service ("connect another online service") a form whose submit posts straight to the OS (the key never
        passes through a model)."""
        if str(provider or "").strip().lower() not in ("other", "other service", "openai-compatible", "openai compatible"):
            self.d.open_connect_panel()
            return "the connect panel is on screen: you sign in to a service there. Say one sentence at most."
        import secrets
        self.d.cloud_nonce = secrets.token_hex(12)
        prov = llm.CLOUD_PROVIDERS
        pid = "openai"
        self.d.open_window({"id": "cloud-form", "replace": True, "title": T("s_online_model", area="settings"), "size": "s", "slot": "cascade", "blocks": [
            {"type": "text", "text": T("d_cloud_intro")},
            {"type": "form", "fields": [{"name": "provider", "label": T("d_cloud_provider"), "options": [p["name"] for p in prov.values()], "value": prov[pid]["name"]},
                                        {"name": "model", "label": T("d_cloud_model"), "value": prov[pid]["models"][0]["id"] if prov[pid]["models"] else ""},
                                        {"name": "url", "label": T("d_cloud_url"), "placeholder": T("d_cloud_url_hint")},
                                        {"name": "key", "label": T("d_cloud_key"), "kind": "password", "placeholder": prov[pid]["key_hint"]},
                                        {"name": "nonce", "kind": "hidden", "value": self.d.cloud_nonce}],
             "submit": {"label": T("d_cloud_save"), "post": "cloud.setup"}},
            {"type": "text", "text": T("d_cloud_hint"), "dim": True}]})
        return "an online-model form is on screen; you fill it in there. Say one sentence at most."

    def setup_connector(self):
        """"add a connector": a form whose submit posts straight to the OS (nothing runs until it is probed)."""
        import secrets
        self.d.connector_nonce = secrets.token_hex(12)
        self.d.open_window({"id": "connector-form", "replace": True, "title": T("d_add_connector", area="settings"), "size": "s", "slot": "cascade", "blocks": [
            {"type": "text", "text": T("d_connector_form_intro", area="settings")},
            {"type": "form", "fields": [{"name": "name", "label": T("d_conn_name", area="settings"), "placeholder": "weather"},
                                        {"name": "transport", "label": T("d_conn_transport", area="settings"), "options": ["stdio", "http"], "value": "stdio"},
                                        {"name": "command", "label": T("d_conn_command", area="settings"), "placeholder": "uvx mcp-server-weather"},
                                        {"name": "url", "label": T("d_conn_url", area="settings"), "placeholder": "https://…/mcp"},
                                        {"name": "nonce", "kind": "hidden", "value": self.d.connector_nonce}],
             "submit": {"label": T("d_conn_add_btn", area="settings"), "post": "connector.add"}},
            {"type": "text", "text": T("d_connector_form_hint", area="settings"), "dim": True}]})
        return "a connector form is on screen; you fill it in there. Say one sentence at most."

    def edit_conduct(self):
        """"pop the hood": the owner edits the conduct section of the system prompt. The text is theirs — it
        comes from their form submission (nonced) and the OS never writes it on its own."""
        import secrets
        from . import agent
        self.d.conduct_nonce = secrets.token_hex(12)
        self.d.open_window({"id": "conduct-form", "replace": True, "title": T("d_conduct_title", area="settings"), "size": "m", "slot": "cascade", "blocks": [
            {"type": "text", "text": T("d_conduct_intro", area="settings")},
            {"type": "form", "fields": [{"name": "text", "label": T("d_conduct_label", area="settings"), "kind": "textarea", "value": agent.conduct_text()},
                                        {"name": "nonce", "kind": "hidden", "value": self.d.conduct_nonce}],
             "submit": {"label": T("d_conduct_save", area="settings"), "post": "conduct.save"}},
            {"type": "text", "text": T("d_conduct_hint", area="settings"), "dim": True}]})
        return "the conduct editor is on screen; you edit it there. Say one sentence at most."

    def interactive(self, cmd):
        return self.d.run_in_terminal(cmd)

    def redraw(self):
        self.d.apply_theme()
        self.d.push_status()

    def start_idle(self):
        self.d.start_idle()

    def start_night_light(self):
        self.d.start_night_light()

    def show_panel(self, panel):
        self.d.open_panel(panel)

    def show_box(self, title, rows):
        self.d.open_window({"title": title, "blocks": [{"type": "text", "text": "\n".join(rows)}]})

    is_desk = True

    def setup_vault(self):
        """"set up a passphrase" after first boot: a form whose submit posts straight to the OS."""
        import secrets
        if config.settings.get("vault"):
            self.d.vault_nonce = secrets.token_hex(12)
            self.d.open_window({"id": "vault-form", "replace": True, "title": "Change passphrase", "size": "s", "slot": "cascade", "blocks": [
                {"type": "text", "text": "Type the passphrase you use now, then the new one twice."},
                {"type": "form", "fields": [{"name": "p0", "label": "Passphrase now", "kind": "password"},
                                            {"name": "p1", "label": "New passphrase", "kind": "password"},
                                            {"name": "p2", "label": T("ask_passphrase_again"), "kind": "password"},
                                            {"name": "nonce", "kind": "hidden", "value": self.d.vault_nonce}],
                 "submit": {"label": "Change it", "post": "vault.change"}}]})
            return ("nothing is changed yet: a window is open where you type the passphrase they use now and the new one. "
                    "Tell them that in one sentence; do not say it is changed.")
        self.d.vault_nonce = secrets.token_hex(12)
        self.d.open_window({"id": "vault-form", "replace": True, "title": T("passphrase"), "size": "s", "slot": "cascade", "blocks": [
            {"type": "text", "text": T("ask_passphrase")},
            {"type": "form", "fields": [{"name": "p1", "label": T("passphrase"), "kind": "password"},
                                        {"name": "p2", "label": T("ask_passphrase_again"), "kind": "password"},
                                        {"name": "nonce", "kind": "hidden", "value": self.d.vault_nonce}],
             "submit": {"label": T("d_set_passphrase"), "post": "vault.create"}},
            {"type": "text", "text": T("w_pass_hint"), "dim": True}]})
        return ("nothing is set yet: a window is open where you type a new passphrase twice. "
                "Tell them that in one sentence; do not say it is set.")

    def show_ui(self, spec):
        cur = getattr(self, "_cur_tool", None)
        if cur and cur[2] in (tools.READ, tools.SAFE) and isinstance(spec, dict) and spec.get("id") and cur[0]:
            self.d.note_window_source(spec["id"], cur[0], cur[1])    # rebuilt by re-running this tool when things change
        return self.d.open_window(spec)

    def close_ui(self, wid):
        if wid in self.d.windows:
            self.d.close_window(wid)

    def display(self, text):
        pass   # terminal art: the desk shows real images instead (show_image passes a spec)

    def media(self, action, **kw):
        return self.d.media_action(action, **kw)

    def launch(self, argv, name=""):
        return self.d.launch_app(argv, name)

    def add_source(self, url, title):
        """Research is visible: every page read for the current request is
        listed in a small Sources window."""
        self.d.sources.append({"url": url, "title": title or url})
        self.d.open_window({"id": "sources", "replace": True, "title": "Sources", "size": "s",
                            "blocks": [{"type": "sources", "items": self.d.sources[-8:]}]})


# --------------------------------------------------------------- desk

class Desk:
    def __init__(self):
        self.ctx = DeskCtx(self)
        self.history = []
        self.windows = {}            # id -> spec
        self.win_seq = 0
        self.screen = "boot"
        self.dialogs = {}            # id -> [Event, value]
        self.dialog_seq = 0
        self.requests = queue.Queue()
        self._unlocking = threading.Lock()
        self.busy = False
        self.listening = False
        self.apps = {}               # pid -> {name, popen}
        self.unlock_failures = 0
        self.last_reply = ""
        self.last_activity = []
        self.sources = []
        self.turn_done = threading.Event()
        self.webview = None
        self.app = None
        self.ready = False
        self._pending = []           # messages emitted before the page was ready
        self._rect_wait = {}         # test shell: "rect <id> <selector>" waiting for the page's answer
        self._req_pending = 0        # requests queued or running (counted from say() until the worker finishes them)
        self._req_done = 0           # requests the worker has finished (a counter: wait "N after M" tells a finished one from none)
        self._pending_lock = threading.Lock()
        self._waiting, self._dropped = [], set()   # requests queued behind the one in progress (shown on the desk)

    # ---- GTK / WebKit

    def run(self):
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        gi.require_version("WebKit", "6.0")
        from gi.repository import Gtk, Gdk, GLib, WebKit
        self.GLib, self.WebKit, self.Gtk, self.Gdk = GLib, WebKit, Gtk, Gdk
        system.apply_timezone_env()
        ui.reload_theme()

        def activate(app):
            os.chdir("/")   # children (WebKit, programs the owner opens) must not sit inside the vault
            win = Gtk.ApplicationWindow(application=app)
            self.gtkwin = win
            win.connect("close-request", lambda *a: True)   # the desk is the screen: it cannot be closed
            win.set_title("LLM OS")
            win.set_decorated(False)
            settings = WebKit.Settings(enable_developer_extras=False, enable_javascript=True, enable_media=True,
                                       enable_webgl=False, allow_file_access_from_file_urls=True,
                                       allow_universal_access_from_file_urls=True, enable_smooth_scrolling=True,
                                       enable_page_cache=False, default_font_family="Inter",
                                       monospace_font_family="JetBrains Mono", default_font_size=16)
            if _software_gpu():
                try:
                    settings.set_hardware_acceleration_policy(WebKit.HardwareAccelerationPolicy.NEVER)
                except Exception:
                    pass
            ucm = WebKit.UserContentManager()
            ucm.connect("script-message-received::llmos", self._on_js)
            ucm.register_script_message_handler("llmos", None)
            # an ephemeral session: no cache, cookies or storage on disk -- the page is local, and an
            # open cache file inside the home folder would keep the vault from closing at lock time
            kw = {}
            try:
                kw["network_session"] = WebKit.NetworkSession.new_ephemeral()
            except Exception as e:
                sys.stderr.write(f"desk: no ephemeral session ({e}); using the default one\n")
            self.webview = WebKit.WebView(settings=settings, user_content_manager=ucm, **kw)
            self.webview.connect("context-menu", lambda *a: True)
            self.webview.connect("web-process-terminated", self._page_ended)
            self.webview.connect("decide-policy", self._decide_policy)
            th = ui.Theme()
            bg = th.bg or (11, 13, 20)
            self.webview.set_background_color(Gdk.RGBA(red=bg[0] / 255, green=bg[1] / 255, blue=bg[2] / 255, alpha=1))
            self._apply_proxy()
            self.webview.load_uri("file://" + PAGE)
            win.set_child(self.webview)
            win.fullscreen()
            win.present()
            # asked again once the window is on screen: a desk started again by an update (outside the compositor's
            # own start-up) had its first request ignored and stayed a 200x200 window in the corner
            for ms in (500, 1500, 4000):
                GLib.timeout_add(ms, lambda w=win: (w.fullscreen(), False)[1])
            GLib.timeout_add(400, self._apply_zoom)
            try:
                Gdk.Display.get_default().get_monitors().connect("items-changed", lambda *a: GLib.timeout_add(600, self._apply_zoom))
            except Exception:
                pass
            self._write_display_env()
            self._start_sound()
            subprocess.run(["pkill", "-f", "wl-paste --type text --watch"], capture_output=True)   # one watcher, even after a restart
            GLib.timeout_add(2000, lambda: (clip.start_watch(), False)[1])
            # a focus period running when the desk restarted carries on (or ends, if its time is up)
            GLib.timeout_add(2500, lambda: (everyday.focus_resume(self), False)[1])
            GLib.timeout_add(2500, lambda: (self._start_notifications(), False)[1])
            GLib.timeout_add_seconds(20, lambda: (threading.Thread(target=lambda: system.sync_time(automatic=True), daemon=True).start(), False)[1])
            GLib.timeout_add(1500, lambda: (self.apply_input(), False)[1])
            threading.Thread(target=self._control_socket, daemon=True).start()
            GLib.timeout_add_seconds(3, self._poll_drives)
            threading.Thread(target=self._worker, daemon=True).start()
            GLib.timeout_add_seconds(20, self._poll_away)
            GLib.timeout_add_seconds(30, self._poll_autolock)
            GLib.timeout_add_seconds(5, self._poll_power)
            GLib.timeout_add(3000, lambda: (self.start_idle(), False)[1])

        self.app = Gtk.Application(application_id="org.llmos.desk")
        self.app.connect("activate", activate)
        os.makedirs(config.RUN, exist_ok=True)
        with open(os.path.join(config.RUN, "desk.pid"), "w") as f:
            f.write(str(os.getpid()))
        try:
            self.app.run(None)
        finally:
            self._cleanup()

    def _app_export(self, name, data):
        """An app hands over a file (a drawing): saved in ~/Pictures under a name that is not taken."""
        import base64
        m = re.match(r"data:image/(png|jpeg);base64,(.+)$", data, re.S)
        if not m or len(data) > apps.MAX_STATE:
            return
        d = os.path.join(config.home(), "Pictures")
        try:
            config.guard_write(d)
            os.makedirs(d, exist_ok=True)
            stem = re.sub(r"[^\w.-]+", "-", os.path.splitext(os.path.basename(name))[0])[:40] or "picture"
            ext = "jpg" if m.group(1) == "jpeg" else "png"
            path, n = os.path.join(d, f"{stem}.{ext}"), 1
            while os.path.exists(path):
                n += 1
                path = os.path.join(d, f"{stem}-{n}.{ext}")
            with open(path, "wb") as f:
                f.write(base64.b64decode(m.group(2)))
            self.emit({"t": "toast", "text": T("d_saved_to", path=path.replace(config.home(), "~"))})
        except (OSError, ValueError) as e:
            self.emit({"t": "toast", "text": agent._plain_error(str(e))})

    def _decide_policy(self, view, decision, kind):
        """The desk and the apps in it are local pages: nothing in them may navigate to the web (an app sending what
        it holds to a server by loading an address). Web pages open in the browser, never inside the desk."""
        try:
            from gi.repository import WebKit
            if kind in (WebKit.PolicyDecisionType.NAVIGATION_ACTION, WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):
                uri = decision.get_navigation_action().get_request().get_uri() or ""
                if not uri.startswith(("file://", "about:", "data:", "blob:")):
                    decision.ignore()
                    return True
        except Exception as e:
            sys.stderr.write(f"desk: navigation check failed: {e}\n")
        return False

    def _page_ended(self, view, reason):
        """The page's process ended (out of memory, a crash): the screen would stay frozen on its last picture, so
        the page is loaded again; on "ready" it gets the current screen and the open windows back."""
        sys.stderr.write(f"desk: the page's process ended ({reason}); loading it again\n")
        self.ready, self._reloaded = False, True
        self.GLib.timeout_add(300, lambda: (view.load_uri("file://" + PAGE), False)[1])

    def _start_notifications(self):
        """Programs' own notifications (a download finished in the browser, a message in a call): shown in the
        corner in the desk's colours by mako, the usual notification daemon for this kind of desktop."""
        if not shutil.which("mako"):
            return
        a = config.settings.get("appearance", {}) or {}
        bg, fg, acc = (a.get("background") or "#14161f"), (a.get("color") or "#e8e9ef"), (a.get("accent") or "#7a52ff")
        d = os.path.join(config.home(), ".config", "mako")
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "config"), "w") as f:
                f.write(f"font=Inter 12\nbackground-color={bg}ee\ntext-color={fg}\nborder-color={acc}\nborder-size=2\n"
                        f"border-radius=12\npadding=12\nmargin=58,16,16,16\nwidth=360\ndefault-timeout=7000\nanchor=top-right\n"
                        f"max-visible=3\nlayer=overlay\n\n[mode=do-not-disturb]\ninvisible=1\n")
            subprocess.run(["pkill", "-x", "mako"], capture_output=True)
            env = dict(os.environ, **(media.desk_env() or {}))
            subprocess.Popen(["mako", "-c", os.path.join(d, "config")], env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            if config.settings.get("do_not_disturb"):
                self.GLib.timeout_add(1000, lambda: (subprocess.run(["makoctl", "mode", "-s", "do-not-disturb"], env=env, capture_output=True), False)[1])
        except OSError:
            pass
        self.start_night_light()

    def start_night_light(self):
        """Warmer colours in the evening (settings: night_light on/off; 19:00 to 07:00 unless set)."""
        subprocess.run(["pkill", "-x", "wlsunset"], capture_output=True)
        if not config.settings.get("night_light") or not shutil.which("wlsunset"):
            return
        try:
            subprocess.Popen(["wlsunset", "-t", "3800", "-T", "6500", "-S", str(config.settings.get("night_light_end") or "07:00"),
                              "-s", str(config.settings.get("night_light_start") or "19:00")],
                             env=dict(os.environ, **(media.desk_env() or {})), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            pass

    def _start_sound(self):
        """PipeWire for this session: programs (the browser, calls, Bluetooth headphones) need a sound server; the
        desk's own sounds still work through ALSA without it."""
        if not shutil.which("pipewire"):
            return
        env = dict(os.environ)
        for prog in ("pipewire", "wireplumber", "pipewire-pulse"):
            if shutil.which(prog) and subprocess.run(["pgrep", "-x", prog], capture_output=True).returncode != 0:
                try:
                    subprocess.Popen([prog], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
                    time.sleep(0.3)
                except OSError as e:
                    sys.stderr.write(f"desk: {prog} did not start: {e}\n")

    def _poll_drives(self):
        """A USB stick plugged in: say so, with a button to open it (and to eject it later)."""
        try:
            now = {d["path"]: d for d in syspanels.removable()}
        except Exception:
            return True
        seen = getattr(self, "_drives_seen", None)
        self._drives_seen = set(now)
        if seen is None or self.screen != "desk":
            return True
        for path in set(now) - seen:
            d = now[path]
            self.emit({"t": "toast", "text": T("d_drive_in", name=d["label"], size=d["size"]), "long": True})
            self.open_window(syspanels.drives())
        return True

    def _cleanup(self):
        for p in list(self.apps.values()):
            try:
                p["popen"].terminate()
            except OSError:
                pass
        try:
            os.unlink(DISPLAY_ENV)
        except OSError:
            pass

    def _write_display_env(self):
        """Other sessions (the text console) launch graphical programs into
        this compositor instead of starting their own."""
        os.makedirs(config.RUN, exist_ok=True)
        wl = os.environ.get("WAYLAND_DISPLAY", "")
        with open(DISPLAY_ENV, "w") as f:
            f.write(f"WAYLAND_DISPLAY={wl}\nXDG_RUNTIME_DIR={os.environ.get('XDG_RUNTIME_DIR', config.RUN)}\n")

    def _apply_proxy(self):
        """Web content inside the desk follows the Tor setting."""
        try:
            WebKit = self.WebKit
            sess = self.webview.get_network_session()
            if config.settings.get("tor"):
                ps = WebKit.NetworkProxySettings.new("socks5://127.0.0.1:9050", None)
                sess.set_proxy_settings(WebKit.NetworkProxyMode.CUSTOM, ps)
            else:
                sess.set_proxy_settings(WebKit.NetworkProxyMode.DEFAULT, None)
        except Exception:
            pass

    # ---- connecting an online model without typing a key

    def _signin_open(self, pid):
        """A window on the service's own key page, in a private session (nothing of the sign-in is kept). The owner
        signs in, creates a key and presses Copy; when the window closes, the key is taken from the clipboard and
        checked (_signin_closed). Main thread."""
        Gtk, WebKit = self.Gtk, self.WebKit
        prov = llm.CLOUD_PROVIDERS.get(pid) or {}
        if not prov.get("signin") or getattr(self, "_signin_win", None) is not None:
            return False
        win = Gtk.Window(title=T("w_cloud_signin", name=prov["name"]))
        win.set_default_size(1100, 800)
        win.maximize()   # a whole web site: as big as the screen allows, whatever the screen
        if getattr(self, "gtkwin", None) is not None:
            win.set_transient_for(self.gtkwin)
            win.set_modal(True)
        kw = {}
        try:
            kw["network_session"] = WebKit.NetworkSession.new_ephemeral()
        except Exception:
            pass
        view = WebKit.WebView(**kw)
        try:
            view.set_zoom_level(self._zoom())
        except Exception:
            pass

        def popup(parent, _action):
            # "Continue with Google / Apple / Microsoft" may open its own small window and close it when done;
            # without this the button would do nothing
            child = WebKit.WebView(related_view=parent)
            pw = Gtk.Window(title=win.get_title())
            pw.set_default_size(620, 760)
            pw.set_transient_for(win)
            pw.set_modal(True)
            pw.set_destroy_with_parent(True)
            pw.set_child(child)
            try:
                child.set_zoom_level(self._zoom())
            except Exception:
                pass
            child.connect("ready-to-show", lambda *_: pw.present())
            child.connect("close", lambda *_: pw.destroy())
            return child
        view.connect("create", popup)
        bar = Gtk.HeaderBar()
        done = Gtk.Button(label=T("w_cloud_done"))
        done.add_css_class("suggested-action")
        done.connect("clicked", lambda *_: win.close())
        bar.pack_end(done)
        win.set_titlebar(bar)
        win.set_child(view)

        # the moment something shaped like this service's key is copied, the window closes itself and the key is checked
        clip, pat = self.Gdk.Display.get_default().get_clipboard(), prov.get("key_re")

        def copied(cb):
            def got(c, res):
                try:
                    text = c.read_text_finish(res) or ""
                except Exception:
                    text = ""
                if pat and re.search(pat, text) and self._signin_win is win:
                    win.close()
            if self._signin_win is win:
                cb.read_text_async(None, got)
        watch = clip.connect("changed", copied)

        def closed(*_):
            clip.disconnect(watch)
            self._signin_win = None
            self._signin_closed(pid)
            return False
        win.connect("close-request", closed)
        view.load_uri(prov["signin"])
        self._signin_win = win
        win.present()
        self.emit({"t": "signin.result", "waiting": True, "note": T("w_cloud_waiting")})
        return False

    def _signin_closed(self, pid):
        """The sign-in window closed: read the clipboard once, keep only text shaped like this service's key."""
        pat = (llm.CLOUD_PROVIDERS.get(pid) or {}).get("key_re")
        clip = self.Gdk.Display.get_default().get_clipboard()

        def got(cb, res):
            try:
                text = cb.read_text_finish(res) or ""
            except Exception:
                text = ""
            m = re.search(pat, text) if pat else None
            if not m:
                self.emit({"t": "signin.result", "ok": False, "none": True, "note": T("w_cloud_none")})
                if self.screen != "wizard":
                    self.emit({"t": "toast", "text": T("d_signin_none"), "long": True})
                return
            threading.Thread(target=self._signin_check, args=(pid, m.group(0)), daemon=True).start()
        clip.read_text_async(None, got)

    def _signin_check(self, pid, key):
        """Check the copied key with one tiny request and keep the account (the key never reaches the page)."""
        wizard = self.screen == "wizard"
        self.emit({"t": "signin.result", "waiting": True, "note": T("w_cloud_checking")})
        ok, note = llm.cloud_setup({"provider": pid, "key": key}, adopt=not wizard)
        label = ""
        if ok:
            c = config.cloud() or {}
            label = llm.cloud_label(c)
            store.audit("online_model", {"provider": pid, "model": c.get("model"), "key": "…" + key[-4:]}, "account added (signed in)", who="owner")
            self.push_status()
        self.emit({"t": "signin.result", "ok": ok, "note": T("w_cloud_ok", model=label) if ok else note})
        if not wizard:
            self.emit({"t": "toast", "text": T("w_cloud_ok", model=label) if ok else note, "long": True})
            if ok:
                self.close_window("cloud-connect")
                if "panel-settings" in self.windows:
                    self.open_panel("settings")

    def open_connect_panel(self):
        """Connect an online model: one sign-in per service, nothing to type; another service takes a pasted key."""
        items = [{"label": T("w_cloud_signin", name=p["name"]), "say": f"sign in to {p['name']}", "primary": True}
                 for p in llm.CLOUD_PROVIDERS.values() if p.get("signin")]
        self.open_window({"id": "cloud-connect", "replace": True, "title": T("d_connect_title"), "size": "s", "slot": "cascade", "blocks": [
            {"type": "text", "text": T("d_connect_text")},
            {"type": "buttons", "items": items},
            {"type": "buttons", "items": [{"label": T("d_connect_other"), "say": "connect another online service"}]}]})

    def emit(self, msg):
        """Send a message to the page (from any thread)."""
        if not self.ready:
            self._pending.append(msg)
            return
        data = json.dumps(msg, ensure_ascii=False)
        self.GLib.idle_add(self._js, data)
        if msg.get("t") in ("reply.end", "toast", "window", "ask") and (msg.get("t") != "toast" or msg.get("text")):
            self._wake_screen()

    def _wake_screen(self):
        """Something to see (an answer, a timer ringing, a question): a screen that went dark for idleness comes back."""
        now = time.time()
        if now - getattr(self, "_woke", 0) < 5 or not shutil.which("wlopm"):
            return
        self._woke = now
        try:
            subprocess.Popen(["wlopm", "--on", "*"], env=dict(os.environ, **(media.desk_env() or {})),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def _js(self, data):
        if self.webview is not None:
            try:
                self.webview.evaluate_javascript(f"llmos.receive({data})", -1, None, None, None, None, None)
            except Exception:
                pass
        return False

    def _on_js(self, manager, value):
        try:
            msg = json.loads(value.to_json(0))
        except (ValueError, AttributeError):
            return
        if not isinstance(msg, dict):
            return
        threading.Thread(target=self.handle, args=(msg,), daemon=True).start()

    # ---- messages from the page

    def handle(self, msg):
        t = msg.get("t")
        if self.screen != "desk" and t not in SCREEN_MESSAGES.get(self.screen, SCREEN_MESSAGES["boot"]) \
                and not (t in ("rect.result", "rects.result") and _fwcfg("testshell")):
            sys.stderr.write(f"desk: ignored '{t}' from the page on the {self.screen} screen\n")
            return
        if t == "ready":
            self.ready = True
            try:
                with open("/proc/self/stat") as f:
                    start_ticks = int(f.read().split(")")[1].split()[19])
                with open("/proc/uptime") as f:
                    up = float(f.read().split()[0])
                hz = os.sysconf("SC_CLK_TCK")
                sys.stderr.write(f"desk: page ready {up - start_ticks / hz:.1f} s after start, {up:.1f} s after boot\n")
            except (OSError, ValueError, IndexError):
                pass
            self.apply_theme()
            self.push_status()
            for m in self._pending:
                self.emit(m)
            self._pending = []
            self.boot_screen()
            if getattr(self, "_reloaded", False) and self.screen == "desk":
                self._reloaded = False
                for wid, spec in list(self.windows.items()):    # the windows that were open before the page ended
                    self.emit({"t": "window", "id": wid, "spec": spec})
        elif t in ("rect.result", "rects.result"):
            slot = self._rect_wait.get(str(msg.get("id")))
            if slot is not None:
                slot[1] = msg
                slot[0].set()
        elif t == "say":
            self.last_active = time.time()
            text = str(msg.get("text", "")).strip()
            self.say(("ask: " + text) if msg.get("mode") == "ask" and text else text)
        elif t == "chat.say":
            cid = str(msg.get("chat", ""))
            if cid.startswith("side-") and "chat-" + cid in self.windows:
                self.last_active = time.time()
                self.say(str(msg.get("text", "")), chat=cid)
        elif t == "act":
            threading.Thread(target=self.act, args=(str(msg.get("text", "")),), daemon=True).start()
        elif t == "app.save":
            aid, state = str(msg.get("id", "")), msg.get("state")
            w = self.windows.get("app-" + aid)
            if w and w.get("kind") == "app":
                try:
                    if apps.save_state(aid, state):
                        w["state"] = state
                except OSError:
                    pass
        elif t == "app.export":
            self._app_export(str(msg.get("name", "picture.png")), str(msg.get("data", "")))
        elif t == "app.result":
            self._app_res = msg.get("data") or {}
            self._app_evt().set()
        elif t == "signin":
            pid = str(msg.get("provider", ""))
            if (llm.CLOUD_PROVIDERS.get(pid) or {}).get("signin"):
                self.GLib.idle_add(self._signin_open, pid)
        elif t == "active":
            self.last_active = time.time()
        elif t == "vault.create":
            p1, p2 = str(msg.get("p1", "")), str(msg.get("p2", ""))
            if not getattr(self, "vault_nonce", None) or msg.get("nonce") != self.vault_nonce:
                sys.stderr.write("desk: ignored a vault.create that did not come from the passphrase form\n")
            elif config.settings.get("vault"):
                self.emit({"t": "toast", "text": T("vault_exists")})
            elif not p1:
                self.emit({"t": "toast", "text": T("passphrase_empty")})
            elif p1 != p2:
                self.emit({"t": "toast", "text": T("passphrase_mismatch")})
            else:
                self.close_window("vault-form")
                self.vault_nonce = None
                self.emit({"t": "toast", "text": T("creating_vault"), "sticky": "vault"})

                def make(p=p1):           # emit() is thread-safe (it goes through the main loop itself)
                    try:
                        vault.create(p)
                        self.emit({"t": "toast", "text": "", "sticky": "vault"})
                        self.emit({"t": "toast", "text": T("vault_made"), "long": True})
                        self.push_status()
                    except Exception as e:
                        self.emit({"t": "toast", "text": "", "sticky": "vault"})
                        self.emit({"t": "toast", "text": agent._plain_error(str(e)), "long": True})
                threading.Thread(target=make, daemon=True).start()
        elif t == "vault.change":
            p0, p1, p2 = str(msg.get("p0", "")), str(msg.get("p1", "")), str(msg.get("p2", ""))
            if not getattr(self, "vault_nonce", None) or msg.get("nonce") != self.vault_nonce:
                sys.stderr.write("desk: ignored a vault.change that did not come from the passphrase form\n")
            elif not p1:
                self.emit({"t": "toast", "text": T("passphrase_empty")})
            elif p1 != p2:
                self.emit({"t": "toast", "text": T("passphrase_mismatch")})
            else:
                self.close_window("vault-form")
                self.vault_nonce = None

                def change(old=p0, new=p1):
                    try:
                        vault.change_passphrase(old, new)
                        self.emit({"t": "toast", "text": "The passphrase is changed. Use the new one from now on.", "long": True})
                    except Exception:
                        self.emit({"t": "toast", "text": "Not changed: the passphrase you use now was not right.", "long": True})
                threading.Thread(target=change, daemon=True).start()
        elif t in ("folder.lock", "folder.unlock"):
            if not getattr(self, "folder_nonce", None) or msg.get("nonce") != self.folder_nonce:
                sys.stderr.write(f"desk: ignored a {t} that did not come from its form\n")
            else:
                self.folder_nonce = None
                path, pw, pw2 = str(msg.get("path", "")), str(msg.get("password", "")), str(msg.get("password2", pw))
                if t == "folder.lock" and pw != pw2:
                    self.emit({"t": "toast", "text": "The two passwords are different; type the same one twice."})
                    self.folder_form("lock", path)
                    return
                self.close_window("folder-lock")

                def go(t=t, path=path, pw=pw):
                    self.emit({"t": "toast", "text": "Locking the folder…" if t == "folder.lock" else "Unlocking…", "sticky": "flock"})
                    ok, out = (folderlock.lock if t == "folder.lock" else folderlock.unlock)(path, pw)
                    self.emit({"t": "toast", "text": "", "sticky": "flock"})
                    home = config.home().rstrip("/")
                    short = lambda p: "~" + p[len(home):] if p.startswith(home) else p
                    if ok and t == "folder.lock":
                        tip = _lock_tip_take()
                        text = (f"Locked: {os.path.basename(path.rstrip('/'))} is now {short(out)}, which opens only with that password "
                                f"(here: say \u201cunlock {os.path.basename(path.rstrip('/'))}\u201d; on another computer: 7-Zip). "
                                + ("Keep the password somewhere safe: without it the files can't be got back." if tip else "")).rstrip()
                    elif ok:
                        text = f"Unlocked: {short(out)} is a normal folder again."
                    else:
                        text = out[:1].upper() + out[1:] + "."
                        if out == "wrong password":
                            self.folder_form("unlock", path)
                    self.instant_reply("lock folder" if t == "folder.lock" else "unlock folder", text)
                threading.Thread(target=go, daemon=True).start()
        elif t == "mail.form":
            if not getattr(self, "mail_nonce", None) or msg.get("nonce") != self.mail_nonce:
                sys.stderr.write("desk: ignored a mail.form that did not come from the email form\n")
            else:
                self.mail_nonce = None
                addr, pw = str(msg.get("address", "")).strip(), str(msg.get("password", ""))
                self.close_window("mail-form")

                def setup(addr=addr, pw=pw):
                    self.emit({"t": "toast", "text": "Checking your email account…", "sticky": "mail"})
                    self.ctx.current_request = "set up my email"
                    out = agent.execute(self.ctx, "mail_setup", {"address": addr, "password": pw})
                    self.emit({"t": "toast", "text": "", "sticky": "mail"})
                    ok = not re.match(r"(?i)(error|could not|failed|not done|login failed|authentication)", out)
                    self.instant_reply("set up my email", ("Your email is set up: say \u201ccheck my email\u201d." if ok else
                                                           agent._cap(agent.scrub(out))))
                    if not ok:
                        self.mail_form()
                threading.Thread(target=setup, daemon=True).start()
        elif t == "wifi.join":
            if not getattr(self, "wifi_nonce", None) or msg.get("nonce") != self.wifi_nonce:
                sys.stderr.write("desk: ignored a wifi.join that did not come from the Wi-Fi form\n")
            else:
                self.wifi_nonce = None
                self.close_window("wifi-join")

                def join(ssid=str(msg.get("ssid", "")), pw=str(msg.get("password", ""))):
                    self.emit({"t": "toast", "text": T("d_net_joining", ssid=ssid), "sticky": "wifi"})
                    good, note = _wifi_connect(ssid, pw)
                    self.emit({"t": "toast", "text": "", "sticky": "wifi"})
                    self.emit({"t": "toast", "text": T("w_wifi_ok") if good else note, "long": not good})
                    self.push_status()
                    self.network_panel()
                threading.Thread(target=join, daemon=True).start()
        elif t == "cloud.setup":
            if not getattr(self, "cloud_nonce", None) or msg.get("nonce") != self.cloud_nonce:
                sys.stderr.write("desk: ignored a cloud.setup that did not come from the online-model form\n")
            else:
                self.cloud_nonce = None
                self.close_window("cloud-form")
                self.emit({"t": "toast", "text": T("d_cloud_checking"), "sticky": "cloud"})

                def check(fields=dict(msg)):
                    ok, note = llm.cloud_setup(fields)
                    self.emit({"t": "toast", "text": "", "sticky": "cloud"})
                    self.emit({"t": "toast", "text": note, "long": True})
                    if ok:
                        store.audit("online_model", {"provider": fields.get("provider"), "model": fields.get("model"),
                                                     "key": "…" + str(fields.get("key", ""))[-4:]}, "account added", who="owner")
                        self.push_status()
                        if "panel-settings" in self.windows:
                            self.open_panel("settings")
                threading.Thread(target=check, daemon=True).start()
        elif t == "connector.add":
            if not getattr(self, "connector_nonce", None) or msg.get("nonce") != self.connector_nonce:
                sys.stderr.write("desk: ignored a connector.add that did not come from the connector form\n")
            else:
                self.connector_nonce = None
                self.close_window("connector-form")
                self.emit({"t": "toast", "text": T("d_conn_checking"), "sticky": "conn"})

                def go(f=dict(msg)):
                    from . import mcp
                    try:
                        transport = (f.get("transport") or ("http" if f.get("url") and not f.get("command") else "stdio"))
                        spec = mcp.add(f.get("name") or "connector", transport, command=f.get("command", ""), url=f.get("url", ""))
                        ok, res = mcp.probe(spec)
                        if not ok:
                            mcp.remove(spec["name"])
                            note = f"{T('error')}: {res}"
                        else:
                            tools.sync_connectors()
                            store.audit("manage_connectors", {"name": spec["name"], "transport": transport,
                                                              "where": spec["command"] or spec["url"]}, "connector added", who="owner")
                            note = T("d_conn_added", n=len(res), name=spec["name"])
                            self.push_status()
                            if "panel-connectors" in self.windows:
                                self.open_panel("connectors")
                    except Exception as e:
                        note = agent._plain_error(str(e))
                    self.emit({"t": "toast", "text": "", "sticky": "conn"})
                    self.emit({"t": "toast", "text": note, "long": True})
                threading.Thread(target=go, daemon=True).start()
        elif t == "conduct.save":
            if not getattr(self, "conduct_nonce", None) or msg.get("nonce") != self.conduct_nonce:
                sys.stderr.write("desk: ignored a conduct.save that did not come from the conduct editor\n")
            else:
                self.conduct_nonce = None
                self.close_window("conduct-form")
                text = str(msg.get("text", "")).strip()
                try:
                    if text:
                        config.write_conduct(text + "\n")
                        note = T("d_conduct_saved")
                    else:
                        try:
                            config.remove_conduct()
                        except OSError:
                            pass
                        note = T("d_conduct_reset")
                    store.audit("edit_conduct", {"chars": len(text)}, "conduct edited by owner" if text else "conduct reset", who="owner")
                    if "panel-settings" in self.windows:
                        self.open_panel("settings")
                except OSError as e:
                    note = agent._plain_error(str(e))
                self.emit({"t": "toast", "text": note, "long": True})
        elif t == "dialog":
            d = self.dialogs.get(str(msg.get("id")))
            if d:
                d[1] = msg.get("value")
                d[0].set()
        elif t == "unlock":
            self.unlock(str(msg.get("passphrase", "")))
        elif t == "wizard":
            if self.screen == "wizard":          # never from a window composed later
                self.wizard_step(str(msg.get("step", "")), msg.get("value"))
        elif t == "tz.search":
            self.emit({"t": "tz.results", "q": str(msg.get("q", "")), "items": system.timezone_search(str(msg.get("q", "")), 8)})
        elif t == "wifi.scan":
            try:
                nets = _wifi_scan()
            except Exception:
                nets = []
            self.emit({"t": "wifi.list", "items": nets})
        elif t == "voice":
            self.voice_turn()
        elif t == "cancel":
            self.stop_all()
        elif t == "queue.drop":
            self.drop_queued(str(msg.get("id", "")))
        elif t == "window.closed" and str(msg.get("id")) == "away":
            self.windows.pop("away", None)
            store.mark_seen(getattr(self, "away_ids", []))
            self.away_ids = []
            self._inbox_key = "unset"
        elif t == "window.closed":
            self.windows.pop(str(msg.get("id")), None)
        elif t == "media":
            self.media_action(str(msg.get("action", "")), value=msg.get("value"))
        elif t == "app.close":
            self.close_app(int(msg.get("pid", 0) or 0))
        elif t == "app.focus":
            a = self.apps.get(int(msg.get("pid", 0) or 0))
            if a:
                threading.Thread(target=self._focus_or_reopen, args=(a["argv"], a.get("name", "")), daemon=True).start()
        elif t == "lock":
            if config.settings.get("vault"):
                self.lock()             # at once, not queued behind a running request
            else:
                self.say("lock")        # nothing to lock with: the assistant says so (and how to set one up)

    # ---- screens

    def boot_screen(self):
        if config.settings.get("vault") and not vault.unlocked():
            self._keybinds(False)       # the passphrase screen at start-up keeps no shortcuts either (no terminal)
            self.set_screen("lock")
            return
        if not config.settings.get("onboarded"):
            self.set_screen("wizard", self._wizard_data())
            self._model_watch()
            return
        self.enter_desk()

    def _wizard_data(self):
        hint = _fwcfg("lang")
        inst = {m["id"] for m in models.installed()}
        sysinfo, tiers_on, tiers_off = _system_check(), _model_tiers(True), _model_tiers(False)
        return {"timezone": system.timezone(), "tz_label": system.timezone_search("", 1)[0] if system.timezone() else None,
                "languages": self._language_choices(), "lang_hint": hint if hint in i18n.BUILTIN else "",
                "wifi": _wifi_device() is not None, "online": _online(), "ram_gb": round(models.ram_gb(), 1),
                "models": [{"id": m["id"], "name": m["name"], "ram_gb": m["ram_gb"], "size_gb": round(m["size"] / 1e9, 1), "installed": m["id"] in inst}
                           for m in models.catalog()],
                "system": sysinfo, "tiers": {"on": tiers_on, "off": tiers_off},
                "all_models": {"on": _model_all(True), "off": _model_all(False)},
                "recommend": {"on": _recommend(sysinfo, tiers_on), "off": _recommend(sysinfo, tiers_off)},
                "cloud_providers": [{"id": k, "name": p["name"], "key_hint": p["key_hint"], "console": p["console"], "models": p["models"],
                                     "signin": bool(p.get("signin"))} for k, p in llm.CLOUD_PROVIDERS.items()]}

    def set_screen(self, name, data=None):
        self.screen = name
        self.emit({"t": "screen", "name": name, "data": data or {}})

    def enter_desk(self):
        config.ensure_folders()
        self.last_active = time.time()
        self.set_screen("desk", {"name": config.Profile().get("name", "")})
        self.push_status()
        self._model_watch()
        self.show_away()
        def on_unlock():
            for t in store.on_event("unlock"):
                if t.get("kind") == "reminder":
                    self.instant_reply("(on unlock)", t["task"])
                    if config.settings.get("speak_replies") or re.search(r"\b(?:say|tell|greet|speak)\b", t.get("when", "") + " " + t["task"], re.I):
                        self.ctx.background(lambda w=t["task"]: voice.speak(w))
                else:
                    self.say(t["task"])
        if store.on_event("unlock"):
            threading.Thread(target=lambda: (time.sleep(2), on_unlock()), daemon=True).start()
        auto = [a for a in (config.settings.get("autostart") or []) if str(a).strip()]
        if auto:                              # "start X when I log in": each time the desk opens (locking closes programs)
            threading.Thread(target=lambda: [(time.sleep(1.5), self.act("open " + a)) for a in auto], daemon=True).start()
        if _live() and not getattr(self, "_live_told", False):
            self._live_told = True          # once per start: running from the stick keeps nothing
            self.open_window({"id": "live", "replace": True, "title": T("d_live_title"), "size": "s", "slot": "cascade", "blocks": [
                {"type": "text", "text": T("d_live_text")},
                {"type": "buttons", "items": [{"label": T("d_live_install"), "say": "install llm os on this computer", "primary": True},
                                              {"label": T("d_live_keep"), "say": "close the live window"}]}]})

    def _model_watch(self):
        def watch():
            if llm.health():
                self.push_status()
                agent.warm_up()
                return
            self.emit({"t": "toast", "text": T("loading_model"), "sticky": "model"})
            llm.wait_ready(900)
            self.emit({"t": "toast", "text": "", "sticky": "model"})
            self.push_status()
            agent.warm_up()
        threading.Thread(target=watch, daemon=True).start()

    def _language_choices(self):
        return [{"code": c, "label": i18n.display_name(c)} for c in ("en", "zh", "es", "fr", "de", "ja")]

    # ---- theme and status

    def theme_payload(self):
        th = ui.Theme()
        css = {}
        if th.bg:
            css["--bg"] = _hex(th.bg)
        if th.fg:
            css["--fg"] = _hex(th.fg)
        if th.acc:
            css["--accent"] = _hex(th.acc)
            css["--on-accent"] = _best_text(css["--accent"])
        css["--on-danger"] = _best_text("#ef5a6f")
        corners = th.corners if th.corners in ("rounded", "square", "double", "heavy", "none") else "rounded"
        css["--radius"] = {"rounded": "14px", "square": "0px", "none": "24px", "double": "6px", "heavy": "8px"}[corners]
        css["--radius-sm"] = {"rounded": "9px", "square": "0px", "none": "16px", "double": "4px", "heavy": "5px"}[corners]
        css["--border-w"] = {"double": "3px", "heavy": "2px"}.get(corners, "1px")
        css["--border-style"] = "double" if corners == "double" else "solid"
        appear = config.settings.get("appearance", {}) or {}
        css["--font"] = themes.FONTS.get(appear.get("font") or "sans", themes.FONTS["sans"]) + \
            ', "Noto Sans CJK SC", "Noto Sans Arabic", "Noto Sans Hebrew", "Noto Sans Devanagari", "Noto Sans Thai", sans-serif'
        backdrop = appear.get("backdrop") or "living"
        style = str(appear.get("style") or "")
        motion = getattr(th, "motion", "full")
        lang = i18n.lang_code(config.llm_language())
        strings = {k: T(k) for k in _PAGE_KEYS}
        strings.update({k: T(k, area="settings") for k in ("settings",)})
        mode = "light" if (th.bg and ui._lum(th.bg) > 0.4) else "dark"
        return {"t": "theme", "css": css, "mode": mode, "corners": corners, "lang": lang, "motion": motion, "style": style,
                "clock24": config.settings.get("clock24", None),
                "layout": config.settings.get("appearance.layout") or "clean",
                "software": os.environ.get("LIBGL_ALWAYS_SOFTWARE") == "1",
                "dir": "rtl" if lang in ("ar", "he", "fa", "ur") else "ltr", "strings": strings,
                "backdrop": backdrop,
                "wallpaper": "" if backdrop != "photo" else ("file://" + _wallpaper() + "?" + str(int(os.path.getmtime(_wallpaper())))) if (config.settings.get("onboarded") and (not config.settings.get("vault") or vault.unlocked()) and os.path.exists(_wallpaper())) else ""}

    def _zoom(self):
        return getattr(self, "display_scale", 1.0) * ui.Theme().scale / 100

    def _apply_zoom(self):
        """The page's zoom: the scale of the screen the desk is on times the owner's text size (main thread)."""
        if self.webview is None:
            return False
        try:
            disp = self.Gdk.Display.get_default()
            surf = self.gtkwin.get_surface() if getattr(self, "gtkwin", None) is not None else None
            mon = disp.get_monitor_at_surface(surf) if surf is not None else None
            mons = disp.get_monitors()
            if mon is None and mons.get_n_items():
                mon = mons.get_item(0)
            self.display_scale = _display_scale(mon) if mon is not None else 1.0
            # scale the whole screen in the compositor, so the programs (the browser, Files…) are as big as the desk;
            # the screen then reports its size in scaled pixels and the page needs no zoom of its own for it
            conn = mon.get_connector() if mon is not None else None
            done = getattr(self, "_out_scaled", {})
            if self.display_scale > 1 and conn and conn not in done and shutil.which("wlr-randr") and not os.environ.get("LLMOS_NO_OUTPUT_SCALE"):
                done[conn] = self.display_scale
                self._out_scaled = done
                if subprocess.run(["wlr-randr", "--output", conn, "--scale", str(self.display_scale)], capture_output=True, timeout=10).returncode == 0:
                    self.display_scale = 1.0
                    self.GLib.timeout_add(1500, self._apply_zoom)
            elif conn in done:
                self.display_scale = 1.0
        except Exception as e:
            sys.stderr.write(f"desk: screen size unknown ({e}); 100%\n")
            self.display_scale = 1.0
        try:
            self.webview.set_zoom_level(self._zoom())
        except Exception as e:
            sys.stderr.write(f"desk: zoom not applied: {e}\n")
        return False

    def apply_theme(self):
        ui.reload_theme()
        pay = self.theme_payload()
        self.emit(pay)
        a = config.settings.get("appearance", {}) or {}
        threading.Thread(target=themes.apply_programs, args=(config.home(), pay["mode"], a.get("font") or "sans",
                         pay["css"].get("--bg", ""), pay["css"].get("--fg", ""), pay["css"].get("--accent", ""), ui.Theme().scale), daemon=True).start()
        if getattr(self, "GLib", None) and self.webview is not None:
            self.GLib.idle_add(self._apply_zoom)
        if getattr(self, "GLib", None):
            self.GLib.idle_add(lambda: (self._safe_proxy(), False)[1])
        else:
            self._safe_proxy()

    def _safe_proxy(self):
        try:
            self._apply_proxy()
        except Exception as e:
            sys.stderr.write(f"desk: proxy not applied: {e}\n")

    def push_status(self):
        s = config.settings.all()
        m = models.active()
        self.emit({"t": "status", "model": m["name"] if m else "", "model_ok": llm.health(),
                   "autonomy": s.get("autonomy", "balanced"), "host_gpu": models.host_mode(),
                   "brain": s.get("brain", "local"), "cloud": llm.cloud_label() if vault.unlocked() or not s.get("vault") else "",
                   "tor": bool(s.get("tor")), "internet": s.get("internet", "yes"),
                   "vault": ("locked" if not vault.unlocked() else "on") if s.get("vault") else "off",
                   "focus": bool(s.get("focus", {}).get("on")), "name": config.Profile().get("name", ""),
                   "tz": system.timezone(), "busy": self.busy, "listening": self.listening,
                   "mic": voice.available(), "tasks": len(store.tasks()), "live": _live(),
                   "net": ("wifi" if _wifi_device() and _online() else "wired" if _online() else "offline"),
                   "battery": _battery(), "volume": self._volume_pct(), "muted": getattr(self, "_muted", False)})

    def _volume_pct(self):
        try:
            out = devices.volume()
            self._muted = "(muted)" in out
            m = re.search(r"Volume is (\d+)%", out)
            return int(m.group(1)) if m else None
        except Exception:
            return None

    # ---- windows

    def open_window(self, spec):
        spec = uispec.normalize(spec)
        if not spec:
            return None
        wid = spec.get("id") or ""
        if not wid or wid not in self.windows and not spec.get("replace"):
            if not wid:
                self.win_seq += 1
                wid = f"w{self.win_seq}"
        spec["id"] = wid
        self.windows[wid] = spec
        self.emit({"t": "window", "id": wid, "spec": spec})
        return wid

    def close_window(self, wid):
        self.windows.pop(wid, None)
        self.emit({"t": "window.close", "id": wid})

    # ---- the owner's apps (apps.py): each one a sandboxed page in a window

    def show_app(self, app):
        import urllib.parse
        wid = "app-" + app["id"]
        spec = {"id": wid, "title": app["title"], "kind": "app", "size": app.get("size") or "m", "app": app["id"],
                "src": "file://" + urllib.parse.quote(app["file"]), "state": apps.load_state(app["id"]),
                "blocks": [{"type": "text", "text": app["title"]}]}
        self.windows[wid] = spec
        self.emit({"t": "window", "id": wid, "spec": spec})

    # ---- quick panels: the status bar's network, sound and power

    def network_panel(self, nets=None):
        now, dev = _wifi_now(), _wifi_device()
        state = (T("d_net_wifi", ssid=now) if now else T("d_net_wired") if _online() else T("d_net_offline"))
        blocks = [{"type": "kv", "rows": [[T("d_net_status"), state]]}]
        if not dev:
            blocks.append({"type": "text", "text": T("d_net_nowifi"), "dim": True})
        elif nets is None:
            blocks.append({"type": "text", "text": T("d_net_scanning"), "dim": True})
            threading.Thread(target=lambda: self.network_panel(_wifi_scan()), daemon=True).start()
        elif not nets:
            blocks.append({"type": "text", "text": T("d_net_none"), "dim": True})
        else:
            blocks.append({"type": "list", "items": [
                {"title": ("🔒 " if n["secured"] else "") + n["ssid"], "meta": "▂▄▆█"[:max(1, min(4, n["signal"]))],
                 "actions": [{"label": "Disconnect", "say": "disconnect from wifi"}, {"label": "Forget", "say": "forget wifi " + n["ssid"], "danger": True}]
                 if n["ssid"] == now else [{"label": T("d_connect"), "say": "join wifi " + n["ssid"], "primary": True}]}
                for n in nets[:20]]})
        airplane = _airplane()
        blocks.append({"type": "buttons", "items": ([{"label": T("d_net_rescan"), "say": "show wifi networks"}] if dev else []) +
                       ([{"label": "Airplane mode: on" if airplane else "Airplane mode", "say": "airplane mode off" if airplane else "airplane mode on",
                          "primary": airplane}] if shutil.which("rfkill") else []) +
                       [{"label": T("settings"), "say": "settings"}]})
        self.open_window({"id": "panel-network", "replace": True, "title": T("d_network"), "size": "s", "slot": "side", "blocks": blocks})

    def wifi_join(self, ssid):
        nets = {n["ssid"]: n for n in (_wifi_scan() if _wifi_device() else [])}
        n = nets.get(ssid)
        if n and not n["secured"]:
            good, note = _wifi_connect(ssid, "")
            self.emit({"t": "toast", "text": (T("w_wifi_ok") if good else note)})
            return self.network_panel()
        import secrets
        self.wifi_nonce = secrets.token_hex(12)
        self.open_window({"id": "wifi-join", "replace": True, "title": ssid, "size": "s", "slot": "cascade", "blocks": [
            {"type": "form", "fields": [{"name": "password", "label": T("w_wifi_pass"), "kind": "password"},
                                        {"name": "ssid", "kind": "hidden", "value": ssid},
                                        {"name": "nonce", "kind": "hidden", "value": self.wifi_nonce}],
             "submit": {"label": T("d_connect"), "post": "wifi.join"}}]})

    def windows_panel(self):
        items = [{"title": w.get("title") or "Window", "subtitle": "on the desk",
                  "actions": [{"label": "Close", "say": f"close window {wid}"}]} for wid, w in self.windows.items() if wid != "panel-open"]
        for aid in dict.fromkeys(wm.windows()) if shutil.which("lswt") else []:
            nm = wm.NAMES.get(aid, aid)
            items.append({"title": nm[:1].upper() + nm[1:], "subtitle": "a program",
                          "actions": [{"label": "Show", "say": f"switch to {aid}", "primary": True}, {"label": "Close", "say": f"close {aid}"}]})
        return {"id": "panel-open", "replace": True, "title": "Open now", "size": "s", "slot": "side",
                "blocks": [{"type": "list", "items": items}] if items else [{"type": "text", "text": "Nothing is open.", "dim": True}]}

    def folder_form(self, kind, path):
        """The password for locking or unlocking a folder: typed into a form, never into the request box."""
        import secrets
        self.folder_nonce = secrets.token_hex(12)
        home = config.home().rstrip("/")
        shown = "~" + path[len(home):] if path.startswith(home) else path
        fields = [{"name": "password", "label": "Password", "kind": "password"}]
        if kind == "lock":
            fields.append({"name": "password2", "label": "The same password again", "kind": "password"})
        fields += [{"name": "path", "kind": "hidden", "value": path}, {"name": "nonce", "kind": "hidden", "value": self.folder_nonce}]
        tip = _lock_tip_take() if kind == "lock" else False
        self.open_window({"id": "folder-lock", "replace": True, "title": ("Lock " if kind == "lock" else "Unlock ") + os.path.basename(path.rstrip("/")),
                          "size": "s", "slot": "cascade", "blocks": [
            {"type": "text", "text": (f"{shown} becomes one locked file that opens only with this password, here or on any computer with 7-Zip."
                                      + (" Without the password the files can't be got back, so keep it safe." if tip else "")) if kind == "lock" else
                                      f"The password {shown} was locked with.", "dim": True},
            {"type": "form", "fields": fields, "submit": {"label": "Lock" if kind == "lock" else "Unlock", "post": "folder." + kind}}]})

    def mail_form(self):
        """Email set up here (to read and answer it on this computer): a form, nothing typed into the request box."""
        import secrets
        self.mail_nonce = secrets.token_hex(12)
        self.open_window({"id": "mail-form", "replace": True, "title": "Set up email", "size": "s", "slot": "cascade", "blocks": [
            {"type": "text", "text": "Your email address and its password. Gmail, Outlook, Yahoo and iCloud want an \u201capp password\u201d "
                                     "here instead of your normal one: make one in your account's security settings (the button opens it).", "dim": True},
            {"type": "form", "fields": [{"name": "address", "label": "Email address", "kind": "text"},
                                        {"name": "password", "label": "Password (or app password)", "kind": "password"},
                                        {"name": "nonce", "kind": "hidden", "value": self.mail_nonce}],
             "submit": {"label": "Set up", "post": "mail.form"}},
            {"type": "buttons", "items": [{"label": "Gmail app password", "say": "open https://myaccount.google.com/apppasswords"},
                                          {"label": "Outlook app password", "say": "open https://account.live.com/proofs/AppPassword"},
                                          {"label": "Just use webmail instead", "say": "check my email"}]}]})

    def sound_panel(self):
        v = self._volume_pct()
        muted = getattr(self, "_muted", False)
        blocks = [{"type": "kv", "rows": [[T("d_volume"), (f"{v}%" + (" · " + T("d_muted", "muted") if muted else "")) if v is not None else T("d_sound_none")]]}]
        if v is not None:
            blocks.append({"type": "slider", "value": v, "min": 0, "max": 100, "say": "set the volume to {v}%"})
            blocks.append({"type": "buttons", "items": [{"label": "🔈 " + T("d_unmute", "Unmute"), "say": "unmute", "primary": True} if muted
                                                        else {"label": "🔇 " + T("d_mute", "Mute"), "say": "mute"}] +
                           [{"label": f"{p}%", "say": f"set the volume to {p}%"} for p in (25, 50, 75, 100)]})
        self.note_window_source("panel-sound", "call", "sound_panel")      # refreshed after a change
        outs = syspanels.audio_devices("Sinks")
        if len(outs) > 1:
            blocks.append({"type": "heading", "text": "Sound comes out of"})
            blocks.append({"type": "choices", "selected": next((n for _, n, d in outs if d), ""),
                           "items": [{"label": n, "say": f"use sound output {i}"} for i, n, d in outs]})
        mics = syspanels.audio_devices("Sources")
        if len(mics) > 1:
            blocks.append({"type": "heading", "text": "Microphone"})
            blocks.append({"type": "choices", "selected": next((n for _, n, d in mics if d), ""),
                           "items": [{"label": n, "say": f"use sound input {i}"} for i, n, d in mics]})
        if shutil.which("pavucontrol"):
            blocks.append({"type": "buttons", "items": [{"label": T("d_sound_more"), "say": "open pavucontrol"}]})
        self.open_window({"id": "panel-sound", "replace": True, "title": T("d_sound"), "size": "s", "slot": "side", "blocks": blocks})

    def power_panel(self):
        items = []
        if config.settings.get("vault"):
            items.append({"label": T("d_lock"), "say": "lock"})
        items += [{"label": T("d_sleep"), "say": "sleep"}, {"label": T("d_restart"), "say": "restart"},
                  {"label": T("d_shutdown"), "say": "shut down", "danger": True}]
        b = _battery()
        blocks = ([{"type": "kv", "rows": [[T("d_battery"), f"{b['pct']}%" + (" ⚡" if b["charging"] else "")]]}] if b else []) + \
            [{"type": "buttons", "items": items}]
        if _live():
            blocks.append({"type": "buttons", "items": [{"label": T("d_live_install"), "say": "install llm os on this computer", "primary": True}]})
        self.open_window({"id": "panel-power", "replace": True, "title": T("d_power"), "size": "s", "slot": "side", "blocks": blocks})

    def show_apps(self):
        mine = apps.installed()
        items = [{"title": a["title"], "subtitle": time.strftime("%b %d", time.localtime(a["made"])),
                  "actions": [{"label": T("d_open"), "say": f"open the app {a['id']}", "primary": True},
                              {"label": T("d_remove"), "say": f"remove the app {a['id']}", "danger": True}]} for a in mine]
        blocks = [{"type": "list", "items": items}] if items else [{"type": "text", "text": T("d_apps_none"), "dim": True}]
        from . import programs
        progs = programs.everyday()
        if progs:
            blocks += [{"type": "heading", "text": T("d_programs")},
                       {"type": "buttons", "items": [{"label": lab, "say": f"open {p['name']}"} for lab, p in progs[:40]]}]
        blocks += [{"type": "heading", "text": T("d_apps_make")},
                   {"type": "buttons", "items": [{"label": t["title"], "say": f"make a {t['id']} app"} for t in apps.templates()]},
                   {"type": "text", "text": T("d_apps_hint"), "dim": True},
                   {"type": "buttons", "items": [{"label": T("d_apps_connectors"), "say": "connectors"}]}]
        self.open_window({"id": "apps", "replace": True, "title": T("d_myapps"), "size": "m", "slot": "side", "blocks": blocks})

    def note_window_source(self, wid, tool, args):
        self.__dict__.setdefault("_win_src", {})[wid] = (tool, args)

    def refresh_windows(self):
        """Rebuild the open windows that show something an action may have changed (a folder, the models, the inbox,
        a settings panel), in the background, without a reply or activity line. A window only refreshes from the
        read-only tool or the panel that made it."""
        src = dict(self.__dict__.get("_win_src", {}))
        if not src or getattr(self, "_refreshing", False):
            return

        def run():
            self._refreshing = True
            try:
                quiet = _QuietCtx(self)
                for wid, (tool, args) in src.items():
                    if wid not in self.windows:
                        self._win_src.pop(wid, None)
                        continue
                    try:
                        if tool == "panel":
                            self.open_panel(args)
                        elif tool == "call":
                            getattr(self, args)()
                        elif tool in tools.REGISTRY:
                            quiet._cur_tool = (tool, args, tools.READ)
                            tools.REGISTRY[tool].fn(dict(args), quiet)
                    except Exception as e:
                        sys.stderr.write(f"desk: refreshing {wid} failed: {e}\n")
            finally:
                self._refreshing = False
        threading.Thread(target=run, daemon=True).start()

    def open_panel(self, which):
        self.note_window_source("panel-" + which, "panel", which)
        spec = self.panel_spec(which)
        if spec:
            spec["id"] = "panel-" + which
            spec["replace"] = True
            self.open_window(spec)

    def models_panel(self):
        """The model manager: on-device models and the optional online model, each with its facts and
        drawbacks, every action a spoken command so a button never does more than the owner could say."""
        L = lambda k, **kw: T(k, area="settings", **kw)

        def facts(good, limits):
            lines = []
            if good:
                lines.append(f"**{L('d_good_at')}** " + "; ".join(good))
            if limits:
                lines.append(f"**{L('d_watch')}** " + "; ".join(limits))
            return "\n\n".join(lines)

        cur = models.active()
        inst_ids = {m["id"] for m in models.installed()}
        host = models.host_mode()
        local = []
        for m in models.catalog():
            active = bool(cur and m["id"] == cur["id"])
            installed = m["id"] in inst_ids
            acts = []
            if not active and installed and not host:
                acts.append({"label": T("d_use"), "say": f"use the model {m['id']}", "primary": True})
            if not installed:
                acts.append({"label": T("d_download", size=f"{m['size'] / 1e9:.1f}"), "say": f"download the model {m['id']}"})
            if installed and not active:
                acts.append({"label": T("d_remove"), "say": f"remove the model {m['id']}", "danger": True})
            sub = " · ".join(x for x in [m["maker"], m.get("license", ""), f"{m['size'] / 1e9:.1f} GB",
                                         f"{m['ram_gb']} GB RAM", m.get("speed", "")] if x)
            if m["ram_gb"] > models.ram_gb() - 1:
                sub += " · " + T("w_model_slow")
            local.append({"title": m["name"], "subtitle": sub, "detail": facts(m.get("good_at"), m.get("limits")),
                          "meta": T("active") if active else (T("installed") if installed else ""), "actions": acts})

        blocks = [{"type": "text", "text": L("d_models_intro") + f"  ·  {models.ram_gb():.1f} GB RAM", "dim": True},
                  {"type": "heading", "text": L("s_on_device")}]
        if host:
            blocks.append({"type": "text", "text": models.HOST_MODE_MSG, "dim": True})
        blocks.append({"type": "list", "items": local})
        # agentic refresh: new models come out constantly, so a button searches Hugging Face for newer ones
        blocks.append({"type": "buttons", "items": [{"label": L("d_refresh_models"), "say": "check for new and updated models"}]})

        # the optional online model
        blocks.append({"type": "heading", "text": L("s_online")})
        blocks.append({"type": "text", "text": L("d_online_note"), "dim": True})
        acct = config.cloud()
        brain = config.settings.get("brain", "local")
        if acct:
            cur_online = acct.get("model")
            prov = llm.CLOUD_PROVIDERS.get(acct.get("provider"), {})
            catalog = prov.get("models") or [{"id": cur_online, "name": llm.cloud_label(acct), "good_at": [], "limits": [], "speed": "", "cost": ""}]
            online = []
            for m in catalog:
                on = m["id"] == cur_online
                sub = " · ".join(x for x in [m.get("speed", ""), (L("d_cost", cost=m["cost"]) if m.get("cost") else "")] if x)
                online.append({"title": m["name"], "subtitle": sub, "detail": facts(m.get("good_at"), m.get("limits")),
                               "meta": L("d_in_use") if on else "",
                               "actions": [] if on else [{"label": T("d_use"), "say": f"use the online model {m['id']}", "primary": True}]})
            blocks.append({"type": "list", "items": online})
            blocks.append({"type": "kv", "rows": [[L("s_online_model"), f"{prov.get('name', acct.get('provider'))} · {L('d_key_ending', k=acct['key'][-4:])}"],
                                                  [L("s_brain"), L("v_brain_" + (brain if brain in ("local", "ask", "cloud") else "local"))]]})
            blocks.append({"type": "buttons", "items": [{"label": L("d_change_online"), "say": "set up the online model"},
                                                        {"label": T("d_forget"), "say": "forget the online model", "danger": True}]})
        else:
            tease = []
            for m in llm.CLOUD_PROVIDERS["anthropic"]["models"]:
                sub = " · ".join(x for x in [m.get("speed", ""), (L("d_cost", cost=m["cost"]) if m.get("cost") else "")] if x)
                tease.append({"title": m["name"], "subtitle": sub, "detail": facts(m.get("good_at"), m.get("limits"))})
            blocks.append({"type": "list", "items": tease})
            blocks.append({"type": "text", "text": llm.CLOUD_PROVIDERS["openai"].get("note", ""), "dim": True})
            blocks.append({"type": "buttons", "items": [{"label": L("d_set_up_online"), "say": "set up the online model"}]})

        # speech to text: used by the microphone and by system-wide dictation (Super+D types at the cursor)
        blocks.append({"type": "heading", "text": L("s_voice_models")})
        blocks.append({"type": "text", "text": L("d_voice_intro"), "dim": True})
        cur_v = voice.active_voice()
        inst_v = {m["id"] for m in voice.installed_voice()}
        vrows = []
        for m in voice.voice_catalog():
            on = bool(cur_v and m["id"] == cur_v["id"])
            have = m["id"] in inst_v
            acts = []
            if have and not on:
                acts.append({"label": T("d_use"), "say": f"use the {m['id']} voice model", "primary": True})
            if not have:
                acts.append({"label": T("d_download", size=f"{m['size'] / 1e9:.1f}"), "say": f"download the {m['id']} voice model"})
            if have and not on and not m.get("shipped"):
                acts.append({"label": T("d_remove"), "say": f"remove the {m['id']} voice model", "danger": True})
            sub = " · ".join(x for x in [L("d_voice_accuracy", a=m.get("accuracy", "")), m.get("speed", ""),
                                         f"{m['size'] / 1e6:.0f} MB", f"{m['ram_gb']} GB RAM",
                                         f"{m.get('langs', '')} {L('d_languages')}"] if x.strip())
            vrows.append({"title": m["name"], "subtitle": sub, "detail": facts(m.get("good_at"), m.get("limits")),
                          "meta": L("d_in_use") if on else (T("installed") if have else ""), "actions": acts})
        blocks.append({"type": "list", "items": vrows})
        return {"title": T("models"), "kind": "panel", "size": "l", "blocks": blocks}

    def connectors_panel(self):
        """The connectors (apps) manager: installed connectors and the tools each adds, with enable/disable/
        remove, and a form to add one. Every connector tool runs under the same autonomy policy and audit log."""
        from . import mcp
        L = lambda k, **kw: T(k, area="settings", **kw)
        regs = mcp.connectors()
        blocks = [{"type": "text", "text": L("d_connectors_intro"), "dim": True}]
        if not regs:
            blocks.append({"type": "text", "text": L("d_no_connectors")})
        for c in regs:
            on = c.get("enabled", True)
            where = c["command"] if c["transport"] == "stdio" else c["url"]
            ts = [t.get("name") for t in mcp.tools_of(c["name"])] if on else []
            detail = ("**" + L("d_conn_tools") + "** " + ", ".join(ts)) if ts else (L("d_conn_unreachable") if on else "")
            acts = [{"label": L("v_off") if on else L("v_on"),
                     "say": (f"disable the connector {c['name']}" if on else f"enable the connector {c['name']}")},
                    {"label": T("d_remove"), "say": f"remove the connector {c['name']}", "danger": True}]
            blocks.append({"type": "list", "items": [{"title": c["name"] + ("" if on else " · " + L("v_off")),
                           "subtitle": f"{c['transport']} · {where}", "detail": detail, "actions": acts}]})
        blocks.append({"type": "buttons", "items": [{"label": L("d_add_connector"), "say": "add a connector"}]})
        blocks.append({"type": "text", "text": L("d_connectors_hint"), "dim": True})
        return {"title": L("connectors"), "kind": "panel", "size": "l", "blocks": blocks}

    def panel_spec(self, which):
        s = config.settings.all()
        if which == "settings":
            L = lambda k, **kw: T(k, area="settings", **kw)
            auto = s.get("autonomy", "balanced")
            pick = lambda k, v: {"label": L(k), "say": v}
            blocks = [
                {"type": "buttons", "items": [{"label": T("d_network"), "say": "network"}, {"label": T("d_sound"), "say": "sound"},
                                              {"label": "Displays", "say": "displays"}, {"label": "Keyboard and mouse", "say": "keyboard and mouse"},
                                              {"label": "Bluetooth", "say": "bluetooth"}, {"label": "Printers", "say": "printers"},
                                              {"label": "Drives", "say": "drives"}, {"label": "Storage", "say": "storage"},
                                              {"label": "Updates", "say": "updates"}, {"label": T("d_power"), "say": "power"},
                                              {"label": "What's running", "say": "task manager"}, {"label": T("d_myapps"), "say": "show my apps"},
                                              {"label": T("d_conversations"), "say": "conversations"}, {"label": "About this computer", "say": "about this computer"}]},
                {"type": "heading", "text": L("s_autonomy")},
                {"type": "choices", "selected": L("v_" + auto), "items": [
                    {"label": L("v_hands-off"), "say": "switch to hands-off mode"},
                    {"label": L("v_balanced"), "say": "switch to balanced mode"},
                    {"label": L("v_hands-on"), "say": "switch to hands-on mode"}]},
                {"type": "toggle", "label": L("s_guard_untrusted"), "hint": L("s_guard_untrusted_hint"),
                 "on": bool(s.get("guard_untrusted", True)), "say_on": "turn on the web page check",
                 "say_off": "turn off the web page check"},
                {"type": "heading", "text": L("s_internet")},
                {"type": "choices", "selected": L("v_" + {"yes": "yes", "ask": "ask", "no": "no"}[s["internet"]]), "items": [
                    pick("v_yes", "allow internet use"), pick("v_ask", "ask me each time before using the internet"),
                    pick("v_no", "turn the internet off")]},
                {"type": "toggle", "label": L("s_tor"), "on": bool(s.get("tor")), "say_on": "route the internet through tor",
                 "say_off": "stop using tor"},
                {"type": "heading", "text": L("s_brain")},
                {"type": "choices", "selected": L("v_brain_" + (s.get("brain") if s.get("brain") in ("local", "ask", "cloud") else "local")), "items": [
                    {"label": L("v_brain_local"), "say": "think only on this computer"},
                    {"label": L("v_brain_ask"), "say": "ask me before going online for big tasks"},
                    {"label": L("v_brain_cloud"), "say": "use the online model for everything"}]},
                {"type": "kv", "rows": [[L("s_online_model"), llm.cloud_label() or L("v_not_set_up")]]},
                {"type": "buttons", "items": [{"label": L("d_cloud_setup"), "say": "set up the online model"}] +
                 ([{"label": L("d_forget"), "say": "forget the online model", "danger": True}] if config.cloud() else [])},
                {"type": "heading", "text": L("s_guidance")},
                {"type": "choices", "selected": L("v_guidance_standard") if s.get("guidance") == "standard" else L("v_guidance_owner"),
                 "items": [{"label": L("v_guidance_owner"), "say": "follow my instructions on my machine"},
                           {"label": L("v_guidance_standard"), "say": "keep standard assistant caution"}]},
                {"type": "heading", "text": L("s_conduct")},
                {"type": "text", "text": L("s_conduct_desc") + " " + (L("v_conduct_custom") if agent.custom_conduct() else L("v_conduct_default")), "dim": True},
                {"type": "buttons", "items": [{"label": L("d_conduct_edit"), "say": "edit the conduct"}] +
                 ([{"label": L("d_conduct_reset_btn"), "say": "reset the conduct to the default", "danger": True}] if agent.custom_conduct() else [])},
                {"type": "divider"},
                {"type": "kv", "rows": [
                    [L("s_model"), (models.active() or {}).get("name", "—") + (" · host GPU" if models.host_mode() else "")],
                    [L("s_timezone"), system.timezone()],
                    [L("s_language"), s["language"]] + ([] if not s["settings_language"] else []),
                    [L("s_settings_language"), s["settings_language"] or L("v_default")],
                    [L("s_color"), s["appearance"]["color"] or L("v_default")],
                    [L("s_background"), s["appearance"]["background"] or L("v_default")],
                    [L("s_accent"), s["appearance"]["accent"] or L("v_default")],
                    [L("s_version"), version_line()]]},
                {"type": "heading", "text": L("s_language")},
                {"type": "choices", "selected": i18n.display_name(s["language"]), "items": [
                    {"label": i18n.display_name(c), "say": f"put everything in {i18n.display_name(c)}"} for c in ("en", "zh", "es", "fr", "de", "ja")]},
                {"type": "heading", "text": L("s_presets")},
                {"type": "buttons", "items": [{"label": T("d_th_dark"), "say": "dark mode"}, {"label": T("d_th_light"), "say": "light mode"},
                                              {"label": L("c_purple"), "say": "make everything purple"}, {"label": L("c_teal"), "say": "make everything teal"},
                                              {"label": L("c_orange"), "say": "make everything orange"}, {"label": L("c_green"), "say": "make everything green"},
                                              {"label": "Ocean", "say": "ocean theme"}, {"label": "Neon", "say": "neon theme"},
                                              {"label": "Retro", "say": "retro theme"}, {"label": "Space", "say": "space theme"},
                                              {"label": T("d_th_contrast"), "say": "high contrast mode"},
                                              {"label": L("v_default"), "say": "default theme"}]},
                {"type": "heading", "text": T("d_font")},
                {"type": "choices", "selected": {"sans": "Sans", "serif": "Serif", "mono": "Mono", "pixel": "Pixel"}.get(s["appearance"].get("font") or "sans", "Sans"),
                 "items": [{"label": "Sans", "say": "change the font to sans"}, {"label": "Serif", "say": "change the font to serif"},
                           {"label": "Mono", "say": "change the font to mono"}, {"label": "Pixel", "say": "change the font to pixel"}]},
                {"type": "heading", "text": T("d_backdrop")},
                {"type": "choices", "selected": T("d_bd_" + (s["appearance"].get("backdrop") or "living")),
                 "items": [{"label": T("d_bd_living"), "say": "animated background"}, {"label": T("d_bd_still"), "say": "still background"},
                           {"label": T("d_bd_plain"), "say": "plain background"}] +
                          ([{"label": T("d_bd_photo"), "say": "make the background photo"}] if os.path.exists(_wallpaper()) else [])},
                {"type": "heading", "text": L("s_corners")},
                {"type": "choices", "selected": L("v_" + s["appearance"]["corners"]) if s["appearance"]["corners"] in ("rounded", "square", "none") else s["appearance"]["corners"],
                 "items": [pick("v_rounded", "rounded corners"), pick("v_square", "square corners"), pick("v_none", "no corners")]},
                {"type": "heading", "text": L("s_size")},
                {"type": "buttons", "items": [{"label": "A−", "say": "make everything smaller"}, {"label": "A+", "say": "make everything bigger"},
                                              {"label": f"{s['appearance'].get('scale', 100)}%", "say": "normal text size"}]},
                {"type": "heading", "text": L("s_layout")},
                {"type": "choices", "selected": L("v_layout_" + (s["appearance"].get("layout") if s["appearance"].get("layout") in ("clean", "windows", "mac") else "clean")),
                 "items": [{"label": L("v_layout_clean"), "say": "give me a clean desk"}, {"label": L("v_layout_windows"), "say": "give me a windows style desk"},
                           {"label": L("v_layout_mac"), "say": "give me a mac style desk"}]},
                {"type": "heading", "text": L("s_motion")},
                {"type": "choices", "selected": L("v_motion_" + (s["appearance"].get("motion") or "full")),
                 "items": [{"label": L("v_motion_full"), "say": "turn animations on"}, {"label": L("v_motion_reduced"), "say": "fewer animations"},
                           {"label": L("v_motion_off"), "say": "turn animations off"}]},
                {"type": "toggle", "label": L("s_voice"), "on": bool(s.get("speak_replies")), "say_on": "read your replies aloud",
                 "say_off": "stop reading replies aloud"},
                {"type": "toggle", "label": L("s_focus"), "on": bool(s.get("focus", {}).get("on")), "say_on": "turn on focus mode",
                 "say_off": "turn off focus mode"},
                {"type": "kv", "rows": [[L("s_vault"), L("v_on") if s.get("vault") else L("v_off")]]},
            ] + ([
                {"type": "heading", "text": L("s_autolock")},
                {"type": "choices", "selected": (L("v_minutes", n=int(s.get("autolock") or 0)) if int(s.get("autolock") or 0) else L("v_never")),
                 "items": [{"label": L("v_never"), "say": "turn off auto-lock"}] +
                          [{"label": L("v_minutes", n=n), "say": f"lock after {n} minutes of inactivity"} for n in (5, 15, 60)]},
            ] if s.get("vault") else []) + [
                {"type": "text", "text": L("s_change_hint"), "dim": True},
            ]
            return {"title": L("settings"), "kind": "panel", "size": "m", "blocks": blocks}
        if which == "models":
            return self.models_panel()
        if which == "connectors":
            return self.connectors_panel()
        if which == "tasks":
            ts = store.tasks()
            items = [{"title": t["task"], "subtitle": t["desc"], "id": t["id"],
                      "actions": [{"label": T("d_cancel"), "say": f"cancel the task {t['id']}", "danger": True}]} for t in ts]
            if not items:
                return uispec.text_window(T("tasks"), T("no_tasks"))
            return uispec.list_window(T("tasks"), items)
        if which == "memory":
            facts = store.facts()
            items = [{"title": f["fact"], "meta": f.get("added", ""),
                      "actions": [{"label": T("d_forget"), "say": f"forget that {f['fact']}", "danger": True}]} for f in facts]
            if not items:
                return uispec.text_window(T("memory"), T("no_memory"))
            return uispec.list_window(T("memory"), items)
        if which == "audit":
            rows = [[r["ts"][11:], ("" if r["allowed"] else "✗ ") + r["tool"], ui.strip(str(r["result"]))[:90]]
                    for r in store.audit_tail(25)]
            if not rows:
                return uispec.text_window(T("audit"), T("no_audit"))
            return {"title": T("audit"), "kind": "panel", "size": "l",
                    "blocks": [{"type": "table", "columns": ["", "", ""], "rows": rows}]}
        if which == "help":
            examples = [T(f"g_ex{i}") for i in (11, 12, 1, 2, 13, 3, 4, 5, 9, 10, 14, 7)]
            return {"title": T("d_try"), "kind": "panel", "size": "l", "blocks": [
                {"type": "text", "text": T("g_intro")},
                {"type": "buttons", "items": [{"label": T("settings", area="settings"), "say": "settings"},
                                              {"label": T("models"), "say": "models"}, {"label": T("tasks"), "say": "tasks"},
                                              {"label": T("memory"), "say": "memory"}, {"label": T("d_lists"), "say": "show my lists"},
                                              {"label": T("d_myapps"), "say": "show my apps"}, {"label": T("d_conversations"), "say": "conversations"},
                                              {"label": T("d_network"), "say": "network"}, {"label": T("d_sound"), "say": "sound"},
                                              {"label": T("audit"), "say": "audit"}]},
                {"type": "list", "columns": 2, "items": [{"title": f"“{e}”", "actions": [{"label": T("d_try_btn"), "say": e}]} for e in examples]},
                {"type": "text", "text": T("d_shortcuts"), "dim": True}]}
        return None

    def show_away(self, force=False):
        """Show the unseen items as the card. Do not disturb holds the card back too: nothing is opened or
        recorded, so the first call after do-not-disturb is off shows it. force=True (an explicit owner
        request) shows the card anyway; the toast, chime and speech are still silenced under do-not-disturb."""
        dnd = bool(config.settings.get("do_not_disturb")) and not force
        try:
            st = os.stat(config.data("inbox.json"))
            key = (st.st_mtime_ns, st.st_size)
        except OSError:
            key = None
        if key == getattr(self, "_inbox_key", "unset") and not force:
            return
        if dnd:
            return
        self._inbox_key = key
        un = store.unseen()
        if not un:
            return
        items = [{"title": m["title"], "detail": ui.strip(m["text"])[:1200]} for m in un[-8:]]
        self.open_window({"id": "away", "replace": True, "title": T("while_away"), "size": "m", "slot": "cascade",
                          "blocks": [{"type": "list", "items": items}]})
        self.away_ids = [m["id"] for m in un]          # marked seen when the owner closes the card
        if getattr(self, "ready", False) and not config.settings.get("do_not_disturb"):     # (do not disturb: the card only, no toast, chime or speech)
            self.emit({"t": "toast", "text": ui.strip(un[-1]["text"])[:120] or un[-1]["title"], "long": True})
            devices.chime()
            if config.settings.get("speak_replies"):
                self.ctx.background(lambda t=ui.strip(un[-1]["text"])[:400]: voice.speak(t))

    def sleep_now(self):
        """Sleep; with a passphrase the screen locks first, so waking needs it (as on any PC)."""
        if config.settings.get("vault") and vault.unlocked() and self.screen == "desk":
            try:
                self.lock()
            except Exception as e:
                sys.stderr.write(f"desk: lock before sleep failed: {e}\n")
            time.sleep(1.5)
        syspanels.sleep()

    def _poll_power(self):
        """Every 5 s: a laptop's lid closed sleeps it; a nearly empty battery warns, then sleeps before it dies."""
        try:
            lid = ""
            for f in glob.glob("/proc/acpi/button/lid/*/state"):
                with open(f) as fh:
                    lid = fh.read().split()[-1]
            was, self._lid = getattr(self, "_lid", lid), lid
            if lid == "closed" and was == "open" and config.settings.get("lid", "sleep") == "sleep" and not self._external_screen():
                threading.Thread(target=self.sleep_now, daemon=True).start()
            b = _battery()
            if b and not b["charging"]:
                warned = getattr(self, "_low_warned", 100)
                if b["pct"] <= 3 and warned > 3:
                    self._low_warned = 3
                    self.emit({"t": "toast", "text": "The battery is empty: going to sleep now. Plug in the charger.", "long": True})
                    threading.Thread(target=lambda: (time.sleep(8), self.sleep_now()), daemon=True).start()
                elif b["pct"] <= 10 and warned > 10:
                    self._low_warned = 10
                    self.emit({"t": "toast", "text": f"The battery is low ({b['pct']}%). Plug in the charger soon.", "long": True})
            elif b:
                self._low_warned = 100
        except Exception as e:
            sys.stderr.write(f"desk: power check failed: {e}\n")
        return True

    def _external_screen(self):
        """A second screen is connected (closing the lid then keeps working, like a docked laptop)."""
        try:
            return sum(1 for d in glob.glob("/sys/class/drm/card*-*/status") if open(d).read().strip() == "connected") > 1
        except OSError:
            return False

    def start_idle(self):
        """The screen turns off after some minutes without use (settings: screen_off, default 10; 0 = never) and
        wakes at a touch; optionally the computer sleeps later (sleep_after). swayidle watches; wlopm switches."""
        subprocess.run(["pkill", "-x", "swayidle"], capture_output=True)
        if not shutil.which("swayidle"):
            return
        off = int(config.settings.get("screen_off", 10) or 0)
        nap = int(config.settings.get("sleep_after", 0) or 0)
        argv = ["swayidle"]
        if off > 0 and shutil.which("wlopm"):
            argv += ["timeout", str(off * 60), "wlopm --off '*'", "resume", "wlopm --on '*'"]
        if nap > 0:
            argv += ["timeout", str(nap * 60), "/usr/bin/llmos desk-ctl act 'sleep'"]
        if len(argv) == 1:
            return
        try:
            subprocess.Popen(argv, env=dict(os.environ, **(media.desk_env() or {})), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            pass

    def _poll_autolock(self):
        """Lock the vault by itself after the owner's chosen idle time (settings: autolock minutes).
        Programs the owner opened and anything playing count as activity: input there never reaches this page."""
        try:
            idle = time.time() - getattr(self, "last_active", time.time())
            mins = int(config.settings.get("autolock") or 0)
            if mins > 0 and idle > mins * 60 and self.screen == "desk" and not self.busy and not self.apps \
                    and not media.playing() and config.settings.get("vault") and vault.unlocked():
                threading.Thread(target=self.lock, daemon=True).start()
        except Exception as e:
            sys.stderr.write(f"desk: autolock check failed: {e}\n")
        return True

    def _poll_away(self):
        """Every 20 s: background results to show; and if another session
        (the text console) finished onboarding or unlocked the vault while
        this screen was waiting, move on."""
        try:
            if self.screen == "desk" and not self.busy:
                self.show_away()
            elif self.screen == "wizard" and config.settings.get("onboarded"):
                self.enter_desk()
            elif self.screen == "lock" and vault.unlocked() and not getattr(self, "lock_stuck", False):
                self._keybinds(True)
                self.enter_desk()   # another session (the console) opened the vault
            if self.screen == "desk" and config.settings.get("vault") and not vault.unlocked():
                threading.Thread(target=self.lock, daemon=True).start()   # ... or locked it: this screen must not stay open
        except Exception:
            pass
        return True

    # ---- dialogs (blocking for the worker thread)

    DIALOG_TIMEOUT = 600   # an unanswered confirmation counts as "no" after 10 minutes

    def ask(self, spec, consent=False):
        if self.ctx.cancel.is_set():      # the owner pressed Stop: nothing more is allowed this turn
            return False
        if config.settings.get("autonomy") == "hands-off" and not consent:
            return True                   # full trust: the owner agreed to everything in advance; nothing is asked
        self.dialog_seq += 1
        did = f"d{self.dialog_seq}"
        ev = threading.Event()
        self.dialogs[did] = [ev, None, spec.get("title", ""), spec.get("text", "")]
        self.emit({"t": "dialog", "id": did, "title": spec.get("title", ""), "text": spec.get("text", ""),
                   "danger": bool(spec.get("danger")), "mono": bool(spec.get("mono")),
                   "buttons": [{"label": spec.get("yes") or T("allow"), "value": "yes", "primary": True},
                               {"label": spec.get("no") or T("d_dont"), "value": "no"}]})
        answered = ev.wait(self.DIALOG_TIMEOUT)
        val = self.dialogs.pop(did, [None, None])[1]
        if not answered:
            self.emit({"t": "dialog.close", "id": did})
            self.emit({"t": "toast", "text": T("skipped")})
        return val == "yes"

    def decline_dialogs(self):
        for did, d in list(self.dialogs.items()):
            d[1] = "no"
            d[0].set()
            self.emit({"t": "dialog.close", "id": did})

    def describe_tool(self, tool, args, confirm=False):
        n = tool.name
        a = args if isinstance(args, dict) else {}
        if n == "run_command":
            return ("Run this command?" if confirm else "run: " + str(a.get("command", ""))[:120])
        if n == "install_app":
            return ("Install software?" if confirm else "install " + str(a.get("packages", "")))
        if n == "write_file":
            return (f"Write to {a.get('path', '')}?" if confirm else f"write {a.get('path', '')}")
        if n == "web_search":
            return "search the web: " + str(a.get("query", ""))
        if n == "read_webpage":
            return "read " + str(a.get("url", ""))[:100]
        if n == "manage_models":
            return f"models: {a.get('action', '')} {a.get('model', '')}"
        if n == "system_power":
            return f"{a.get('action', '')} the computer?" if confirm else f"{a.get('action', '')}…"
        if n == "change_setting":
            return (f"Switch {a.get('setting', '')} to {a.get('value', '')}?" if confirm
                    else f"change {a.get('setting', '')} → {a.get('value', '')}")
        if n == "delete_file":
            return (f"Move {os.path.basename(str(a.get('path', '')).rstrip('/'))} to the trash?" if confirm
                    else f"trash {a.get('path', '')}")
        if n == "open_file":
            return f"open {os.path.basename(str(a.get('path', '')))}"
        if n == "show_files":
            return f"files: {a.get('path', '') or '~'}"
        if n == "screenshot":
            return "take a screenshot"
        if n == "note_add":
            return f"add to the {a.get('list') or 'notes'} list: {str(a.get('text', ''))[:60]}"
        if n == "notes_show":
            return f"show the {a.get('list') or 'lists'}"
        if n == "note_done":
            return f"tick off: {str(a.get('item', ''))[:60]}" if a.get("done", True) is not False else f"un-tick: {str(a.get('item', ''))[:60]}"
        if n == "note_remove":
            return f"remove from the list: {str(a.get('item', ''))[:60]}"
        if n == "restore_file":
            return f"restore from the trash: {a.get('name', '')}"
        if n == "empty_trash":
            return "Empty the trash?" if confirm else "empty the trash"
        if n == "set_passphrase":
            return "set up a passphrase"
        if n in ("set_brightness", "set_volume"):
            what = "brightness" if n == "set_brightness" else "volume"
            if a.get("percent") is not None:
                return f"{what}: {a.get('percent')}%"
            if a.get("delta") is not None:
                d = str(a.get("delta"))
                return f"{what} {'+' if not d.startswith(('+', '-')) else ''}{d}"
            return f"{what}: {'mute' if a.get('mute') else 'unmute'}"
        if n == "set_appearance":
            return "change the look"
        if n == "make_app":
            return f"make an app: {a.get('what', '')}" + (f" ({a.get('look')})" if a.get("look") else "")
        if n == "open_app":
            return f"open {a.get('command', '')}"
        if n == "manage_apps":
            return "Remove the app " + str(a.get("name", "")) + "?" if confirm and a.get("action") == "remove" else f"apps: {a.get('action', 'list')}"
        if n == "online_model":
            act = str(a.get("action", "")).lower()
            who = {"claude": "Claude", "anthropic": "Claude", "chatgpt": "ChatGPT", "openai": "ChatGPT"}.get(str(a.get("provider", "")).lower(), "")
            if act in ("sign in", "signin", "log in", "login"):
                return f"sign in to {who or 'an online model'}"
            if act == "forget":
                return "Forget the online model?" if confirm else "forget the online model"
            if act in ("use", "switch", "select"):
                return f"online model: {a.get('model', '')}"
            if act in ("set up", "setup", "add", "configure", "change", "replace"):
                return "Connect an online model?" if confirm else "connect an online model"
            return "the online model"
        if n == "play_media":
            return "play: " + str(a.get("query", ""))
        if n.startswith("mail_"):
            what = n[5:]
            ref = a.get("id") or a.get("ids") or a.get("to") or a.get("address") or ""
            return (f"{'Send' if what in ('send', 'reply') else what.capitalize()} email {ref}?".replace("  ", " ") if confirm
                    else f"email: {what} {ref}".strip())
        if n in ("show_screen", "show_panel", "show_image", "real_quote", "calculate", "remember", "forget", "schedule_task"):
            key = next((k for k in ("panel", "subject", "who_or_topic", "expression", "fact", "what", "task", "title") if a.get(k)), None)
            return f"{n.replace('_', ' ')}: {str(a.get(key, ''))[:70]}" if key else n.replace("_", " ")
        # never raw arguments: the tool's own first words ("Ask the owner which file…") read as plain language
        what = re.split(r"[.:(]", (getattr(tool, "description", "") or n.replace("_", " ")))[0].strip()
        what = what[:70] + ("…" if len(what) > 70 else "")
        return (f"{what}?" if confirm else what)

    def describe_args(self, tool, args):
        a = args if isinstance(args, dict) else {}
        if tool.name == "run_command":
            return str(a.get("command", ""))
        if tool.name == "install_app":
            return str(a.get("packages", ""))
        if tool.name == "change_setting":
            return ("This lets me do more without asking first." if a.get("setting") == "autonomy"
                    else "This loosens a limit you set." if a.get("setting") in ("internet", "tor") else f"{a.get('setting', '')}: {a.get('value', '')}")
        if tool.name in ("delete_file", "open_file", "show_files"):
            return str(a.get("path", "")) + ("" if tool.name != "delete_file" else " → ~/.Trash (it can be put back)")
        # plain "key: value" lines, never raw JSON
        s = "\n".join(f"{k}: {v}" for k, v in a.items() if v not in ("", None)) or "(no details)"
        return s if len(s) < 300 else s[:297] + "…"

    # ---- requests

    def say(self, text, done=None, chat="main"):
        """Queue a request; `done` (an Event) is set when its turn is over. While the model is still working on an
        earlier one, something the OS does by itself (open the settings, show the lists, dark mode…) is done at once
        instead of waiting behind it."""
        text = intent.fix_typos(text.strip())
        if not text:
            if done:
                done.set()
            return
        self.last_active = time.time()
        if chat == "main" and self.busy and self._instant(text):
            def now():
                queued = False
                try:
                    queued = self.act(text, done)
                finally:
                    if done and not queued:       # act queued it: the worker sets done when that turn ends
                        done.set()
            threading.Thread(target=now, daemon=True).start()
            return
        self._enqueue(text, done, chat)

    def _enqueue(self, text, done, chat):
        qid = uuid.uuid4().hex[:8]
        with self._pending_lock:
            self._req_pending += 1
            waiting = self.busy or not getattr(self.requests, "empty", lambda: True)()
            if chat == "main":
                self.__dict__.setdefault("_waiting", []).append({"id": qid, "text": text[:160]})
        self.requests.put((text, done, chat, qid))
        if chat == "main" and waiting:
            self.emit({"t": "toast", "text": T("d_queued")})
        self._emit_queue()

    def _emit_queue(self):
        """The requests waiting their turn, in order, for the desk's queue strip (each can be removed)."""
        with self._pending_lock:
            items = [dict(w) for w in self.__dict__.get("_waiting", [])]
        self.emit({"t": "queue", "items": items})

    def drop_queued(self, qid):
        with self._pending_lock:
            if any(w["id"] == qid for w in self._waiting):
                self._dropped.add(qid)
                self._waiting = [w for w in self._waiting if w["id"] != qid]
        self._emit_queue()

    # tools that finish at once and need no model: safe to run beside a request in progress
    _SLOW = {"web_answer", "make_list", "install_app", "manage_models", "find_by_meaning", "edit_images", "convert_media", "web_search", "read_webpage", "show_image", "set_wallpaper", "install_to_disk",
             "play_media", "check_new_models", "add_model", "manage_voice", "wifi_scan", "wifi_connect", "run_command"}

    _QUICK = {"settings", "models", "tasks", "memory", "audit", "help", "connectors", "?", "lock", "voice", "listen", "clear",
              "close the live window", "keep trying it", "network", "wifi", "wi-fi", "internet", "show wifi networks",
              "show the wifi networks", "wifi networks", "connect to wifi", "connect to wi-fi", "network settings",
              "show the network settings", "sound", "volume", "sound settings", "audio", "power", "power options", "power menu",
              "history", "conversations", "my conversations", "show my conversations", "chat history", "show the history",
              "show my chats", "chats", "sessions"}
    _QUICK_RE = re.compile(r"(?:what can you do|what can i (?:do|say|ask)(?: here| with (?:this|it|you))?|how do i use (?:this|you|it)|what do i do|help me|show me what you can do|"
                           r"what are you|what is this|get started|getting started|\?+)[?.!]*|(?:stop|cancel|never ?mind|forget it|abort|halt that|stop that|stop it|cancel that|no stop)[.!]*|(?:please )?close (?:all (?:the |my |of the )?(?:windows|apps)|everything|all of them|every window)(?: please)?[.!]?|"
                           r"(?:join wifi |continue topic |forget topic |open side chat |delete side chat ).+|"
                           r"(?:new (?:topic|chat|conversation)|start (?:fresh|over|a new (?:topic|chat|conversation))|fresh start|"
                           r"clear (?:the )?chat|forget this conversation|change the subject)[.!]?|"
                           r"(?:new |start a |open a |start a new |open a new )?side ?chat(?:\s+(?:about|on|for)\s+.+)?[.!]?")

    def _instant(self, text):
        low = intent.plain(text).lower().strip()
        if intent.is_chain(low):
            return False                  # several steps that build on each other: the model does them together
        if self._app_question(low) is not None:
            return True                   # close or read an open app of the OS's own: done now, even while the model works
        if low in self._QUICK or low in _LOCK_WORDS or self._QUICK_RE.fullmatch(low) or everyday.MATCH.search(low) or _MEDIUM_Q.search(low) or _TIME_Q.fullmatch(low) or _BATTERY_Q.fullmatch(low) or re.search(r"\b(?:font|typeface)\b", low) or re.search(r"\b(?:magnif\w*|keyboard)\b", low) or re.search(r"\b(?:games?|bored)\b", low) or re.match(r"close window \S+$|(?:switch to|close) [\w.-]+$", low) or re.search(r"\b(?:root|sudo|admin|firewall|virus|viruses|malware|antivirus|permissions?|dual[- ]?boot|boot|crash\w*|captions|subtitles|dock|taskbar|default|button|drive|open right now|what'?s open|popped up|side by side|split screen|battery|history|conversations?|what did you)\b", low) or re.search(r"\bip\b", low) or re.search(r"\b(?:unsaved|forgot to save|didn'?t save|(?:from|off(?: of)?) (?:my |the )?(?:phone|camera|iphone|android))\b|\brepo(?:sitory)?\b|\b(?:reset|factory|like new|erase everything)\b|\b(?:lock|encrypt|password|protect|secure)\b.*\bfolder\b|^(?:unlock|decrypt) \w|\b(?:lock|encrypt|password[- ]?protect) (?:my )?(?:documents|pictures|photos|music|videos|downloads|desktop)\b|\bbookmarks?\b|\bblur\b|\b(?:users?|accounts?|profile|login|guest)\b|plug in (?:my )?phone|connect (?:my )?(?:phone|iphone)", low) or re.search(r"\brecord|recording\b|voice (?:memo|note)", low) or re.fullmatch(r"forget (?:this|the current|my|the) (?:wi-?fi|network|wi-?fi network)", low.rstrip(".!")) or re.search(r"\bspell|\bscan\b", low) or re.search(r"\bshare (?:my |the )?screen|screen ?shar|fill (?:in|out) .*pdf|sign .*pdf", low) or re.search(r"\b(?:pdf|password|passwords|translate|safe|legit|scam)\b", low) or re.match(r"(?:please )?(?:set ?up|add|connect|configure|sign in to|log ?in to)(?: my)? e-?mail", low) or re.search(r"\b(?:website|site|page)s?\b.*\b(?:load|work|open|broken)", low) or re.search(r"\b(?:zoom (?:in|out)|bookmark|ads|adverts|pop-?ups|ad ?blocker|history)\b|bigger on (?:this|the)|smaller on (?:this|the)", low) or low in ("switch to hands-off mode", "switch to balanced mode", "switch to hands-on mode", "follow my instructions on my machine", "keep standard assistant caution") or re.match(r"use sound (?:output|input) \d+", low) or re.search(r"\b(?:presentation|slides|slideshow|powerpoint)\b", low) or re.match(r"(?:my email is|i use) ", low) or re.search(r"\b(?:workspace|virtual desktop)\b", low) or re.match(r"how (?:do|can|to) |where (?:are|do|is) my|what(?:'s| is)? (?:the )?(?:keyboard )?shortcut|keyboard shortcuts|privacy|is (?:this|it|my data) private|(?:do|does|are) you (?:spy|track|send|collect|record|listen)|what (?:data |information )?(?:do|does|will) (?:you|it|this)|(?:the )?(?:model|ai|you|wi-?fi|internet)\b.*(?:respond|answer|work|stuck|frozen|down|connect)|are you there|no (?:internet|wi-?fi)|headphones", low) or re.fullmatch(r"(?:please )?(?:close|hide|dismiss) (?:this|it|that)(?: \w+)?|close the window", low.rstrip("?.!")) or re.search(r"\b(?:read (?:this|that|it)|aloud|out loud|dictat|type what i say|can'?t (?:see|read|hear)|too small|hard to (?:see|read)|wrong (?:time|clock|speaker)|time is wrong|clock is wrong|no sound|wallpaper|background)\b", low) or re.match(r"(?:please )?(?:save|keep) (?:it|this|that|the \w+)\b", low) or re.search(r"(?:airplane|aeroplane|flight) mode|^forget (?:the )?wi-?fi|^disconnect (?:from )?(?:the )?wi-?fi", low) or re.fullmatch(r"(?:pause|resume|unpause|play ?pause)[.!]?", low) or re.fullmatch(r"(?:it says )?(?:(?:the )?(?:wi-?fi|network) )?connected(?: to (?:the |my )?(?:wi-?fi|network|internet))?,? (?:but|yet|and)(?: (?:there'?s|there is|it'?s|it is|nothing))? (?:no internet|not online|nothing loads)", low.rstrip("?.!")) or _CLIP_Q.fullmatch(low) or _DEV_Q.fullmatch(low) or \
                any(rx.fullmatch(low) for rx, _ in self._SYS) or any(rx.fullmatch(low.rstrip("?.!")) for rx, _ in self._CANON) or \
                any(rx.fullmatch(low.rstrip("?.!")) for rx in (self._ROTATE, self._RES, self._EJECT, self._DESKTOP, self._TILE, self._TILE2)) or (shutil.which("wlrctl") and self._WIN.fullmatch(low.rstrip(".!?"))) or re.fullmatch(r"(?:end process \d+|(?:open|eject) drive /dev/\S+|"
                                                                            r"(?:extend|mirror) the displays|use only the main display|use only the (?:projector|tv|second (?:screen|display))|projector only|"
                                                                            r"bluetooth (?:on|off|search|connect|disconnect|forget)(?: [0-9a-f:]{17})?|add printer \S+|print a test page on \S+|make \S+ the default printer|"
                                                                            r"(?:natural scrolling|tap to click|left handed mouse) (?:on|off)|mouse (?:faster|slower|normal speed)|"
                                                                            r"key repeat (?:faster|slower|normal)|set resolution \S+ \d+x\d+|"
                                                                            r"(?:sleep|suspend|go to sleep|put (?:it|the computer) to sleep|hibernate)[.!]?|clear (?:the )?caches?[.!]?|install (?:the |all (?:the )?)?updates[.!]?|"
                                                                            r"add (?:the |an? )?[a-z]+ layout|(?:this |my |the )?(?:app|program)(?: is frozen| froze| stopped responding)|(?:keyboard layout|use an? |switch (?:the )?keyboard to|change (?:the )?keyboard (?:layout )?to )[a-z ()-]+)", low):
            return True
        if self._howto(low.rstrip("?.!")) is not None:
            return True                   # a how-to the desk answers from its own table: no model needed
        m = intent.match(text)
        return bool(m) and m[0] not in self._SLOW and not m[0].startswith("mail_")

    def act(self, text, done=None):
        """A button on the desk (a status chip, the dock, the start menu, a window's button): done straight away on
        its own thread, never queued behind a request the model is still thinking about. What the OS cannot do by
        itself goes to the model like anything typed. Returns True when it queued the text (the worker sets `done`)."""
        text = str(text or "").strip()
        if not text:
            return False
        self.last_active = time.time()
        mm = re.fullmatch(r"(download|use|remove) the model ([\w.+-]+)", text, re.I)
        if mm:                                  # the models page's own buttons: on their own thread, at once, never
            threading.Thread(target=self._model_button, args=(text, mm.group(1).lower(), mm.group(2)),  # behind the model
                             daemon=True).start()
            return False
        if not self._instant(text):
            self._enqueue(intent.fix_typos(text), done, "main")
            return True
        try:
            if self.shortcut(text):
                self.last_reply = self.__dict__.pop("_said", None) or "Done."
                getattr(self, "refresh_windows", lambda: None)()
                getattr(self, "push_status", lambda: None)()
                return False
            m = intent.match(text)
            if not m:
                self._enqueue(intent.fix_typos(text), done, "main")   # looked instant, but needs the model after all
                return True
            name, args = m

            class Lane:                     # the desk's context, with this button's words as "the request"
                def __init__(lane, ctx):
                    lane._ctx, lane.current_request = ctx, text

                def __getattr__(lane, k):
                    return getattr(lane._ctx, k)
            lane = Lane(self.ctx)
            out = agent.execute(lane, name, args)
            if lane.__dict__.get("after_turn"):    # system_power sets it on the lane object, not on the desk's context
                self.ctx.after_turn = lane.__dict__["after_turn"]
            if str(out).startswith(agent._NOT_AN_APP):
                self._enqueue(intent.fix_typos(text), done, "main")   # words, not an app: the model writes them
                return True
            reply = agent._cap(agent._shortcut_reply(name, args, out))
            self.last_reply = reply
            if reply and reply not in ("Here it is.", "(done)"):
                self.emit({"t": "toast", "text": reply[:240]})
        except Exception as e:
            self.emit({"t": "toast", "text": agent._plain_error(str(e))})
        how = getattr(getattr(self, "ctx", None), "after_turn", None)   # a button that restarts or shuts down (system_power): do it now, as
        if how:                                 # a typed request does after its reply; before this, nothing happened
            self.ctx.after_turn = None
            self.shutdown(how)
        return False

    def _model_button(self, text, action, mid):
        """Download / use / remove a model from its button: feedback at once, the result as a toast, the page refreshed."""
        self.emit({"t": "toast", "text": {"download": f"Downloading {mid}… (progress shows below)",
                                          "use": f"Switching to {mid}…", "remove": f"Removing {mid}…"}[action]})

        class Lane:                             # the desk's context, with this button's words as "the request"
            def __init__(lane, ctx):
                lane._ctx, lane.current_request = ctx, text

            def __getattr__(lane, k):
                return getattr(lane._ctx, k)
        args = {"action": action, "model": mid}
        try:
            out = agent.execute(Lane(self.ctx), "manage_models", args)
            reply = agent._cap(agent._shortcut_reply("manage_models", args, out))
        except Exception as e:
            reply = agent._plain_error(str(e))
        self.emit({"t": "toast", "text": (reply or "Done.")[:240]})
        if "panel-models" in self.windows:
            try:
                self.open_panel("models")       # the page shows the new state (downloaded, in use, removed)
            except Exception:
                pass

    def _worker(self):
        while True:
            item = self.requests.get()
            text, done, chat = (item + ("main",))[:3] if len(item) == 2 else item[:3]
            qid = item[3] if len(item) > 3 else None
            with self._pending_lock:
                skip = qid in self._dropped
                self._dropped.discard(qid)
                self._waiting = [w for w in self._waiting if w["id"] != qid]
            self._emit_queue()
            try:
                if skip:                    # the owner removed it from the queue: it never runs
                    continue
                self.turn(text, chat)
            except Exception as e:      # never let the worker die
                self.emit({"t": "reply.error", "text": agent._plain_error(str(e))})
            finally:
                with self._pending_lock:
                    self._req_pending = max(0, self._req_pending - 1)
                    self._req_done += 1
                self.turn_done.set()
                if done:
                    done.set()

    def _app_question(self, low):
        """'close the calculator' / 'what does the calculator show' for an app of the OS's own that is installed:
        (kind, app, window id or None when it is not open). None for anything else."""
        q = intent.app_question(low)
        if not q:
            return None
        from . import apps
        a = apps.find(q[1])
        if not a:
            return None
        wid = "app-" + a["id"]
        return q[0], a, (wid if wid in self.windows else None)

    def shortcut(self, line):
        line = intent.plain(line)
        low = line.lower().strip()
        if low in ("settings", "models", "tasks", "memory", "audit", "help", "connectors", "?"):
            if low in ("help", "?"):
                self._said = "Type what you want. F1 talks. Esc closes the window."
            self.open_panel("help" if low == "?" else low)
            return True
        if re.fullmatch(r"(?:please )?close (?:all (?:the |my |of the )?(?:windows|apps)|everything|all of them|every window)(?: please)?[.!]?", low):
            for wid in list(self.windows):
                self.close_window(wid)
            self.emit({"t": "clear"})
            return True
        if re.fullmatch(r"what(?: did|'d|’d) i miss|anything new|any notifications|show my notifications|what happened while i was away|while i was away", low.rstrip("?.! ")):
            if not store.unseen():      # the same test show_away makes: nothing unseen, nothing to show
                self.instant_reply(line, "Nothing new since you last looked.")
            else:
                self.show_away(force=True)      # an explicit owner request: the card opens even under do-not-disturb
            return True
        # the video / music player: full screen, back, close (before "close <program>", which did not know it)
        if media.playing():
            q = low.rstrip("?.! ")
            if re.fullmatch(r"(?:make\s+|put\s+|turn\s+|go\s+|watch\s+)?(?:the\s+|this\s+|my\s+)?(?:video|movie|player)?\s*(?:in\s+|to\s+)?(?:full ?screen)(?:\s+(?:the\s+)?(?:video|player|mode))?|(?:make|put)\s+(?:it|the video|this)\s+(?:bigger|full ?screen)|maximi[sz]e\s+(?:the\s+)?(?:video|player)", q):
                media.ipc({"command": ["set_property", "fullscreen", True]})
                wm.act("focus", "llmos-media")
                self.instant_reply(line, "Full screen. Press Esc or say “exit full screen” to go back.")
                return True
            if re.fullmatch(r"(?:exit|leave|stop|end|undo)\s+(?:the\s+)?full ?screen(?:\s+mode)?|(?:make|put)\s+(?:it|the video)\s+(?:smaller|back)|un-?full ?screen", q):
                media.ipc({"command": ["set_property", "fullscreen", False]})
                self.instant_reply(line, "Back to a window.")
                return True
            if re.fullmatch(r"(?:close|stop|quit|end|turn off|exit|shut)\s+(?:the\s+|this\s+|my\s+)?(?:video|movie|music|song|player|media player|playback)(?:\s+player)?", q):
                self.media_action("stop")
                self.instant_reply(line, "Stopped and closed.")
                return True
        hit = self._app_question(low)
        if hit:
            kind, a, wid = hit
            if not wid:
                self.instant_reply(line, f"The {a['title'].lower()} is not open.")
            elif kind == "close":
                self.close_window(wid)              # the window goes; its page (and any number in it) with it
                self.instant_reply(line, f"Closed {a['title']}.")
            else:
                self.instant_reply(line, intent.app_reading(self.app_call("read", "", a["id"]), a["title"]))
            return True
        if re.fullmatch(r"unlock(?: the)? (?:screen|computer|desk)[.!]?", low) and self.screen != "lock":
            self.last_reply = self._said = "The screen isn't locked."
            return True
        if re.fullmatch(r"what (?:did|was it) i (?:just )?(?:say|ask|type|write)(?: (?:you|to you))?(?: (?:a (?:minute|moment|second|bit) ago|before|earlier|last|just now|before that))?|"
                        r"what was my (?:last|previous) (?:question|request|message)|what did i ask you(?: (?:before|last|earlier))?", low.rstrip("?.! ")):
            prev = [m["content"] for m in self.chat().msgs if m["role"] == "user" and m["content"].strip().lower().rstrip("?.! ") != low.rstrip("?.! ")]
            self.last_reply = self._said = (f"You said: “{prev[-1]}”" if prev else "You haven't asked me anything yet in this conversation.")
            return True
        if re.fullmatch(r"what(?:'s| is) on (?:my |the )?screen(?: now| right now)?|what(?:'s| is) open(?: now| right now)?|which (?:windows|apps|programs) are open", low.rstrip("?.! ")):
            names = []
            try:
                names += [str(w).split(".")[-1].replace("-", " ").replace("_", " ").title() for w in wm.windows() if str(w).strip()]
            except Exception:
                pass
            names += [str(s.get("title")) for s in self.windows.values() if s.get("title") and str(s.get("title")) not in names]
            seen, uniq = set(), []
            for n in names:
                if n.strip() and n.lower() not in seen:
                    seen.add(n.lower())
                    uniq.append(n)
            names = uniq
            self.last_reply = self._said = ("Open now: " + ", ".join(names) + ".") if names else "Nothing is open, just the desk."
            return True
        if re.fullmatch(r"what(?:'s| is| are| devices are)? (?:plugged|connected) (?:in|into|to) (?:my |the |this )?(?:computer|pc|laptop|machine)|what(?:'s| is) plugged in|(?:list|show)(?: me)? (?:my |the )?(?:usb |connected |plugged[- ]in )?devices", low.rstrip("?.! ")):
            from . import hardware
            self.last_reply = self._said = hardware.plugged_in_sentence()
            return True
        if re.fullmatch(r"(?:please )?(?:click|tap|press)(?: on)?(?: the)? .+", low.rstrip(".!")) and not re.fullmatch(r"(?:please )?(?:press|tap|hit) (?:\S|\d+)", low.rstrip(".!")):
            try:
                open_now = [w for w in wm.windows() if str(w).strip()]
            except Exception:
                open_now = ["?"]                     # can't tell: let the click be tried
            if not open_now and not any(s.get("kind") == "app" for s in self.windows.values()):
                self.last_reply = self._said = _nothing_open_reply(line)
                return True
        r = self._system_shortcut(low, line)
        if r:
            return True
        if everyday.MATCH.search(low) and not intent.is_chain(low) and everyday.handle(self, line):
            return True
        if re.fullmatch(r"(?:skip|next)(?: (?:this|the|that|current))?(?: (?:song|track|one|video|tune))?[.!]?|skip it|next song|next track", low) \
                and getattr(self, "_np_query", ""):
            def skip():
                try:
                    self.media_action("skip")
                except Exception as e:
                    self.emit({"t": "toast", "text": f"Couldn't skip: {e}"})
            threading.Thread(target=skip, daemon=True).start()
            self.last_reply = self._said = "Playing the next one."
            return True
        if re.fullmatch(r"(?:skip|next)(?: (?:this|the|that|current))?(?: (?:song|track|one|video|tune))?[.!]?|skip it|next song|next track", low):
            playing = False
            if shutil.which("playerctl"):
                try:
                    playing = subprocess.run(["playerctl", "status"], capture_output=True, text=True, timeout=5).stdout.strip() == "Playing"
                    if playing:
                        subprocess.run(["playerctl", "next"], capture_output=True, timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    playing = False
            self.last_reply = self._said = "Playing the next one." if playing else "Nothing is playing."
            return True
        if re.fullmatch(r"(?:pause|resume|unpause|play ?pause|pause (?:the |my )?(?:music|video|song)|resume (?:the |my )?(?:music|video|song)|keep playing)[.!]?", low):
            if not media.playing():
                # a video in the browser or another player: the standard media controls (MPRIS)
                if shutil.which("playerctl"):
                    env = dict(os.environ, **(media.desk_env() or {}))
                    st = subprocess.run(["playerctl", "status"], capture_output=True, text=True, timeout=5, env=env).stdout.strip()
                    if st in ("Playing", "Paused"):
                        verb = "play" if re.match(r"resume|unpause|keep", low) else "pause" if not low.startswith("play") else "play-pause"
                        subprocess.run(["playerctl", verb], capture_output=True, timeout=5, env=env)
                        now = subprocess.run(["playerctl", "status"], capture_output=True, text=True, timeout=5, env=env).stdout.strip()
                        self.instant_reply(line, "Paused." if now == "Paused" else "Playing.")
                        return True
                self.instant_reply(line, "Nothing is playing.")
                return True
            want = "resume" if re.match(r"resume|unpause|keep", low) else "pause"
            if low.startswith("play"):
                want = "resume" if getattr(self, "_np_state", "playing") == "paused" else "pause"
            self.media_action(want)
            self._np_state = "paused" if want == "pause" else "playing"
            self.instant_reply(line, "Paused." if want == "pause" else "Playing.")
            return True
        m = _CLIP_Q.fullmatch(low)
        if m:
            if m.group("item"):
                ok = clip.copy_again(m.group("item"))
                self.instant_reply(line, "Copied. Paste it with Ctrl+V." if ok else "That item is gone; copy it again.")
            elif m.group("clear"):
                clip.clear()
                self.instant_reply(line, "Cleared the clipboard.")
            elif m.group("hist"):
                self.open_window(clip.panel())
                self.last_reply = self._said = "Here's what you've copied."
            else:
                t = clip.current()
                self.instant_reply(line, ("You copied: \u201c" + (t[:400] + ("…" if len(t) > 400 else "")) + "\u201d") if t.strip()
                                   else "The clipboard is empty, or holds a picture or a file rather than text.")
            return True
        m = _DEV_Q.fullmatch(low)
        if m:
            fn = clip.camera_test if m.group("cam") else clip.mic_test
            if m.group("mic"):
                self.emit({"t": "toast", "text": "Listening for 4 seconds: say something…"})
            threading.Thread(target=lambda: self.instant_reply(line, fn()[1]), daemon=True).start()
            self._said = "Checking now; the result follows."
            return True
        m = re.fullmatch(r"(?:turn |switch )?(?:the )?wi-?fi (?P<v>on|off)|(?:turn|switch) (?P<v2>on|off) (?:the )?wi-?fi|(?P<v3>enable|disable) (?:the )?wi-?fi", low.rstrip(".!"))
        if m and shutil.which("rfkill"):
            v = m.group("v") or m.group("v2") or ("on" if m.group("v3") == "enable" else "off")
            try:
                have = subprocess.run(["rfkill", "list", "wifi"], capture_output=True, text=True, timeout=5).stdout.strip()
                if have:
                    if system.radio("wifi", _wifi_radio_on(v))[0] == 124:
                        have = ""  # rfkill timed out: keep the old "no Wi-Fi adapter" reply
            except (OSError, subprocess.TimeoutExpired):
                have = ""
            self.instant_reply(line, ("Wi-Fi is off." if v == "off" else "Wi-Fi is on.") if have else "This computer has no Wi-Fi adapter.")
            self.push_status()
            return True
        m = re.fullmatch(r"(?:turn |switch )?(?:on |off )?(?:airplane|aeroplane|flight|plane) mode(?: (?P<v>on|off))?|(?P<v2>turn on|turn off|enable|disable) (?:airplane|aeroplane|flight) mode", low.rstrip(".!"))
        if m and shutil.which("rfkill"):
            v = m.group("v") or ("off" if (m.group("v2") or "").endswith(("off", "disable")) or low.startswith(("turn off", "switch off")) else "on")
            system.radio("all", _airplane_radio_on(v))
            self.instant_reply(line, "Airplane mode is on: Wi-Fi and Bluetooth are off." if v == "on" else "Airplane mode is off.")
            self.push_status()
            return True
        if re.fullmatch(r"forget (?:this|the current|my|the) (?:wi-?fi|network|wi-?fi network)", low.rstrip(".!")):
            if not _wifi_now():
                self.instant_reply(line, "You're not on Wi-Fi right now (connected by cable or not at all), so there's no network to forget. "
                                   "Say \u201cwifi\u201d to see the ones this computer remembers.")
                return True
            line = "forget wifi " + _wifi_now()
        m = re.fullmatch(r"forget (?:the )?wi-?fi(?: network)? (?P<s>.+)|(?P<dis>disconnect (?:from )?(?:the )?wi-?fi)", line.strip().rstrip(".!"), re.I)
        if m and shutil.which("iwctl"):
            dev = _wifi_device()
            if m.group("dis"):
                subprocess.run(["iwctl", "station", dev, "disconnect"], capture_output=True, timeout=15)
                self.instant_reply(line, "Disconnected from Wi-Fi.")
            else:
                subprocess.run(["iwctl", "known-networks", m.group("s"), "forget"], capture_output=True, timeout=15)
                self.instant_reply(line, f"Forgot {m.group('s')}: it won't join by itself any more.")
            threading.Thread(target=self.network_panel, daemon=True).start()
            return True
        if re.fullmatch(r"(?:please )?(?:save|keep) (?:it|this|that|the (?:letter|story|poem|text|email|essay|list|draft|recipe|plan|answer|reply))(?: for me| please)?(?: (?:as a|to a|in a) (?:file|document))?[.!]?", low):
            last = next((m["content"] for m in reversed(self.chat().msgs) if m["role"] == "assistant"), "")
            path = re.search(r"(~/[^\s,;:]+?\.\w{1,5})(?=[\s.,;:!?]|$)", last or "")
            if path:
                self.instant_reply(line, f"It's already saved: {path.group(1)}.")
            elif len(last) >= 120:
                req = next((m["content"] for m in reversed(self.chat().msgs) if m["role"] == "user" and not re.match(r"(?:please )?(?:save|keep)\b", m["content"], re.I)), "")
                title = re.sub(r"[^\w -]+", "", re.sub(r"^(?:please\s+)?(?:write|make|draft|give me|create)\s+(?:me\s+)?(?:a|an|the)?\s*", "", req, flags=re.I)).strip()[:40] or "Note"
                d = os.path.join(config.home(), "Documents")
                os.makedirs(d, exist_ok=True)
                p, n = os.path.join(d, title.capitalize() + ".txt"), 1
                while os.path.exists(p):
                    n += 1
                    p = os.path.join(d, f"{title.capitalize()} ({n}).txt")
                config.guard_write(p)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(last.strip() + "\n")
                self.instant_reply(line, f"Saved in Documents as \u201c{os.path.basename(p)}\u201d.")
            else:
                self.instant_reply(line, "There's nothing here to save yet. In a program, press Ctrl+S; apps you made here save by themselves.")
            return True
        l2 = low.rstrip("?.!")
        btn = {"switch to hands-off mode": ("autonomy", "hands-off"), "switch to balanced mode": ("autonomy", "balanced"),
               "switch to hands-on mode": ("autonomy", "hands-on"), "follow my instructions on my machine": ("guidance", "owner"),
               "keep standard assistant caution": ("guidance", "standard")}.get(l2)
        if btn:      # the Settings window's own buttons: exactly what they say, no model, no guessing
            self.ctx.current_request = f"change the {btn[0]} setting: {line}"     # (the button names the setting itself)
            out = agent.execute(self.ctx, "change_setting", {"setting": btn[0], "value": btn[1]})
            self.instant_reply(line, agent._cap(agent._shortcut_reply("change_setting", {"setting": btn[0], "value": btn[1]}, out)))
            threading.Thread(target=lambda: (time.sleep(0.3), self.open_panel("settings") if "panel-settings" in self.windows or "settings" in self.windows else None), daemon=True).start()
            return True
        m = re.fullmatch(r"use sound (output|input) (\d+)", l2)
        if m:
            ok = syspanels.set_audio_default(m.group(2))
            name = next((n for i, n, _ in syspanels.audio_devices("Sinks" if m.group(1) == "output" else "Sources") if i == m.group(2)), "it")
            self.instant_reply(line, (f"Sound now comes out of {name}." if m.group(1) == "output" else f"The microphone is now {name}.") if ok
                               else "That device isn't available any more.")
            threading.Thread(target=self.sound_panel, daemon=True).start()
            return True
        m = re.fullmatch(r"(?:please )?(?:make|create|play|show|start|do|run|give me) (?:me )?(?:a )?slide ?show (?:of|with|from|using) (?:all )?(?:these|the|my|those)? ?(?:photos|pictures|pics|images)(?: (?:in|from) (?:my )?(?P<f>[\w .~/-]+?))?"
                         r"|(?:show|play) (?:me )?(?:these|the|my|those) (?:photos|pictures|pics|images)(?: (?:in|from) (?:my )?(?P<f2>[\w .~/-]+?))? (?:as a|in a) slide ?show|slide ?show(?: of my (?:photos|pictures))?", l2)
        if m:
            f = (m.group("f") or m.group("f2") or "").strip()
            cands = ([tools._path("~/" + f.capitalize()) if "/" not in f and not f.startswith("~") else tools._path(f)] if f else []) + \
                ([tools._LAST_FOLDER] if tools._LAST_FOLDER else []) + [tools._path("~/Pictures")]
            pics = []
            for d in cands:
                try:
                    pics = sorted((os.path.join(d, n) for n in os.listdir(d) if n.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"))
                                   and not n.startswith(".")), key=os.path.getmtime)
                except OSError:
                    pics = []
                if pics:
                    break
            if not pics or not shutil.which("mpv"):
                self.instant_reply(line, "There are no photos here to show: open the folder they're in (\u201cshow my files in …\u201d) and say it again."
                                   if not pics else "The player isn't installed: say \u201cinstall mpv\u201d.")
                return True
            subprocess.Popen(["mpv", "--fs", "--image-display-duration=5", "--loop-playlist=inf", "--really-quiet", "--title=Slideshow", "--"] + pics,
                             env=self._child_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            self.instant_reply(line, f"Slideshow of {len(pics)} photo(s), 5 seconds each. Space pauses, \u2190 \u2192 go back and forward, Esc ends it.")
            return True
        if re.fullmatch(r"(?:please )?(?:make|create|start|open|do|build|i (?:want|need) to make) (?:a |an |some |my )?(?:new )?(?:presentation|slides|slide ?show|powerpoint)(?: .*)?", l2) \
                and not programs.find("presentation"):
            self.instant_reply(line, "There's no presentation program yet. Say \u201cinstall LibreOffice\u201d (about 300 MB) to get one that "
                               "makes and opens PowerPoint files; or say \u201copen google slides\u201d to make them in the browser.")
            return True
        m = re.fullmatch(r"(?:my email is|i use|use) (?P<w>gmail|outlook|hotmail|yahoo|icloud|aol)(?: mail| for (?:my )?email)?", l2)
        if m:
            w = {"hotmail": "outlook"}.get(m.group("w"), m.group("w"))
            site, name = {"gmail": ("gmail", "Gmail"), "outlook": ("outlook", "Outlook"), "yahoo": ("yahoo mail", "Yahoo Mail"),
                          "icloud": ("https://www.icloud.com/mail", "iCloud Mail"), "aol": ("https://mail.aol.com", "AOL Mail")}[w]
            config.settings.set("mail_web", site)
            config.settings.set("mail_web_name", name)
            self.close_window("mail-pick")
            out = agent.execute(self.ctx, "browse", {"site": site})
            self.instant_reply(line, f"Opened {name}. From now on, \u201ccheck my email\u201d opens it." if not out.startswith("error") else agent.owner_text(out))
            return True
        # the browser's own keys, by name: zoom the page, bookmark it, clear its history
        m = re.fullmatch(r"(?P<zin>(?:make )?(?:the )?(?:text|page|words|font) bigger on (?:this|the) (?:page|website|site)|zoom in(?: on)?(?: (?:this|the) (?:page|website|site))?)|"
                         r"(?P<zout>(?:make )?(?:the )?(?:text|page|words|font) smaller on (?:this|the) (?:page|website|site)|zoom out(?: on)?(?: (?:this|the) (?:page|website|site))?)|"
                         r"(?P<bm>bookmark (?:this|it|this page|the page|this site)|add (?:this|it|this page) to (?:my )?(?:bookmarks|favou?rites)|save this page)|"
                         r"(?P<bms>(?:open|show)(?: me)? (?:my |the )?(?:bookmarks|favou?rites))|"
                         r"(?P<bms2>(?:open|show)(?: me)? (?:my |the )?(?:browser|firefox) (?:bookmarks|favou?rites)|(?:my )?bookmarks)|"
                         r"(?P<priv>(?:(?:open|start|new) )?(?:an? )?(?:new )?private window|(?:open|start|new) (?:an? )?(?:incognito|private)(?: (?:window|mode|browsing))?|incognito(?: window| mode)?)", l2)
        if m and shutil.which("wtype"):
            k = "zoom in" if m.group("zin") else "zoom out" if m.group("zout") else "bookmarks" if (m.group("bms") or m.group("bms2")) else "private window" if m.group("priv") else "bookmark"
            ok, note = wm.browser_key(k)
            self.instant_reply(line, ({"zoom in": "Made the page bigger (Ctrl+0 puts it back).", "zoom out": "Made the page smaller.",
                                       "bookmark": "The bookmark window is open in the browser: press Save.",
                                       "bookmarks": "Your bookmarks are open in the browser.",
                                       "private window": "A private window is open in the browser."}[k]) if ok
                               else note[:1].upper() + note[1:] + ".")
            return True
        if re.fullmatch(r"(?:this |the |a |my )?(?:website|site|web ?page|page|web ?site) (?:won'?t|wont|doesn'?t|does not|isn'?t|is not|will not|can'?t|cannot) (?:load|work|open|come up|connect)(?:ing)?|"
                        r"(?:this |the )?(?:page|website|site) (?:is )?(?:not loading|stuck loading|broken)|(?:websites?|pages?|the internet) (?:are|is) not loading", l2):
            def diagnose():
                if config.settings.get("internet") == "no":
                    return self.instant_reply(line, "The internet is turned off in Settings, so no site loads. Say \u201cturn the internet on\u201d.")
                if not _online():
                    threading.Thread(target=self.network_panel, daemon=True).start()
                    return self.instant_reply(line, "This computer isn't connected to the internet right now. Here are the networks: pick yours.")
                ok = wm.browser_key("reload")[0] if shutil.which("wtype") else False
                self.instant_reply(line, ("Your connection works, so I reloaded the page. " if ok else "Your connection works. ") +
                                   "If it still doesn't load, the site itself is probably down or busy: try again in a few minutes.")
            threading.Thread(target=diagnose, daemon=True).start()
            self._said = "Checking the connection now; the result follows."
            return True
        if re.fullmatch(r"(?:save|print|export|turn) (?:this|the) (?:web ?)?page (?:as|to|into) (?:a )?pdf|save (?:this|the) (?:web ?)?page|print (?:this|the) (?:web ?)?page", l2) and shutil.which("wtype"):
            ok, note = wm.browser_key("print")
            self.instant_reply(line, ("The print window is open in the browser" + (": choose \u201cSave to PDF\u201d as the printer and press Save; it goes to Downloads."
                                                                                     if "pdf" in l2 or l2.startswith("save") else ": press Print.")) if ok
                               else note[:1].upper() + note[1:] + ".")
            return True
        if re.fullmatch(r"(?:remember|save|store) (?:my |the |this )?(?:password|login|sign[- ]in)(?: for (?:this|the) (?:site|website|page))?|(?:where are|show me) my (?:saved )?passwords", l2):
            self.instant_reply(line, "Firefox remembers it: after you sign in on the site it asks \u201cSave login?\u201d, press Save. "
                               "To see saved ones, open the browser menu (\u2630) and choose Passwords.")
            return True
        if re.fullmatch(r"translate (?:this|the) (?:web ?)?(?:page|site|website)(?: (?:to|into) \w+)?", l2):
            self.instant_reply(line, "Firefox translates pages on this computer, privately: press the translate icon (\u6587A) at the right of the "
                               "address bar, or in the menu (\u2630) choose Translate page. To translate some text, paste it here and say \u201ctranslate this to Spanish\u201d.")
            return True
        if re.fullmatch(r"is (?:this|the|that) (?:site|website|web ?page|page|link) (?:safe|legit|real|trustworthy|a scam|secure)", l2):
            self.instant_reply(line, "Tell me its address and I'll check it (for example \u201cis paypa1.com safe?\u201d). Meanwhile: the address must be "
                               "exactly the company's own (watch for swapped letters), and never type a password on a page you reached from an email or an ad.")
            return True
        if re.fullmatch(r"(?:block|stop|remove|get rid of|no) (?:the )?(?:ads|adverts|advertisements|pop-?ups)(?: in the browser| on websites)?|(?:is there an |install an? )?ad ?blocker", l2):
            self.instant_reply(line, "Ads are already blocked: Firefox here comes with uBlock Origin (the red shield at the top right). "
                               "If a site still shows some, press the shield to block more.")
            return True
        if re.fullmatch(r"(?:clear|delete|erase|wipe) (?:my |the |all )?(?:browsing |search |web |browser |chat |conversation )?history", l2):
            web = re.search(r"brows|search|web", l2)
            chat = re.search(r"chat|conversation", l2)
            if web and not chat:
                ok, note = wm.browser_key("clear history") if shutil.which("wtype") else (False, "the browser is not open")
                self.instant_reply(line, "The browser's Clear history window is open: choose how far back and press Clear." if ok
                                   else "Open the browser first (\u201copen the browser\u201d), then say \u201cclear my browsing history\u201d.")
            elif chat and not web:
                self.act("conversations")
                self.last_reply = self._said = "Here are your conversations: press Forget on the ones to remove."
            else:
                self.open_window({"id": "clear-history", "replace": True, "title": "Clear history", "size": "s", "blocks": [
                    {"type": "text", "text": "Which history?", "dim": True},
                    {"type": "buttons", "items": [{"label": "The browser's (sites visited)", "say": "clear my browsing history"},
                                                  {"label": "Our conversations", "say": "clear my chat history"}]}]})
                self.last_reply = self._said = "Which history: the browser's, or our conversations?"
            return True
        if re.fullmatch(r"(?:please )?(?:set ?up|add|connect|configure|sign in to|log ?in to)(?: my)? e-?mail(?: account)?(?: (?:in an app|here|on this computer|in the os|properly))?", l2):
            self.mail_form()
            self.last_reply = self._said = "Type your email address and password in the window."
            return True
        m = re.fullmatch(r"(?:please )?(?:start )?(?:record|recording|capture) (?:my |the |a )?(?P<k>screen|desktop|video of (?:my |the )?screen|voice|audio|microphone|mic|sound|voice (?:memo|note)|memo|me talking)(?: recording)?|"
                         r"(?:start )?(?:a )?(?P<k2>screen|voice|audio) recording|(?:(?:make|start) a )?(?P<k3>voice memo|voice note)", l2)
        if m:
            k = (m.group("k") or m.group("k2") or m.group("k3") or "")
            kind = "screen" if re.search(r"screen|desktop", k) else "voice"
            ok, note = record.start(kind)
            self.instant_reply(line, ("Recording the screen now. Say \u201cstop recording\u201d when you're done; it's saved in Videos." if kind == "screen"
                                      else "Recording from the microphone now. Say \u201cstop recording\u201d when you're done; it's saved in Music.")
                               if ok else note[:1].upper() + note[1:] + ".")
            return True
        if re.fullmatch(r"(?:please )?(?:stop|end|finish) (?:the )?(?:recording|record(?:ing)? (?:my |the )?(?:screen|voice|audio)|screen recording|voice recording)", l2):
            done = record.stop()
            home = config.home().rstrip("/")
            self.instant_reply(line, ("Saved " + " and ".join(("~" + p[len(home):]) if p.startswith(home) else p for _, p in done) + ".")
                               if done else "Nothing was being recorded.")
            return True
        if re.fullmatch(r"what(?:'s| is) (?:my |the |this computer'?s? )?(?:ip|ip address|address on the network|local ip|public ip)|(?:show|tell me) (?:my )?ip(?: address)?|my ip", l2):
            def ip():
                local = ""
                try:
                    out = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=5).stdout
                    local = ", ".join(re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", out))
                except (OSError, subprocess.SubprocessError):
                    pass
                public = ""
                if config.settings.get("internet") in ("yes", "ask") and everyday._net_ok(self, "read_webpage", {"url": "https://api.ipify.org"}):
                    try:
                        from . import web
                        public = web.fetch("https://api.ipify.org", max_bytes=100, timeout=6)[3].decode("ascii", "replace").strip()[:45]
                    except Exception:
                        public = ""
                self.instant_reply(line, (f"On your network: {local or 'not connected'}." if local else "Not connected to a network.") +
                                   (f" To the internet: {public}." if re.fullmatch(r"[\d.:a-f]+", public or "x") else ""))
            threading.Thread(target=ip, daemon=True).start()
            self._said = "Checking now; the result follows."
            return True
        m = re.fullmatch(r"close window (\S+)", l2)
        if m and m.group(1) in self.windows:
            self.close_window(m.group(1))
            self.open_window(self.windows_panel())
            self.last_reply = self._said = "Closed."
            return True
        m = re.fullmatch(r"(switch to|close) ([\w.-]+)", l2)
        if m and shutil.which("lswt") and m.group(2) in wm.windows():
            ok, note = wm.act("focus" if m.group(1) == "switch to" else "close", m.group(2))
            if m.group(1) == "close":
                time.sleep(0.4)
                self.open_window(self.windows_panel())
            self.last_reply = self._said = "Done." if ok else note
            return True
        if re.fullmatch(r"(?:let'?s )?play a game(?: with me)?|(?:show me |any )?games|i'?m bored|what games (?:are there|do you have|can i play)|"
                        r"(?:find|give me|get) (?:me )?(?:a |some )?games?(?: for (?:my |the )?(?:kids?|child|children|son|daughter|grandkids?|family))?|play (?:solitaire|chess|minesweeper|sudoku)(?: / (?:solitaire|chess|minesweeper|sudoku))+", l2):
            games = [("Tic-tac-toe", "play tic tac toe"), ("Snake", "play snake"), ("Minesweeper", "play minesweeper"), ("Sudoku", "play sudoku"),
                     ("Flashcards", "open flashcards"), ("Chess (online)", "play chess"), ("Solitaire (online)", "play solitaire")]
            self.open_window({"id": "games", "replace": True, "title": "Games", "size": "s", "blocks": [
                {"type": "buttons", "items": [{"label": n, "say": sy, "primary": i == 0} for i, (n, sy) in enumerate(games)]},
                {"type": "text", "text": "Or ask for one: \u201cmake a memory game for my kid\u201d.", "dim": True}]})
            self.last_reply = self._said = "Pick a game."
            return True
        if re.fullmatch(r"(?:open |turn on |start |use )?(?:the )?(?:magnifier|magnifying glass|screen magnifier|zoom(?:ed)? (?:in )?on the screen)|magnify(?: the screen)?", l2):
            if shutil.which("wtype"):
                subprocess.run(["wtype", "-M", "logo", "-k", "equal", "-m", "logo"], capture_output=True, timeout=5, env=dict(os.environ, **(media.desk_env() or {})))
            self.instant_reply(line, "Magnifier on. Super and + zooms in further, Super and - zooms out, Super+0 turns it off; "
                               "it follows the pointer. For bigger text everywhere, say \u201cmake everything bigger\u201d.")
            return True
        m = re.fullmatch(r"(?:open |show |turn on |start |use )?(?:the |an? )?(?:on-?screen|virtual|touch(?:screen)?) keyboard(?: (?P<off>off))?|(?P<off2>(?:close|hide|turn off) (?:the )?(?:on-?screen|virtual) keyboard)", l2)
        if m:
            running = subprocess.run(["pgrep", "-f", "wvkbd"], capture_output=True).returncode == 0
            if m.group("off") or m.group("off2") or running:
                subprocess.run(["pkill", "-f", "wvkbd"], capture_output=True)
                self.instant_reply(line, "The on-screen keyboard is closed.")
            elif not shutil.which("wvkbd-mobintl"):
                self.instant_reply(line, "The on-screen keyboard isn't installed yet: say \u201cinstall wvkbd\u201d.")
            else:
                subprocess.Popen(["wvkbd-mobintl", "-L", "260"], env=dict(os.environ, **(media.desk_env() or {})), stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                self.instant_reply(line, "Here's the on-screen keyboard; it types wherever you click. Say \u201cclose the keyboard\u201d to hide it.")
            return True
        if re.fullmatch(r"(?:change|switch|pick|choose) (?:the |my )?(?:font|typeface|letters|writing style)", l2):
            self.open_window({"id": "fonts", "replace": True, "title": "Font", "size": "s", "blocks": [
                {"type": "buttons", "items": [{"label": "Modern (sans)", "say": "use a sans font", "primary": True}, {"label": "Classic (serif)", "say": "use a serif font"},
                                              {"label": "Typewriter (mono)", "say": "use a mono font"}, {"label": "Pixel", "say": "use a pixel font"}]},
                {"type": "buttons", "items": [{"label": "Bigger", "say": "bigger"}, {"label": "Smaller", "say": "smaller"}, {"label": "Normal size", "say": "normal text size"}]}]})
            self.last_reply = self._said = "Pick a font."
            return True
        # what is on the screen: the desk's windows and the programs, each with Switch / Close
        if re.fullmatch(r"what(?:'s| is) (?:open|running)(?: right now| now)?|(?:show|list) (?:me )?(?:my |all )?(?:open )?(?:windows|programs that are open)|"
                        r"where (?:did|is|are) (?:my |the )?(?:window|windows|program|browser)(?: go| gone)?|i lost (?:my |a |the )?window|"
                        r"something (?:just )?popped up(?: and i don'?t know what it is)?|what(?:'s| is) this (?:window|pop-?up|box)", l2):
            self.open_window(self.windows_panel())
            self.last_reply = self._said = "Here's everything that's open."
            return True
        if re.fullmatch(r"(?:put|show|place|arrange) (?:these|them|the two|both|my windows|the windows) side by side|side by side|split (?:the )?screen", l2) and shutil.which("wtype"):
            ok, note = wm.side_by_side()
            self.instant_reply(line, note[:1].upper() + note[1:] + ".")
            return True
        if re.fullmatch(r"(?:make|help) (?:the |my )?battery last longer|(?:save|saving) (?:the )?battery|battery saver(?: on)?|power sav(?:er|ing)(?: mode)?(?: on)?|low power mode", l2):
            for k, v in (("screen_off", 3), ("sleep_after", 15)):
                config.settings.set(k, v)
            try:
                agent.execute(self.ctx, "set_appearance", {"motion": "off"})
            except Exception:
                pass
            self.start_idle()
            self.instant_reply(line, "Battery saving on: the screen turns off after 3 minutes without use, the computer sleeps after 15, "
                               "and the background stops moving. Lower brightness helps most: say \u201cdimmer\u201d.")
            return True
        if re.fullmatch(r"(?:delete|erase|clear|forget|wipe) (?:all )?(?:my |our )?(?:history|conversations?|chats?|messages) (?:with you|together)|forget everything (?:we|i) (?:said|talked about)|forget (?:all )?our conversations?", l2):
            n = conversation.forget_all()
            self.chats = {}
            self.history = []
            self.emit({"t": "clear"})
            self.instant_reply(line, "Done: every conversation with me is deleted from this computer." if n else "There was no conversation history to delete.")
            return True
        if re.fullmatch(r"(?:forget|clear|delete) (?:my |the )?routines", l2):
            ok = store.clear_routines()
            self.instant_reply(line, "Done. I've forgotten the routines I learned." if ok else "I couldn't clear the routines just now.")
            return True
        if re.fullmatch(r"(?:clear|delete) (?:my |the )?(?:activity|audit) log|forget what you did", l2):
            ok = store.clear_audit()
            self.instant_reply(line, "Done. The activity log is empty." if ok else "I couldn't clear the activity log just now.")
            return True
        if re.fullmatch(r"what did you (?:just )?do|what have you (?:just )?done|why did that happen|what happened just now|show me what you did", l2):
            rows = [r for r in store.audit_tail(12) if r.get("tool") not in ("routine",)][-6:]
            if not rows:
                self.instant_reply(line, "I haven't done anything yet in this session.")
            else:
                lines_ = []
                for r in rows:
                    t_ = self.describe_tool(tools.REGISTRY[r["tool"]], r.get("args") or {}) if r.get("tool") in tools.REGISTRY else r.get("tool", "")
                    ok_ = "" if r.get("allowed", True) else " (not done)"
                    lines_.append(f"\u2022 {t_}{ok_}")
                self.instant_reply(line, "Most recent first:\n" + "\n".join(reversed(lines_)) + "\n\nThe full record: say \u201caudit\u201d.")
            return True
        how = self._howto(l2)
        if how:
            self.instant_reply(line, how)
            return True
        if re.fullmatch(r"(?:what|which) (?:data |information |info )?(?:do|does|will) (?:you|it|this|llm os|the (?:os|computer|system)) (?:send|share|upload|collect)(?: to the internet| online| to anyone)?|"
                        r"(?:do|does|are) (?:you|it|this) (?:spy(?:ing)?|track(?:ing)?|send(?:ing)? my data|collect(?:ing)? (?:my )?data|record(?:ing)? me|listen(?:ing)?(?: to me)?)(?: on me)?|"
                        r"is (?:this|it|llm os|my data) private|privacy|(?:what about|tell me about) (?:my )?privacy|where does my data go|who can see my (?:data|files|chats)", l2):
            s_ = config.settings
            net = {"no": "The internet is off: nothing leaves this computer.", "ask": "The internet is set to ask: nothing goes online without your OK each time."}.get(
                s_.get("internet", "yes"), "Something goes online only when a request needs it: a web search, a page or a video you asked for, a download, a model or app you asked to install. It also sets the clock each time the computer starts.")
            svc_ = llm.cloud_label()
            brain = ("Your requests are answered by the model on this computer." if s_.get("brain", "local") == "local" or not config.cloud()
                     else f"With the online assistant on, each request goes to {svc_} with the recent chat, anything I look at to answer it (files, mail, web pages, the screen), and your name and saved memory. "
                          "What I don't look at stays here. Say “ask me before going online” to keep things here unless you agree." if s_.get("brain") == "cloud"
                     else "Requests you send to the online model (Claude/ChatGPT) go to that company; everything else stays here.")
            self.instant_reply(line, f"{net} {brain} There is no tracking, no telemetry and no account. The microphone is only on while you talk to me. "
                               "Your files and chats stay on this computer" + (", locked with your passphrase." if s_.get("vault") else
                                                                                 "; say \u201cset a passphrase\u201d to lock them.") +
                               " Say \u201caudit\u201d to see everything I did.")
            return True
        if re.fullmatch(r"(?:hi|hello|hey|hiya|howdy|good (?:morning|afternoon|evening|day))(?:\s+(?:there|world|again|friend|friends|everyone|everybody|all|computer|buddy|mate|you))?[\s.!,]*", l2):
            self._said = "Hi. What would you like to do?"
            return True
        if re.fullmatch(r"(?:the )?(?:model|ai|assistant|you) (?:is ?n'?t|is not|isnt|aren'?t|are not|stopped|has stopped|keeps not) (?:responding|answering|working|replying)|"
                        r"(?:you'?re|you are|it'?s|it is) (?:stuck|not answering|not responding|frozen)|why (?:aren'?t|are) you (?:not )?(?:answering|responding)|are you (?:there|alive|working)|hello\?+", l2):
            def check():
                if llm.health():
                    self.instant_reply(line, "I'm here and working. " + ("I'm still busy with the last request; say \u201cstop\u201d to cancel it." if self.busy
                                                                         else "Ask me anything."))
                    return
                rc, out, err = system.service("llmos-model", "restart", timeout=60)   # rc 124 = timed out; the wait below decides what to say
                ok = llm.wait_ready(180) if hasattr(llm, "wait_ready") else llm.health()
                self.instant_reply(line, "The model had stopped; I restarted it and it's answering again." if ok else
                                   "The model had stopped and is still starting up. Give it a minute; buttons and settings work meanwhile.")
            threading.Thread(target=check, daemon=True).start()
            self._said = "(checking the model)"
            return True
        if re.fullmatch(r"(?:the )?(?:wi-?fi|internet|network|connection) (?:is ?n'?t|is not|isnt|doesn'?t|does not|not|stopped|keeps) (?:working|work|connecting|dropping)|"
                        r"no (?:internet|wi-?fi|connection)|(?:it says )?(?:(?:the )?(?:wi-?fi|network) )?connected(?: to (?:the |my )?(?:wi-?fi|network|internet))?,? (?:but|yet|and)(?: (?:there'?s|there is|it'?s|it is|nothing))? (?:no internet|not online|nothing (?:loads|works|opens)|no connection|offline)|(?:i )?(?:can'?t|cannot) (?:get online|connect(?: to (?:the )?(?:internet|wi-?fi))?)|(?:the )?internet is (?:down|slow|out)", l2):
            threading.Thread(target=self.network_panel, daemon=True).start()
            wifi = _wifi_device()
            state = ("You're on Wi-Fi (" + _wifi_now() + ") and online." if _online() else "You're on Wi-Fi (" + _wifi_now() + ") but the internet isn't answering; try another network or restart the router.") \
                if _wifi_now() else ("You're online by cable." if _online() else "Not connected.")
            tip = (" Here are the networks in range: pick yours to join." if wifi else
                   " This computer has no Wi-Fi adapter that works here; a network cable or a USB Wi-Fi adapter will.")
            off = " The internet is turned off in Settings; say \u201cturn the internet on\u201d." if config.settings.get("internet") == "no" else ""
            self.instant_reply(line, f"{state}{off}{tip}")
            return True
        if re.fullmatch(r"(?:please )?(?:close|hide|dismiss|get rid of) (?:this|it|that)(?: window| one| thing| app| program)?|close the window", l2):
            if self.windows:
                wid = list(self.windows)[-1]
                title = self.windows[wid].get("title") or "the window"
                self.close_window(wid)
                self.instant_reply(line, f"Closed {title}.")
            elif shutil.which("wlrctl") and wm.last_program():
                t = wm.last_program()
                ok, note = wm.act("close", t)
                self.instant_reply(line, f"Closed {wm.NAMES.get(t, t)}." if ok else note[:1].upper() + note[1:] + ".")
            else:
                self.instant_reply(line, "Nothing is open.")
            return True
        # read the last answer (or what is shown) aloud
        if re.fullmatch(r"(?:please )?(?:read|say) (?:this|that|it|the (?:answer|reply|text|last (?:answer|reply)))(?: (?:to me|out loud|aloud|for me))*|read (?:it |this )?(?:out loud|aloud)(?: to me)?", l2):
            last = next((m["content"] for m in reversed(self.chat().msgs) if m["role"] == "assistant" and len(m["content"]) > 3), "")
            if not last:
                self.instant_reply(line, "There's nothing to read yet. Ask me something, or say \u201cread your replies aloud\u201d to hear every answer.")
            else:
                threading.Thread(target=voice.speak, args=(re.sub(r"[*_`#>]", "", last),), daemon=True).start()
                self.last_reply = self._said = "(reading aloud)"
            return True
        # dictation: words typed wherever the cursor is
        if re.fullmatch(r"(?:please )?(?:type|write down|transcribe) (?:what|everything|whatever) i say|(?:start |turn on )?dictation|dictate|voice typing|speech to text", l2):
            self.instant_reply(line, "Click where the words should go, then press the Windows key + D and talk: what you say is typed there. "
                               "To talk to me instead, press the microphone button.")
            return True
        # hard to see: bigger, straight away
        if re.fullmatch(r"(?:i )?(?:can'?t|cannot|can not) (?:see|read) (?:very well|well|anything|it|this|the (?:text|screen|words))?|(?:the )?(?:text|writing|words|letters|font) (?:is|are) (?:too |so |really )?(?:small|tiny|hard to read)|"
                        r"(?:it'?s |everything is )?(?:too small|hard to (?:see|read))|my eyes (?:are bad|hurt)|i have (?:bad|poor|low) (?:eyesight|vision)", l2):
            agent.execute(self.ctx, "set_appearance", {"scale": "bigger"})
            self.instant_reply(line, "Made everything bigger. Say \u201cbigger\u201d again for more, \u201chigh contrast\u201d for stronger colours, "
                               "or \u201cread your replies aloud\u201d to hear the answers.")
            return True
        # the clock: set it from the internet, then the time zone if the hour is still off
        if re.fullmatch(r"(?:the )?(?:time|clock|date) (?:is |looks |seems )?(?:wrong|off|incorrect|not right)|wrong (?:time|clock|date)|fix (?:the )?(?:time|clock)|"
                        r"(?:the )?(?:time|clock) is (?:an hour|\d+ hours?) (?:off|ahead|behind)", l2):
            def fix():
                ok = system.sync_time()
                now = time.strftime("%-I:%M %p", time.localtime())
                zone = system.timezone() or "UTC"
                self.instant_reply(line, (f"I set the clock from the internet: it's {now} ({zone}). " if ok else f"It's {now} here ({zone}). ") +
                                   "If the hour is still wrong, tell me your city: \u201cset my time zone to Chicago\u201d.")
            threading.Thread(target=fix, daemon=True).start()
            self._said = "(checking the clock)"
            return True
        # the wrong speaker / headphones: the sound panel lists the outputs
        if re.fullmatch(r"(?:the )?sound (?:is )?(?:coming|playing) (?:from|out of|through) the wrong (?:speaker|place|device)|(?:switch|change) (?:the )?(?:speaker|audio output|sound output|output)(?: device)?|"
                        r"use (?:my )?(?:headphones|headset|speakers|the hdmi|the tv) (?:for sound)?|(?:my )?headphones (?:are )?plugged in but (?:the )?sound (?:is )?(?:coming )?(?:from|out of) (?:the )?speakers|"
                        r"(?:sound|audio) (?:still )?(?:comes|coming) (?:from|out of) (?:the )?speakers|(?:i )?(?:can'?t|cannot) hear (?:anything|the sound|sound|it)|no sound|there'?s no sound|sound (?:isn'?t|is not|doesn'?t) work(?:ing)?", l2):
            def fix():
                try:
                    agent.execute(self.ctx, "set_volume", {"mute": False})
                    if (self._volume_pct() or 0) < 30:
                        agent.execute(self.ctx, "set_volume", {"percent": 50})
                except Exception:
                    pass
                chime = "/usr/share/llmos/chime.wav"
                player = shutil.which("pw-play") or shutil.which("aplay")
                if player and os.path.exists(chime):
                    subprocess.Popen([player, chime], env=dict(os.environ, **(media.desk_env() or {})),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.act("sound")
                self.instant_reply(line, "I turned the sound on and played a chime. Heard it? If not, pick your speaker or headphones "
                                   "under Output in the sound panel (More\u2026 shows every device).")
            threading.Thread(target=fix, daemon=True).start()
            self._said = "Checking the sound now; the result follows."
            return True
        # a new wallpaper: the choices, never a removal
        if re.fullmatch(r"(?:change|switch|new|different|another|pick a) (?:my |the |a )?(?:wallpaper|background|desktop background|desktop picture)|(?:change|set) (?:my |the )?wallpaper|i want a (?:new|different) (?:wallpaper|background)", l2):
            self.open_window({"id": "wallpaper", "replace": True, "title": "Wallpaper", "size": "s", "blocks": [
                {"type": "text", "text": "Pick one, or say what you'd like: \u201cuse a photo of the sea as my wallpaper\u201d.", "dim": True},
                {"type": "buttons", "items": [{"label": "Living (moves gently)", "say": "living background", "primary": True},
                                              {"label": "A nature photo", "say": "use a photo of mountains at sunrise as my wallpaper"},
                                              {"label": "One of my pictures", "say": "show my photos"},
                                              {"label": "Plain", "say": "plain background"}]}]})
            self.last_reply = self._said = "Here are the wallpaper choices."
            return True
        if _BATTERY_Q.fullmatch(low):
            b = _battery()
            self.instant_reply(line, "This computer has no battery; it runs on mains power." if not b else
                               f"The battery is at {b['pct']}%" + (", charging." if b["charging"] else "."))
            return True
        if _TIME_Q.fullmatch(low):
            now = time.localtime()
            self.instant_reply(line, time.strftime("It's %-I:%M %p on %A, %B %-d, %Y.", now))
            return True
        if _MEDIUM_Q.search(low):
            self.instant_reply(line, T("d_live_answer") if _live() else T("d_disk_answer"))
            return True
        if re.fullmatch(r"(?:please )?(?:reset (?:this|the|my) (?:computer|pc|laptop|machine|system)(?: to factory(?: settings)?)?|factory reset(?: (?:this|the|my) (?:computer|pc|laptop))?|"
                        r"start (?:fresh|over|from scratch) with (?:this|the|my) (?:computer|pc|laptop)|wipe (?:this|the|my) (?:computer|pc|laptop) and start (?:again|over)|"
                        r"restore (?:to )?factory settings|make it like new|erase everything(?: on (?:this|the) computer)?)", l2):
            usb = bool(syspanels.removable())
            self.open_window({"id": "reset", "replace": True, "title": "Start fresh", "size": "s", "slot": "cascade", "blocks": [
                {"type": "text", "text": f"This erases {reset.LOST}. It keeps {reset.KEPT}, then restarts at the first-time setup."},
                {"type": "text", "text": ("A USB drive is plugged in: back up first and keep your files." if usb else
                                          "To keep your files, plug in a USB drive and press Back up first."), "dim": True},
                {"type": "buttons", "items": [{"label": "Back up my files first", "say": "back up my files", "primary": True},
                                              {"label": "Erase everything and restart", "say": "factory reset now", "danger": True}]}]})
            self.last_reply = self._said = "Here's what starting fresh erases and keeps. Nothing happens until you press Erase."
            return True
        if l2 == "factory reset now":
            def go():
                if not self.ask({"title": "Erase everything?", "text": f"All of it goes for good: {reset.LOST}. This can't be undone.", "danger": True}):
                    self.instant_reply(line, "Nothing was erased.")
                    return
                self.close_window("reset")
                self.emit({"t": "toast", "text": "Erasing…", "sticky": "reset"})
                left = reset.erase()
                if left:
                    sys.stderr.write("desk: reset could not remove: " + ", ".join(left) + "\n")
                self.shutdown("reboot")
            threading.Thread(target=go, daemon=True).start()
            self.last_reply = self._said = "Erasing everything and restarting…"
            return True
        m = re.fullmatch(r"(?:lock|password[- ]?protect|encrypt|protect|put a password on|add a password to|secure) (?:this|that|the|my)?\s*(?P<f>[\w .~/-]*?)\s*folder"
                         r"(?: (?:with|using) (?:a |its own )?password)?|(?:lock|encrypt|password[- ]?protect) (?:my |the folder )?(?P<f2>documents|pictures|photos|music|videos|downloads|desktop|~/\S+|/\S+)(?: (?:with|using) (?:a )?password)?", l2)
        if m:
            g = "f" if m.group("f") else "f2" if m.group("f2") else None
            f = intent.plain(line).strip()[m.start(g):m.end(g)].strip() if g else ""     # (as typed: folder names have capitals)
            f = {"photos": "~/Pictures", "pictures": "~/Pictures", "music": "~/Music", "documents": "~/Documents", "downloads": "~/Downloads",
                 "videos": "~/Videos", "desktop": "~/Desktop"}.get(f.lower(), f)
            path = tools._path(f) if f.startswith(("~", "/")) else (os.path.join(config.home(), f) if f and os.path.isdir(os.path.join(config.home(), f))
                                                                   else (tools._LAST_FOLDER if not f else None))
            if not path or path.rstrip("/") in (config.home().rstrip("/"), "/") or not os.path.isdir(path):
                home = config.home()
                subs = sorted(n for n in os.listdir(home) if not n.startswith(".") and os.path.isdir(os.path.join(home, n)) and n != "lost+found")[:24]
                self.open_window({"id": "folder-pick", "replace": True, "title": "Lock which folder?", "size": "s", "slot": "cascade", "blocks": [
                    {"type": "buttons", "items": [{"label": n, "say": f"lock the folder {os.path.join(home, n)} with a password"} for n in subs]}]})
                self.last_reply = self._said = "Which folder? Pick it in the window (everything in your home folder is already locked by your passphrase whenever the computer is)."
                return True
            self.folder_form("lock", path)
            self.last_reply = self._said = "Type the password for it in the window."
            return True
        m = re.fullmatch(r"(?:unlock|open|decrypt) (?:the |my )?(?P<n>[\w .~/-]+?)(?: folder)?", l2)
        if m and m.group("n") not in ("screen", "computer", "the screen", "it", "vault"):
            hits = folderlock.find_locked(m.group("n"), config.home().rstrip("/"))
            if hits:
                self.folder_form("unlock", hits[0])
                self.last_reply = self._said = "Type its password in the window."
                return True
        if re.fullmatch(r"(?:what can you do|what can i (?:do|say|ask)(?: here| with (?:this|it|you))?|how do i use (?:this|you|it)|what do i do|help me|show me what you can do|"
                        r"what are you|what is this|get started|getting started|\?+)[?.!]*", low):
            self.open_panel("help")
            self.last_reply = self._said = ("Here's what I can do: find and open files, read and send email, play music and videos, "
                                            "set reminders and timers, change how the screen looks and sounds, install programs, and answer questions. "
                                            "You can also say things like “take a screenshot”, “world clock Tokyo” or “lock the screen”.")
            return True
        if re.fullmatch(r"(?:stop|cancel|never ?mind|forget it|abort|halt that|stop that|stop it|cancel that|no stop)[.!]*", low):
            if self.busy:
                self.stop_all()                 # the request in progress stops (its reply says so), and what waited behind it
            else:
                self.emit({"t": "toast", "text": T("d_nothing_running")})
            return True
        if low in ("network", "wifi", "wi-fi", "internet", "show wifi networks", "show the wifi networks", "wifi networks",
                   "connect to wifi", "connect to wi-fi", "network settings", "show the network settings") or \
                re.fullmatch(r"(?:please\s+)?(?:how\s+(?:do|can)\s+i\s+|help\s+me\s+|can\s+you\s+|i\s+(?:want|need)\s+to\s+)?"
                             r"(?:connect|get|go)\s+(?:me\s+|this(?:\s+computer)?\s+)?(?:on(?:to)?|to)\s+(?:the\s+|a\s+)?"
                             r"(?:wi-?fi|wireless|internet|network)(?:\s+network)?", low.rstrip("?.! ")):
            self.network_panel()
            # what the panel shows, in words (it said "Here are the Wi-Fi networks" on a computer without Wi-Fi)
            if _wifi_device() is None:
                self.instant_reply(line, "This computer has no Wi-Fi. " + ("It's online through its network cable." if _online()
                                                                           else "Plug in a network cable to get online."))
            else:
                self.last_reply = self._said = "Here are the Wi-Fi networks: click one to connect."
            return True
        if low in ("sound", "volume", "sound settings", "audio"):
            self.sound_panel()
            return True
        if low in ("power", "power options", "power menu"):
            self.power_panel()
            return True
        if low.startswith("join wifi "):
            self.wifi_join(line.strip()[len("join wifi "):])
            return True
        if low in ("close the live window", "keep trying it"):
            self.close_window("live")
            return True
        if low == "clear":
            self.chat().new_topic()
            for wid in list(self.windows):
                self.close_window(wid)
            self.emit({"t": "clear"})
            return True
        if re.fullmatch(r"(?:new (?:topic|chat|conversation)|start (?:fresh|over|a new (?:topic|chat|conversation))|fresh start|"
                        r"clear (?:the )?chat|forget this conversation|change the subject)[.!]?", low):
            self.chat().new_topic()
            self.emit({"t": "toast", "text": T("d_fresh")})
            return True
        m = re.fullmatch(r"(?:new |start a |open a |start a new |open a new )?side ?chat(?:\s+(?:about|on|for)\s+(?P<about>.+))?[.!]?", low)
        if m:
            self.open_chat(conversation.new_side(m.group("about") or "").id)
            return True
        if low in ("history", "conversations", "my conversations", "show my conversations", "chat history", "show the history",
                   "show my chats", "chats", "sessions"):
            self.conversations_panel()
            return True
        m = re.fullmatch(r"(continue|forget) topic (t[0-9a-f]+)", low)
        if m:
            c = self.chat()
            if m.group(1) == "continue":
                t = c.resume(m.group(2))
                if t:
                    self.emit({"t": "toast", "text": T("d_resumed", title=t["title"])})
            else:
                c.forget_topic(m.group(2))
            self.conversations_panel()
            return True
        m = re.fullmatch(r"(open|delete) side chat (side-[0-9a-f]+)", low)
        if m:
            if m.group(1) == "open":
                self.open_chat(m.group(2))
            else:
                conversation.delete(m.group(2))
                self.chats.pop(m.group(2), None)
                self.close_window("chat-" + m.group(2))
                self.conversations_panel()
            return True
        if low in _LOCK_WORDS:
            if config.settings.get("vault"):
                self.lock()
            else:                               # no passphrase: the screen still locks (and says how to protect it)
                self._keybinds(False)
                self.set_screen("lock", {"note": T("d_lock_open"), "open": True})
            if re.search(r"\b(?:sign|log) (?:me )?(?:out|off)\b", low):
                self.instant_reply(low, "Locked. Signing out here just locks the screen.")
            return True
        if low in ("voice", "listen"):
            self.voice_turn()
            return True
        if low in ("shutdown", "poweroff", "halt", "shut down"):
            self.shutdown("poweroff")
            return True
        if low in ("reboot", "restart"):
            self.shutdown("reboot")
            return True
        if line.startswith("!"):
            self.run_in_terminal(line[1:].strip() or "sh")
            return True
        return False

    # ---- conversations (conversation.py): the main one never needs clearing; side chats beside it

    def chat(self, cid="main"):
        if not hasattr(self, "chats"):
            self.chats = {}
        if cid not in self.chats:
            self.chats[cid] = conversation.Chat(cid)
        return self.chats[cid]

    def open_chat(self, cid):
        c = self.chat(cid)
        wid = "chat-" + cid
        spec = {"id": wid, "title": c.title or T("d_sidechat"), "kind": "chat", "size": "m", "chat": cid,
                "transcript": c.transcript(), "blocks": [{"type": "text", "text": c.title or T("d_sidechat")}]}
        self.windows[wid] = spec
        self.emit({"t": "window", "id": wid, "spec": spec})

    def conversations_panel(self):
        c = self.chat()
        cur = c.current()
        topics = [{"title": t["title"], "subtitle": time.strftime("%b %d, %H:%M", time.localtime(t["last"])) + f" · {t['n']}×",
                   "detail": t.get("gist", ""), "meta": T("d_now") if (cur and t["id"] == cur["id"] and not c.fresh) else "",
                   "actions": ([] if (cur and t["id"] == cur["id"] and not c.fresh) else [{"label": T("d_continue"), "say": f"continue topic {t['id']}", "primary": True}]) +
                              [{"label": T("d_forget"), "say": f"forget topic {t['id']}", "danger": True}]}
                  for t in reversed(c.topics[-30:])]
        sides = [{"title": x["title"], "subtitle": time.strftime("%b %d, %H:%M", time.localtime(x["last"])),
                  "actions": [{"label": T("d_open"), "say": f"open side chat {x['id']}", "primary": True},
                              {"label": T("d_delete"), "say": f"delete side chat {x['id']}", "danger": True}]} for x in conversation.side_chats()[:20]]
        blocks = [{"type": "text", "text": T("d_conv_intro"), "dim": True},
                  {"type": "buttons", "items": [{"label": T("d_new_topic"), "say": "new topic", "primary": True}, {"label": T("d_new_side"), "say": "new side chat"}]},
                  {"type": "heading", "text": T("d_topics")}]
        blocks.append({"type": "list", "items": topics} if topics else {"type": "text", "text": T("d_none_yet"), "dim": True})
        if sides:
            blocks += [{"type": "heading", "text": T("d_sidechats")}, {"type": "list", "items": sides}]
        self.open_window({"id": "panel-conversations", "replace": True, "title": T("d_conversations"), "size": "m", "slot": "side", "blocks": blocks})

    _SYS = [
        (re.compile(r"(?:open (?:the )?)?(?:task manager|activity monitor|system monitor|processes|what'?s running|what is running|"
                    r"what'?s using (?:my |the )?(?:memory|ram|cpu|processor)|why is (?:it|everything|my computer|the computer) (?:so )?(?:slow|laggy)|"
                    r"(?:my )?computer is (?:so )?(?:slow|laggy))[?.!]*"), "processes"),
        (re.compile(r"(?:open (?:my |the )?)?(?:drives|usb|usb drives?|my usb|my stick|usb stick|flash drive|external drives?|whats on the (?:stick|usb)|"
                    r"what'?s on (?:the|my) (?:stick|usb(?: stick| drive)?|flash ?drive|memory stick|thumb ?drive|sd card)|(?:read|open|show) (?:my |the )?(?:sd|memory) card|"
                    r"open (?:the |my )?(?:usb(?: stick| drive)?|flash ?drive))[?.!]*"), "drives"),
        (re.compile(r"(?:open (?:the )?)?(?:displays?|monitors?|screens|display settings|second (?:monitor|screen)|use both screens|projector|"
                    r"(?:change|set|adjust) (?:the |my )?(?:screen |display )?resolution|screen resolution|resolution)[?.!]*"), "displays"),
        (re.compile(r"(?:open (?:the )?)?(?:bluetooth|bluetooth settings|pair (?:a |my )?(?:device|headphones|mouse|keyboard|speaker)s?|"
                    r"connect (?:my )?bluetooth(?: \w+)*)[?.!]*"), "bluetooth"),
        (re.compile(r"(?:open (?:the )?)?(?:printers?|printer settings|add (?:a |my )?printer|set up (?:a |my )?printer|print(?:ing)? (?:is ?n'?t|not) working)[?.!]*"), "printers"),
        (re.compile(r"(?:open (?:the )?)?(?:keyboard|mouse|touchpad|trackpad|keyboard settings|mouse settings|touchpad settings|keyboard and mouse|"
                    r"keyboard layout|change (?:the |my )?keyboard(?: layout)?|input settings|"
                    r"(?:my |the )?(?:mouse|touchpad|keyboard|pointer)(?: is| has)? (?:stopped|stopped working|isn'?t|is not|doesn'?t|won'?t|not|no longer) (?:working|responding|moving|clicking|typing|connecting)|"
                    r"(?:my |the )?(?:mouse|touchpad|keyboard) (?:is )?(?:broken|dead|frozen|not responding)|"
                    r"(?:mouse|keyboard|touchpad) (?:problem|trouble)s?)[?.!]*"), "input"),
        (re.compile(r"(?:open (?:the )?)?(?:storage|disk space|disk usage|free (?:up )?(?:some )?space|(?:my )?disk is full|clean ?up(?: the computer| my computer| disk)?|"
                    r"what'?s (?:using|filling|taking up) (?:my |the )?(?:disk|space|storage)|running out of space|"
                    r"why(?: is|'s) (?:my |the )?(?:disk|drive|storage|computer|hard drive) (?:so )?full|why am i (?:out of|running out of|low on) (?:space|storage)|"
                    r"how much (?:free |disk |storage )?(?:space|storage)(?: do i have| is left| left| have i got)?|how full is (?:my |the )?(?:disk|computer|drive))[?.!]*"), "storage"),
        (re.compile(r"(?:are there (?:any )?updates|check for updates|any updates|updates|"
                    r"is (?:it|the system|everything) up to date)[?.!]*"), "updates"),
        (re.compile(r"(?:about this computer|what computer is this|system info(?:rmation)?|how much (?:ram|memory) do i have|"
                    r"what (?:processor|cpu) do i have|specs|my specs|computer specs)[?.!]*"), "about"),
    ]

    _WIN = re.compile(r"(?P<key>(?:go )?back|previous page|go forward|next page|reload(?: the page)?|refresh(?: the page)?|(?:open )?(?:a )?new tab|"
                      r"close (?:this |the )?tab)|"
                      r"(?:switch|go back|go) to (?:the |my )?(?P<focus>browser|firefox|internet|files|file manager|terminal|editor|text editor|"
                      r"document|word processor|spreadsheet|photos|image viewer|player|video)(?: window| app| program)?|"
                      r"(?:maximi[sz]e|make (?:it|this|the window) (?:full ?screen|bigger|full size)|bigger window|full ?screen)(?: (?:the )?(?P<maxw>\w[\w ]*))?|"
                      r"(?:minimi[sz]e|hide) (?:the )?(?P<minw>\w[\w ]*)|"
                      r"(?:close|quit|exit) (?:the )?(?P<closew>firefox|browser|internet|files|file manager|terminal|editor|text editor|abiword|"
                      r"gnumeric|word processor|spreadsheet|photos|image viewer|player|video|mousepad|thunar)(?: window| app| program)?|"
                      r"(?:force quit|kill(?= \w))(?: (?:the )?(?P<killw>\w[\w ]*))?|"
                      r"(?P<reopen>reopen (?:what i closed|the tab i closed|(?:the |my )?(?:last )?closed (?:tab|one)|the last closed tab)|undo (?:the )?close tab)|"
                      r"(?P<stopf>(?:this|the|my) (?:app|program) (?:is|has|seems) frozen|(?:this|the|my) (?:app|program) froze|"
                      r"(?:this|the|my) (?:app|program) stopped responding)|"
                      r"(?:the )?(?P<frozen>\w[\w ]*?) (?:is|has|seems) (?:frozen|stuck|not responding|hung)")

    def _window_shortcut(self, low):
        """Program windows (the browser, files, a terminal…): switch, maximize, close, unfreeze; the browser's own keys."""
        m = self._WIN.fullmatch(low.rstrip(".!?"))
        if not m:
            return False
        g = m.groupdict()
        for k in ("maxw", "minw", "killw"):          # a name that is not a program's ("hide the clock": a desk window) is not for here
            if g[k] and not wm.app_id(g[k]) and not (k == "killw" and m.group(0).startswith("force quit") and g[k] in ("it", "this", "this app")):
                return False                          # ("force quit it/this": the last program, in stop() below)
        frozen = (g["frozen"] or "").strip()
        if frozen and frozen not in ("screen", "computer", "desk", "everything", "it", "system", "the screen", "my computer", "llm os") \
                and not wm.app_id(frozen):
            return False
        said = {"back": "Back.", "forward": "Forward.", "reload": "Reloaded.", "new tab": "New tab open.", "close tab": "Tab closed."}
        if g["key"]:
            k = g["key"].replace("go ", "").replace(" the page", "").replace("open ", "").replace("a new", "new").replace("this ", "").replace("the ", "")
            k = {"previous page": "back", "next page": "forward", "refresh": "reload"}.get(k, k)
            ok, note = wm.browser_key(k)
            done = said.get(k, "Done.")
        elif g["focus"]:
            t = wm.app_id(g["focus"]) or ""
            ok, note = wm.act("focus", t)
            done = f"Switched to {wm.NAMES.get(t, t)}."
        elif g["reopen"]:
            ok, note = wm.browser_key("reopen tab")
            done = "Reopened the last closed tab."
        elif m.group(0).startswith(("maximi", "make", "bigger", "full")):
            target = wm.app_id(g["maxw"]) if g["maxw"] else wm.last_program()
            ok, note = wm.act("maximize", target) if target else (False, "there is no program window to make bigger")
            done = f"Made {wm.NAMES.get(target, target)} full size."
        elif g["minw"]:
            t = wm.app_id(g["minw"]) or ""
            ok, note = wm.act("minimize", t)
            done = f"Hid {wm.NAMES.get(t, t)}; say \u201cswitch to {g['minw']}\u201d to bring it back."
        elif g["closew"]:
            t = wm.app_id(g["closew"]) or ""
            ok, note = wm.act("close", t)
            done = f"Closed {wm.NAMES.get(t, t)}."
        elif (g["frozen"] or "").strip() in ("screen", "computer", "desk", "everything", "it", "system", "the screen", "my computer", "llm os"):
            # the desk itself: load its page again (windows come back; nothing is lost)
            self._reloaded = True
            self.GLib.idle_add(lambda: (self.webview.load_uri("file://" + PAGE), False)[1])
            self.last_reply = self._said = "Reloaded the screen."
            return True
        else:
            def stop():
                target = wm.app_id(g["killw"] or g["frozen"] or "") or wm.last_program()
                if not target:
                    return self.instant_reply(low, "No program is open to stop.")
                if self.ask({"title": f"Stop {wm.NAMES.get(target, target)}?", "text": "Anything unsaved in it is lost.", "danger": True}):
                    note = wm.force_quit(target)[1]
                    self.instant_reply(low, note[:1].upper() + note[1:] + ".")
            threading.Thread(target=stop, daemon=True).start()
            return True
        text = done if ok else (note[:1].upper() + note[1:] + "." if note else "That didn\u2019t work.")
        self.instant_reply(low, text)
        return True

    # what people say -> the exact phrase a panel's button says (one code path for both)
    _CANON = [
        (re.compile(r"(?:make |set )?(?:the |my )?(?:mouse|pointer|cursor|touchpad|trackpad)(?: speed)? (?:faster|quicker)|speed up (?:the |my )?(?:mouse|pointer|cursor|touchpad)|"
                    r"(?:the |my )?(?:mouse|pointer|cursor|touchpad) is (?:too )?slow|increase (?:the )?(?:mouse|pointer) speed"), "mouse faster"),
        (re.compile(r"(?:make |set )?(?:the |my )?(?:mouse|pointer|cursor|touchpad|trackpad)(?: speed)? slower|slow down (?:the |my )?(?:mouse|pointer|cursor|touchpad)|"
                    r"(?:the |my )?(?:mouse|pointer|cursor|touchpad) is (?:too )?fast|decrease (?:the )?(?:mouse|pointer) speed"), "mouse slower"),
        (re.compile(r"(?:turn on |enable |use )?(?:natural|reverse[d]?|mac[- ]style|inverted) scrolling(?: on)?|reverse (?:the )?scroll(?:ing)?(?: direction)?|invert (?:the )?scroll(?:ing)?"), "natural scrolling on"),
        (re.compile(r"(?:turn off |disable |stop )(?:natural|reverse[d]?|inverted) scrolling|(?:natural|reverse) scrolling off|normal scrolling"), "natural scrolling off"),
        (re.compile(r"(?:turn on |enable )?tap(?:ping)? to click(?: on)?|let me tap (?:the touchpad )?to click"), "tap to click on"),
        (re.compile(r"(?:turn off |disable )tap(?:ping)? to click|tap to click off|stop tap(?:ping)? to click"), "tap to click off"),
        (re.compile(r"(?:i'?m left[- ]handed|left[- ]handed mouse(?: on)?|swap (?:the )?mouse buttons|make the mouse left[- ]handed)"), "left handed mouse on"),
        (re.compile(r"(?:right[- ]handed mouse|left[- ]handed mouse off|normal mouse buttons)"), "left handed mouse off"),
        (re.compile(r"(?:mirror|duplicate|clone) (?:my |the )?(?:screen|display|displays|screens)(?: (?:to|on) (?:the )?(?:projector|tv|second screen|monitor))?|"
                    r"show (?:my |the )?screen on (?:the )?(?:projector|tv|big screen)|same picture on both screens"), "mirror the displays"),
        (re.compile(r"extend (?:my |the )?(?:screen|display|displays|desktop)(?: (?:to|onto) (?:the )?(?:second (?:screen|monitor)|monitor|tv))?|use both (?:screens|monitors) separately"), "extend the displays"),
        (re.compile(r"(?:turn|switch) (?:off|on) (?:the |my )?bluetooth|(?:turn|switch) (?:the |my )?bluetooth (?:off|on)|(?:disable|enable) bluetooth|bluetooth (?:off|on)"), "__bt__"),
        (re.compile(r"(?:make )?(?:the )?key(?:board)? repeat(?: rate)? faster|keys repeat (?:too )?slow(?:ly)?"), "key repeat faster"),
        (re.compile(r"(?:make )?(?:the )?key(?:board)? repeat(?: rate)? slower|keys repeat (?:too )?(?:fast|quickly)"), "key repeat slower"),
    ]
    _ROTATE = re.compile(r"(?:rotate|turn|flip) (?:the |my )?(?:screen|display|monitor)(?: (?P<how>left|right|upside down|around|back|back to normal|normal|90 degrees|180 degrees))?|"
                         r"(?:the |my )?(?:screen|display) is (?P<side>sideways|upside down)|(?:portrait|landscape) mode")
    _RES = re.compile(r"(?:set|change|make) (?:the |my )?(?:screen |display )?resolution (?:to )?(?P<w>\d{3,4}) ?[x×*by ]+ ?(?P<h>\d{3,4})")
    _EJECT = re.compile(r"(?:eject|safely remove|unmount|disconnect) (?:the |my )?(?:usb(?: stick| drive)?|stick|flash ?drive|thumb ?drive|external (?:drive|disk)|memory stick|sd card|drive)|"
                        r"(?:is it|can i) (?:safe to )?(?:remove|unplug|take out|pull out) (?:the |my )?(?:usb|stick|flash ?drive|drive)")
    _DESKTOP = re.compile(r"show (?:me )?(?:the )?desktop|minimi[sz]e (?:everything|all(?: (?:the )?windows)?)|hide (?:all (?:the )?)?(?:windows|programs|everything)|clear the screen")
    _TILE = re.compile(r"(?:put|move|snap) (?:the )?(?P<w>[\w ]+?) (?:on|to) the (?P<side>left|right)(?: side| half)?")
    _TILE2 = re.compile(r"(?:(?:put|move|snap) )?(?:the )?(?P<a>[\w ]+?) (?:on the )?(?P<s1>left|right)(?:,| and) (?:the )?(?P<b>[\w ]+?) (?:on the )?(?P<s2>left|right)")

    _HOWTO = [
        (r"(?:import|bring|move|copy|transfer|get) (?:over )?(?:my )?(?:bookmarks|passwords|favou?rites|history)(?: ?(?:and|/|&|or) ?(?:my )?(?:bookmarks|passwords|favou?rites|history))*"
         r"(?: and \w+)? (?:from|out of|over from) (?:google )?(?:chrome|edge|safari|brave|opera|my old (?:computer|browser|laptop))",
         "On the old computer, in Chrome: Bookmarks → Bookmark manager → ⋮ → Export bookmarks (a .html file), and Settings → Passwords → "
         "Export passwords (a .csv file). Put the files on a USB stick and plug it in here. Then in Firefox: Ctrl+Shift+O → Import and Backup → "
         "Import Bookmarks from HTML, and for the passwords about:logins → ⋯ → Import from a File. Delete the passwords file afterwards: it isn't encrypted."),
        (r"(?:how (?:do|can) i )?(?:change|set|pick) (?:the |my )?(?:browser'?s? |firefox'?s? )?(?:home ?page|start ?page|start-up page)|(?:set|change|make) (?:my |the )?(?:home ?page|start ?page)(?: to .+)?|how do i (?:set|change) (?:my |the )?home ?page",
         "In Firefox: open the menu (☰), choose Settings, then Home, and type the page you want under “Homepage and new windows”."),
        (r"blur (?:my |the )?background(?: (?:in|on|during) (?:the |my )?(?:video )?(?:call|meeting|zoom|teams|meet))?|(?:change|hide) (?:my )?background (?:in|on|during) (?:the |my |a )?(?:video )?(?:call|meeting)|virtual background",
         "That's set in the call itself: in Google Meet, ⋮ → Apply visual effects → Blur; in Zoom, ^ next to Stop Video → Blur my background; in Teams, "
         "… → Video effects → Blur. (Say “change the wallpaper” if you meant this computer's background.)"),
        (r"(?:how (?:do|to|can)(?: (?:i|you|we))? |hwo (?:do|to)(?: i)? )?print(?:ing)?(?: a| the| this| my)?\s*(?:how|document|file|page|something)?\??|(?:how (?:do|to) |hwo )?(?:i )?(?:want to )?print (?:this|that|it|a document|a page)\s*\??$",
         "To print: open the document, press Ctrl+P, pick the printer and press Print. Or say 'print recipe.pdf' with the file's name and I'll send it. No printer yet? Say 'add a printer'."),
        (r"(?:add|make|create|set up|new) (?:an? |another |a new |a separate )?(?:user|account|login|profile)(?: account)?(?: for (?:my |the |a )?.+)?|"
         r"(?:remove|delete) (?:that|the|this|a|my \w+'?s?) (?:user|account|profile)|(?:switch|change) (?:the )?users?|guest (?:account|mode)|"
         r"(?:can|how do) (?:my )?(?:\w+ )?(?:have|get|use) (?:their|his|her|my|an?) (?:own )?(?:account|login)|"
         r"(?:a )?second (?:user|account|login|profile)|another (?:user|account|login)|"
         r"(?:my |the )?\w+ needs (?:her|his|their) own (?:login|account|user)|my (?:wife|husband|son|daughter|kid|partner|friend) needs an? (?:login|account)|"
         r"can two people use this computer",
         "LLM OS has one account so far, yours: everyone who uses this computer uses it as you. Separate accounts for other people are planned. "
         "Until then, say “lock” when you step away (it opens only with your passphrase), or set “hands-on” so I ask before every change."),
        (r"(?:git )?clone (?:this|a|the|my|that) (?:git )?repo(?:sitory)?|(?:download|get) (?:a |this |the )?(?:git ?hub )?repo(?:sitory)?",
         "Sure: say “clone” and the repo's address, for example “clone https://github.com/user/project”. It goes into your Projects folder."),
        (r"give me root|(?:make me|am i|i want to be|run as) (?:an? )?(?:root|admin(?:istrator)?|superuser)|sudo|how do i get root",
         "You already have it: everything on LLM OS runs as the computer's owner account, root. In a terminal (Ctrl+Alt+T) every command "
         "works without sudo, and I can run any command for you: just say it."),
        (r"(?:is|check) (?:the |my )?firewall(?: on| working| running)?|do i have a firewall",
         "__firewall__"),
        (r"(?:check|scan) (?:for|my computer for|this computer for) (?:viruses|malware)|(?:do i have|is there) (?:a |any )?(?:virus|viruses|malware)|antivirus|virus scan",
         "Ordinary viruses are made for Windows and can't run here. To scan files you'll pass on to Windows users anyway, say "
         "\u201cinstall clamav\u201d, then \u201cscan my downloads for viruses with clamscan\u201d."),
        (r"which (?:apps|programs) (?:can|are allowed to) (?:use|access|see) (?:my )?(?:camera|mic|microphone|location)(?:/(?:camera|mic|microphone|location))*|(?:camera|microphone|location) permissions?",
         "Programs here can use the camera and microphone once they're open; websites must ask you first (the browser shows Allow / Block), "
         "and the browser's padlock menu lists what each site may use. Nothing here tracks your location."),
        (r"can i (?:dual[- ]?boot|keep windows|have (?:both|windows too)|install (?:it )?next to windows)(?: with windows)?|dual[- ]?boot(?: with windows)?|"
         r"install alongside windows|install next to windows|keep windows and install (?:llm os|this)|install (?:llm os |this )?without (?:erasing|deleting|removing) windows",
         "Yes: say \u201cinstall LLM OS on this computer\u201d and choose \u201cnext to what's there\u201d. It shrinks the free space, keeps Windows "
         "and its files, and you pick which one to start when the computer turns on."),
        (r"(?:it|the computer|llm os) (?:won'?t|will not|doesn'?t|does not) (?:boot|start|turn on)|(?:my )?computer won'?t start",
         "Plug the LLM OS USB stick in and start the computer from it (hold F12, F9 or Esc while it powers on and choose the USB). "
         "From there, \u201cinstall LLM OS on this computer\u201d can repair it; your files on the disk are kept."),
        (r"(?:an? |the |this |my )?(?:app|program|browser|firefox) keeps (?:crashing|closing|freezing|quitting)|(?:app|program) (?:crashes|closes) (?:all the time|a lot)",
         "Say \u201cforce quit\u201d and its name when it hangs, then open it again. If it keeps happening, \u201cupdate the system\u201d often fixes it; "
         "\u201cwhat's using my memory\u201d shows whether the computer is running short."),
        (r"captions|subtitles|live captions|(?:turn on|show) (?:closed )?captions",
         "For videos, press CC in the player (YouTube and most sites have it). To turn your own speech into text, press the Windows key + D and talk."),
        (r"(?:move|put) (?:the )?(?:dock|taskbar|bar|menu bar) (?:to )?(?:the )?(?:left|right|bottom|top)|pin (?:the |my )?\w+ (?:to|on) the (?:dock|taskbar)",
         "The bar sits at the top (Clean and Mac styles) or the bottom (\u201cWindows layout\u201d). Pinning programs isn't possible yet; "
         "say a program's name to open it, or use the apps button at the top."),
        (r"(?:set|change) (?:the )?default (?:browser|music player|pdf (?:app|reader|viewer)|apps?|programs?)(?:/(?:browser|music player|pdf app))*",
         "Right now: web pages open in Firefox, PDFs in Firefox, documents in AbiWord, spreadsheets in Gnumeric, pictures here, music and video "
         "in the player. To use another program for one file, open that program and open the file from it."),
        (r"what(?:'s| does) this button do|what is this button|what does that button do",
         "Point at it: most buttons show their name. Or tell me what it says and I'll explain."),
        (r"(?:my )?(?:external|usb) (?:hard )?drive (?:isn'?t|is not|won'?t|doesn'?t) (?:showing up|show up|appear|work|mount)|(?:can'?t|cannot) see my (?:usb|external) drive",
         "Unplug it, wait five seconds and plug it into a different USB port, straight into the computer (not a hub). Big drives need their own "
         "power. Then say \u201cdrives\u201d: if it's listed but won't open, it may need repair on the computer that made it."),
        (r"(?:recover|get back|restore|find) (?:my |an? |the )?(?:unsaved|lost) (?:document|file|work|essay|changes)|i (?:forgot|didn'?t) (?:to )?save(?: it)?",
         "Open the same program again: the word processor and the text editor offer to bring back what they saved automatically. "
         "Also try \u201cfind my files called \u2026\u201d with a word from its name, and \u201cshow the trash\u201d."),
        (r"(?:import|copy|get|transfer|move|download) (?:my |the |all (?:my |the )?)?(?:photos|pictures|pics|videos|files)(?: and videos)? (?:from|off(?: of)?) (?:my |the )?(?:phone|camera|iphone|android|sd card)(?: ?(?:/|or) ?(?:my )?(?:phone|camera|iphone|android))?|"
         r"(?:connect|plug in) (?:my )?(?:phone|camera|iphone|android)",
         "Plug the phone or camera in with its USB cable and unlock it; on Android choose \u201cFile transfer\u201d, on an iPhone press Trust. It then appears "
         "in Files (say \u201copen the file manager\u201d) on the left; open its DCIM folder and drag the photos into Pictures. A camera's memory card works the same."),
        (r"(?:check|fix|correct) (?:my |the )?spelling(?: and grammar)?|spell ?check|is this spelled (?:right|correctly)",
         "Paste the text here after \u201ccheck the spelling of:\u201d and I'll correct it. In the word processor or text editor, misspelled words are "
         "underlined in red; right-click one for suggestions."),
        (r"scan (?:this|a|the|my)? ?(?:document|page|paper|photo|it)?(?: (?:to|into|as) (?:a )?pdf)?|how (?:do|can) i scan(?: something| a document)?",
         "Scanning needs the scanner program: say \u201cinstall simple-scan\u201d, connect the scanner (or turn on the printer's scanner), then "
         "\u201copen simple scan\u201d and press Scan; it saves PDFs. With no scanner, a phone photo of the page works too."),
        (r"(?:share|present) (?:my |the )?screen(?: in (?:the |a |my )?(?:call|meeting|zoom|meet|teams))?|screen ?shar(?:e|ing)|how (?:do|can) i share (?:my )?screen",
         "In the call, press its Share screen button (Meet: \u201cPresent now\u201d; Zoom: \u201cShare Screen\u201d). The browser then asks what to share: "
         "pick the whole screen or a window and press Allow."),
        (r"(?:fill (?:in|out)|complete|sign) (?:this |the |a )?pdf(?: form)?|how (?:do|can) i fill (?:in|out) (?:a |this )?pdf(?: form)?",
         "Open the PDF (\u201copen the file \u2026\u201d, or Open on it in your files): it opens in the browser, where you can click into the form's boxes "
         "and type, then press the download arrow to save the filled-in copy, or print it."),
        (r"talk to me|(?:can|could) (?:i|we) talk|(?:can|could) you (?:hear|listen to) me|how (?:do|can) i talk to you|voice mode|use my voice",
         "Press the microphone button (or F1) and talk; I answer when you pause. Say \u201cread your replies aloud\u201d to hear my answers too."),
        (r"how (?:do|can) i (?:take|make|get) (?:a )?screen ?shot|how to (?:take a )?screen ?shot",
         "Press the Print Screen key (or say \u201ctake a screenshot\u201d); Shift+Print Screen or Windows+Shift+S lets you drag a box around part of the screen. It's saved in Pictures and copied, so you can paste it with Ctrl+V."),
        (r"how (?:do|can) i copy and paste|how to copy(?: and paste)?|how (?:do|can) i (?:copy|paste)(?: (?:text|something|things))?",
         "Select the text, press Ctrl+C to copy, click where it should go and press Ctrl+V to paste. Super+V (or \u201cclipboard history\u201d) shows what you copied before."),
        (r"how (?:do|can) i (?:switch|change|move) between (?:windows|programs|apps)|how (?:do|can) i switch windows",
         "Press Alt+Tab, or say \u201cswitch to the browser\u201d. Super+Up makes a window full size; Super+Left and Super+Right put it on half the screen."),
        (r"how (?:do|can) i close (?:a |the |this )?(?:program|window|app)",
         "Press Alt+F4 or the \u00d7 in its corner, or say \u201cclose the browser\u201d. A frozen one: \u201cforce quit firefox\u201d."),
        (r"how (?:do|can) i install (?:a |an )?(?:program|app|software|apps|programs)",
         "Say \u201cinstall\u201d and its name: \u201cinstall VLC\u201d, \u201cinstall Spotify\u201d. It comes from Alpine's packages or Flathub and then opens by name."),
        (r"where (?:are|do) (?:my |the )?(?:files|downloads|documents|pictures|photos)(?: go| saved| kept)?|where (?:is|are) my stuff",
         "In your home folder: Documents, Downloads, Pictures, Music and Videos. Say \u201cshow my files\u201d or \u201copen my downloads\u201d."),
        (r"how (?:do|can) i (?:turn (?:it |this |the computer )?off|shut (?:it |this |the computer )?down|switch (?:it )?off)",
         "Say \u201cshut down\u201d, or press the power symbol at the top right and choose Shut down."),
        (r"how (?:do|can) i (?:lock|log out)(?: the (?:screen|computer))?",
         "Press Super+L or say \u201clock\u201d. With a passphrase set, it's needed to get back in."),
        (r"what(?:'s| is) (?:the )?(?:keyboard )?shortcuts?|(?:list|show)(?: me)? (?:the |all )?(?:keyboard )?shortcuts|keyboard shortcuts",
         "Alt+Tab switch windows \u00b7 Super+Up full size \u00b7 Super+Left/Right half screen \u00b7 Alt+F4 close \u00b7 Print Screen screenshot (Shift: an area) \u00b7 "
         "Ctrl+Alt+Left/Right workspaces \u00b7 Super+V clipboard \u00b7 Super+L lock \u00b7 Super+E files \u00b7 Ctrl+Alt+T terminal \u00b7 Super+D dictation \u00b7 Ctrl+Shift+Esc task manager \u00b7 F1 talk to me."),
    ]

    def _howto(self, l2):
        for rx, text in self._HOWTO:
            if re.fullmatch(rx, l2):
                if text == "__firewall__":     # the status answer follows the firewall setting
                    if config.settings.get("firewall") == "off":
                        return ("The firewall is off: other computers can connect to this one. "
                                "Say “turn the firewall on” to put it back.")
                    return ("The firewall is always on: nothing from the internet can reach this computer unless it answers something you started. "
                            "“Turn the internet off” blocks everything going out too.")
                return text
        return None

    def _system_shortcut(self, low, line):
        """The system's own panels and their buttons (syspanels.py): no model, done at once."""
        low = low.rstrip("?.!")
        for rx, canon in self._CANON:
            if rx.fullmatch(low):
                if canon == "__bt__":
                    canon = "bluetooth off" if re.search(r"\b(?:off|disable)\b", low) else "bluetooth on"
                low = line = canon
                break
        said = {"mouse faster": "The pointer is faster.", "mouse slower": "The pointer is slower.", "mouse normal speed": "The pointer is at normal speed.",
                "natural scrolling on": "Scrolling is reversed (natural), like a phone.", "natural scrolling off": "Scrolling is back to normal.",
                "tap to click on": "Tapping the touchpad clicks.", "tap to click off": "Tapping no longer clicks; press to click.",
                "left handed mouse on": "The mouse buttons are swapped for the left hand.", "left handed mouse off": "The mouse buttons are back to normal.",
                "key repeat faster": "Keys repeat faster.", "key repeat slower": "Keys repeat slower.", "key repeat normal": "Key repeat is normal."}.get(low)
        if said:
            self.instant_reply(line, said)
        m = self._ROTATE.fullmatch(low)
        if m:
            how = (m.group("how") or m.group("side") or "").replace("90 degrees", "left").replace("180 degrees", "upside down").replace("around", "upside down")
            how = {"sideways": "left", "back": "normal", "back to normal": "normal", "": "left"}.get(how, how)
            if low.startswith("landscape"):
                how = "normal"
            if "is upside down" in low or "is sideways" in low:
                how = "normal"
            ok, note = syspanels.rotate(how)
            self.instant_reply(line, note[:1].upper() + note[1:])
            return True
        m = self._RES.fullmatch(low)
        if m:
            out = syspanels.first_output()
            ok, note = syspanels.set_mode(out, f"{m.group('w')}x{m.group('h')}") if out else (False, "no screen found")
            self.instant_reply(line, (note[:1].upper() + note[1:] + ".") if ok else note[:1].upper() + note[1:] + ". Say \u201cdisplays\u201d to see the ones this screen offers.")
            return True
        if self._EJECT.fullmatch(low):
            ds = syspanels.removable()
            if not ds:
                self.instant_reply(line, "No USB stick is plugged in. Plug one in and say it again.")
                return True
            else:
                low = line = f"eject drive {ds[0]['disk']}"
        if self._DESKTOP.fullmatch(low) and shutil.which("wlrctl"):
            for w in list(self.windows):
                self.close_window(w)
            ok, note = wm.minimize_all()
            self.instant_reply(line, "Here's the desktop." if ok or self.windows == {} else note)
            return True
        m = re.fullmatch(r"(?:go to|switch to|show) (?:workspace|desktop|virtual desktop) (?P<n>[1-4]|one|two|three|four)|(?P<dir>next|previous) (?:workspace|desktop)", low)
        if m and shutil.which("wtype"):
            if m.group("n"):
                n = {"one": "1", "two": "2", "three": "3", "four": "4"}.get(m.group("n"), m.group("n"))
                keys = ["-M", "logo", "-k", n, "-m", "logo"]
            else:
                keys = ["-M", "ctrl", "-M", "alt", "-k", "Right" if m.group("dir") == "next" else "Left", "-m", "alt", "-m", "ctrl"]
            subprocess.run(["wtype"] + keys, capture_output=True, timeout=5, env=dict(os.environ, **(media.desk_env() or {})))
            self.instant_reply(line, "Here you are. Ctrl+Alt+Left and Right move between workspaces; Super+1 to 4 jumps.")
            return True
        m = self._TILE.fullmatch(low)
        if m and shutil.which("wlrctl") and wm.app_id(m.group("w")):
            ok, note = wm.tile(wm.app_id(m.group("w")), m.group("side"))
            self.instant_reply(line, note[:1].upper() + note[1:])
            return True
        m = self._TILE2.fullmatch(low)
        if m and m.group("s1") != m.group("s2") and shutil.which("wlrctl"):
            a, b = wm.app_id(m.group("a")), wm.app_id(m.group("b"))
            if a and b and a != b:
                notes = [wm.tile(a, m.group("s1"))[1], wm.tile(b, m.group("s2"))[1]]
                self.instant_reply(line, " ".join(notes))
                return True
        if shutil.which("wlrctl") and self._window_shortcut(low):
            return True
        for rx, which in self._SYS:
            if rx.fullmatch(low):
                fn = {"processes": syspanels.processes, "drives": syspanels.drives, "displays": syspanels.displays,
                      "bluetooth": syspanels.bluetooth, "printers": syspanels.printers, "about": syspanels.about,
                      "input": syspanels.input_panel, "storage": syspanels.storage, "updates": lambda: syspanels.updates_panel(asked=True)}[which]
                threading.Thread(target=lambda: self.open_window(fn()), daemon=True).start()
                self.last_reply = self._said = {"processes": "Here's what is running.", "drives": "Here are the drives.", "displays": "Here are the screens.",
                                                "bluetooth": "Here's Bluetooth.", "printers": "Here are the printers.", "about": "Here's this computer.",
                                                "input": "Check the cable or batteries and try another USB port. Here are the mouse and keyboard settings.", "storage": "Here's the storage.",
                                                "updates": "Checking for updates; the list is on the right."}[which]
                if which == "storage":          # the numbers in words too, not only in the window
                    try:
                        u = shutil.disk_usage("/")          # the same disk the storage window shows
                        self.last_reply = self._said = f"You have {u.free / 1e9:.1f} GB free of {u.total / 1e9:.1f} GB. The details are in the window."
                    except OSError:
                        pass
                return True
        m = re.fullmatch(r"end process (\d+)", low)
        if m:
            def end(pid=m.group(1)):
                if self.ask({"title": f"End {syspanels.friendly_name(pid)}?", "text": "Anything unsaved in it is lost.", "danger": True}):
                    ok, note = syspanels.end_process(pid)
                    self.emit({"t": "toast", "text": note})
                    self.open_window(syspanels.processes())
            threading.Thread(target=end, daemon=True).start()
            return True
        m = re.fullmatch(r"(open|eject) drive (/dev/\S+)", low)
        if m:
            def drive(act=m.group(1), dev=m.group(2)):
                if act == "eject":
                    ok, note = syspanels.eject(dev)
                    self.emit({"t": "toast", "text": note.capitalize(), "long": not ok})
                    self.open_window(syspanels.drives())
                else:
                    ok, where = syspanels.mount(dev)
                    if ok:
                        agent.execute(self.ctx, "show_files", {"path": where})
                    else:
                        self.emit({"t": "toast", "text": where, "long": True})
            threading.Thread(target=drive, daemon=True).start()
            return True
        m = re.fullmatch(r"(extend|mirror) the displays|use only the main display|(?P<proj>use only the (?:projector|tv|second (?:screen|display))|projector only)", low)
        if m:
            ok, note = syspanels.arrange("projector" if m.group("proj") else m.group(1) if m.group(1) else "only")
            self.instant_reply(line, note[:1].upper() + note[1:] + ".")
            self.open_window(syspanels.displays())
            return True
        m = re.fullmatch(r"bluetooth (on|off|search|connect|disconnect|forget)(?: ([0-9a-f:]{17}))?", low)
        if m:
            if m.group(1) in ("on", "off"):          # the power switch: quick, and its answer is the reply
                ok, note = syspanels.bt_action(m.group(1))
                self.instant_reply(line, note + "." if ok else note[:1].upper() + note[1:] + ".")
                self.open_window(syspanels.bluetooth())
                return True
            def bt(act=m.group(1), mac=(m.group(2) or "").upper()):
                if act == "search":
                    self.emit({"t": "toast", "text": "Looking for Bluetooth devices…"})
                    self.open_window(syspanels.bluetooth(scan=True))
                    return
                ok, note = syspanels.bt_action(act, mac)
                self.emit({"t": "toast", "text": note.capitalize(), "long": not ok})
                self.open_window(syspanels.bluetooth())
            threading.Thread(target=bt, daemon=True).start()
            return True
        m = re.fullmatch(r"(?:keyboard layout|use an? |add (?:an? |the )?(?=.*\b(?:keyboard|layout)\b)|switch (?:the )?keyboard to |change (?:the )?keyboard (?:layout )?to )(?P<k>[a-z ()-]+?)(?: keyboard)?(?: layout)?", low)
        if m and syspanels.layout_code(m.group("k")):
            code = syspanels.layout_code(m.group("k"))
            config.settings.set("input.layout", code)
            self.apply_input()
            self.emit({"t": "toast", "text": T("d_kb_set", name=syspanels.LAYOUTS[code])})
            self.open_window(syspanels.input_panel())
            return True
        m = re.fullmatch(r"(natural scrolling|tap to click|left handed mouse) (on|off)|mouse (faster|slower|normal speed)|key repeat (faster|slower|normal)", low)
        if m:
            inp = config.settings.get("input", {}) or {}
            if m.group(1):
                key = {"natural scrolling": "natural_scroll", "tap to click": "tap", "left handed mouse": "left_handed"}[m.group(1)]
                config.settings.set(f"input.{key}", m.group(2) == "on")
            elif m.group(3):
                sp = float(inp.get("pointer_speed", 0))
                sp = 0.0 if m.group(3) == "normal speed" else max(-1.0, min(1.0, sp + (0.25 if m.group(3) == "faster" else -0.25)))
                config.settings.set("input.pointer_speed", sp)
            else:
                rate = int(inp.get("repeat_rate", 25))
                config.settings.set("input.repeat_rate", 25 if m.group(4) == "normal" else max(5, min(60, rate + (10 if m.group(4) == "faster" else -10))))
            self.apply_input()
            self.open_window(syspanels.input_panel())
            return True
        m = re.fullmatch(r"set resolution (\S+) (\d+x\d+)", low)
        if m:
            ok, note = syspanels.set_mode(m.group(1), m.group(2))
            self.emit({"t": "toast", "text": note})
            self.open_window(syspanels.displays())
            return True
        if re.fullmatch(r"clear (?:the )?caches?[.!]?", low):
            self.emit({"t": "toast", "text": syspanels.clear_caches().capitalize()})
            self.open_window(syspanels.storage())
            return True
        if re.fullmatch(r"install (?:the |all (?:the )?)?updates[.!]?|(?:update|upgrade) (?:the |my |all (?:my |the )?)?(?:system|computer|os|llm os|everything|apps|programs|software|applications)(?: now)?[.!]?", low):
            def upd():                    # (asked for in so many words: done, not asked about again)
                self.emit({"t": "toast", "text": "Installing updates…", "sticky": "upd"})
                ok, note = syspanels.updates_apply()
                self.emit({"t": "toast", "text": "", "sticky": "upd"})
                self.emit({"t": "toast", "text": note.capitalize(), "long": True})
                self.open_window(syspanels.updates_panel(asked=True))
            threading.Thread(target=upd, daemon=True).start()
            self.last_reply = self._said = "Installing the updates; you can keep working. I'll say when they're done."
            return True
        if re.fullmatch(r"(?:sleep|suspend|go to sleep|put (?:it|the computer) to sleep|hibernate)[.!]?", low):
            threading.Thread(target=self.sleep_now, daemon=True).start()
            return True
        m = re.fullmatch(r"(?:print a test page on|make) (\S+?)(?: the default printer)?", line.strip(), re.I)
        if m and (low.startswith("print a test page") or low.endswith("the default printer")):
            def prn(name=m.group(1), test=low.startswith("print a test")):
                ok, note = syspanels.test_page(name) if test else syspanels.default_printer(name)
                self.instant_reply(line, note)
                self.open_window(syspanels.printers())
            threading.Thread(target=prn, daemon=True).start()
            self._said = "(printer)"
            return True
        m = re.fullmatch(r"add printer (\S+)", line.strip(), re.I)
        if m:
            def addp(uri=m.group(1)):
                ok, note = syspanels.add_printer(uri)
                self.emit({"t": "toast", "text": note, "long": True})
                self.open_window(syspanels.printers())
            threading.Thread(target=addp, daemon=True).start()
            return True
        return False

    def instant_reply(self, request, text):
        """An answer the OS knows itself, shown like any reply (no model involved)."""
        text = text if self.busy else replytr.translate(text, config.llm_language())
        if self.busy and getattr(self, "_turn_open", False):
            # a longer request is on the card: this answer is a notice beside it, not over it (it was lost when the
            # card's next words arrived)
            self.emit({"t": "toast", "text": f"{request}: {text}"[:400], "long": True})
        else:
            self.emit({"t": "reply.start", "request": request})
            self.emit({"t": "reply.end", "text": text})
        self.last_reply = self._said = text
        try:
            self.chat().record(request, text, False)
        except OSError:
            pass

    def _split_compound(self, text):
        """'open my email and play music': two requests the OS knows by heart, done one after the other. Only when
        every part is one it handles without the model, so 'rock and roll' or 'add milk and eggs' are left whole."""
        parts = [p.strip(" ,.") for p in re.split(r"\s*(?:,\s*)?\b(?:and then|and also|then|and)\b\s*", text) if p.strip(" ,.")]
        if len(parts) < 2 or len(parts) > 3 or intent.is_chain(text) or intent.match(text):
            return None                       # a chain, or a request the OS already knows whole (a schedule "...and then...")
        # a chain, not a list: a later step works on what an earlier one made ("turn it into a pdf, then email it"), or a
        # part is itself several steps; done one by one, each would lose what "it" is, so the model does the whole thing
        if any(re.search(r"\b(?:it|its|them|they|that|those|this|these|the result|the file|the same)\b", p, re.I) for p in parts[1:]) \
                or any("," in p for p in parts):
            return None
        if all(self._instant(p) or intent.match(p) for p in parts):
            return parts
        return None

    def turn(self, text, chat="main"):
        # Ask mode (the switch beside the input): an answer in words, no actions. "ask: " marks it through the queue.
        ask = bool(re.match(r"ask:\s", text))
        if ask:
            text = text[4:].strip()
        if getattr(self, "ctx", None) is not None:
            self.ctx.ask_only = ask
        fixed = intent._retype(text)          # typo-fixed copy: the fast paths get a second pass on it; the model always gets text as typed
        parts = self._split_compound(text) if chat == "main" else None
        if parts:
            said = []
            for p in parts:
                self.last_reply = ""
                self.act(p)
                time.sleep(0.3)
                s = self.__dict__.pop("_said", None) or self.last_reply or ""
                if not s:                       # a step that answers in no words still says it was done
                    s = "Done: " + p
                if s not in said:
                    said.append(s)
            self.last_reply = " ".join(x.rstrip(".") + "." for x in said) if said else "Done: " + "; ".join(parts) + "."
            return
        # fast paths (shortcut, which includes everyday.handle): the typed line first; the typo-fixed copy only when the
        # first pass handled nothing (short-circuit: no second run of a path that already acted)
        if chat == "main" and (self.shortcut(text) or (fixed != text and self.shortcut(fixed))):
            self.last_reply = self.__dict__.pop("_said", None) or "Done."
            getattr(self, "refresh_windows", lambda: None)()
            getattr(self, "push_status", lambda: None)()
            return
        c = self.chat(chat)
        cont = c.continues(text)
        replay, note = c.context(text)
        self.busy = True
        self.ctx.after_turn = None
        self.ctx.cancel.clear()
        self.ctx.chat_id, self.ctx.topic_note = chat, note
        self.last_activity = []
        self.sources = []
        self.emit({"t": "reply.start", "request": text, "chat": chat})
        self._turn_open = chat == "main"
        self.push_status()
        final = ""
        try:
            final = agent.run(self.ctx, text, replay)
            try:
                c.record(text, final, cont)
            except OSError as e:
                sys.stderr.write(f"desk: the conversation could not be kept: {e}\n")
            self.emit({"t": "reply.end", "text": final, "chat": chat})
            if final and config.settings.get("speak_replies"):
                self.emit({"t": "speaking", "on": True})
                try:
                    voice.speak(final)
                finally:
                    self.emit({"t": "speaking", "on": False})
        except llm.ModelError as e:
            self.emit({"t": "reply.error", "text": agent._plain_error(str(e)), "chat": chat})
        except llm.ModelDown:
            self.emit({"t": "reply.error", "text": T("model_down"), "chat": chat})
        except agent.Cancelled:
            self.emit({"t": "reply.error", "text": T("stopped"), "chat": chat, "stopped": True})
        except Exception as e:
            self.emit({"t": "reply.error", "text": agent._plain_error(str(e)), "chat": chat})
        finally:
            self.ctx.chat_id, self.ctx.topic_note = "main", ""
            self.busy = False
            self.last_reply = final
            self.push_status()
        self._turn_open = False
        if self.ctx.after_turn:
            self.shutdown(self.ctx.after_turn)

    # ---- voice

    def voice_turn(self):
        if self.listening or self.screen != "desk":
            return
        if not voice.available():
            self.emit({"t": "toast", "text": T("no_mic")})
            return

        def go():
            self.listening = True
            self.emit({"t": "listening", "on": True})
            self.push_status()
            try:
                wav = voice.listen()
                if wav is None:
                    self.emit({"t": "toast", "text": T("no_mic")})
                    return
                if not wav:
                    self.emit({"t": "toast", "text": T("nothing_heard")})
                    return
                text = voice.transcribe(wav)
            finally:
                self.listening = False
                self.emit({"t": "listening", "on": False})
                self.push_status()
            if text and self.screen == "desk":
                self.emit({"t": "heard", "text": text})
                self.say(text)
        threading.Thread(target=go, daemon=True).start()

    # ---- lock / unlock / power

    _KEEP = ("labwc", "python3", "WebKitWebProcess", "WebKitNetworkProcess", "WebKitGPUProcess", "seatd", "dbus-daemon",
             "pipewire", "wireplumber", "pipewire-pulse",
             "at-spi2-registryd", "at-spi-bus-launcher", "xdg-dbus-proxy",
             # the session's own helpers (nothing of the owner's inside the vault): notifications, idle screen-off,
             # night light, the clipboard history watcher, the portals for screen sharing
             "mako", "swayidle", "wlsunset", "wl-paste", "xdg-desktop-portal", "xdg-desktop-portal-wlr",
             "xdg-document-portal", "xdg-permission-store", "fusermount3")

    def _session_pids(self):
        """Every process of this desk session except the compositor, the desk itself and its WebKit helpers.
        A process's name in /proc is cut at 15 characters ("WebKitWebProces"), so names are compared both whole
        (the program file) and cut: killing the desk's own page at lock would freeze the screen on the desk."""
        mine = os.getpid()
        keep_cut = {k[:15] for k in self._KEEP}
        try:
            display = self._child_env().get("WAYLAND_DISPLAY", "")
        except Exception:
            display = ""
        out = []
        for d in os.listdir("/proc"):
            if not d.isdigit() or int(d) == mine:
                continue
            try:
                with open(f"/proc/{d}/environ", "rb") as f:
                    env = f.read()
                with open(f"/proc/{d}/comm") as f:
                    comm = f.read().strip()
            except OSError:
                continue
            try:
                exe = os.path.basename(os.readlink(f"/proc/{d}/exe"))
            except OSError:
                exe = ""
            if display and (b"WAYLAND_DISPLAY=" + display.encode()) in env.split(b"\0") and \
                    exe not in self._KEEP and comm not in keep_cut and not comm.startswith("llmos"):
                out.append(int(d))
        return out

    def _keybinds(self, enabled):
        """The compositor's configuration: the system's own, with the owner's keyboard and mouse settings; while
        locked it keeps no shortcuts (no new terminal, no Alt-Tab to an old one)."""
        self._locked_keys = not enabled
        self.apply_input()

    def apply_input(self):
        """Write the compositor's settings (keyboard layout and repeat, pointer speed, scrolling, tapping) and reload."""
        cfg = os.path.join(os.environ.get("XDG_CONFIG_HOME", "/var/cache/llmos"), "labwc")
        inp = config.settings.get("input", {}) or {}
        try:
            os.makedirs(cfg, exist_ok=True)
            with open("/etc/xdg/labwc/rc.xml") as f:
                xml = f.read()
            yn = lambda v: "yes" if v else "no"
            dev = (f'<device category="default"><pointerSpeed>{float(inp.get("pointer_speed", 0)):.2f}</pointerSpeed>'
                   f'<leftHanded>{yn(inp.get("left_handed"))}</leftHanded></device>'
                   f'<device category="touchpad"><naturalScroll>{yn(inp.get("natural_scroll", True))}</naturalScroll>'
                   f'<tap>{yn(inp.get("tap", True))}</tap><pointerSpeed>{float(inp.get("pointer_speed", 0)):.2f}</pointerSpeed>'
                   f'<leftHanded>{yn(inp.get("left_handed"))}</leftHanded></device>')
            if "natural_scroll" in inp:          # asked for by the owner: a mouse wheel too, not only the touchpad
                dev = dev.replace('<device category="default">', f'<device category="default"><naturalScroll>{yn(inp.get("natural_scroll"))}</naturalScroll>', 1)
            xml = re.sub(r"<libinput>.*?</libinput>", f"<libinput>{dev}</libinput>", xml, flags=re.S)
            # maximized programs leave the desk's bar (clock, Wi-Fi, battery) in view: top bar, or bottom in the Windows layout
            bar = int(round((48 if (config.settings.get("appearance.layout") or "clean") == "windows" else
                             32 if config.settings.get("appearance.layout") == "mac" else 46) * ui.Theme().scale / 100))
            side = "bottom" if config.settings.get("appearance.layout") == "windows" else "top"
            xml = re.sub(r"\s*<margin [^>]*/>", "", xml)
            xml = xml.replace("</labwc_config>", f'  <margin {side}="{bar}" />\n</labwc_config>', 1)
            # a slower double-click (shaky hands): two clicks this far apart still count as one double-click
            xml = xml.replace("<mouse>", f"<mouse><doubleClickTime>{int(inp.get('double_click_ms', 500))}</doubleClickTime>", 1)
            rate, delay = int(inp.get("repeat_rate", 25)), int(inp.get("repeat_delay", 600))
            xml = xml.replace("<keyboard>", f"<keyboard><repeatRate>{rate}</repeatRate><repeatDelay>{delay}</repeatDelay>", 1)
            if getattr(self, "_locked_keys", False):
                xml = re.sub(r"<keyboard>.*?</keyboard>", f'<keyboard><repeatRate>{rate}</repeatRate><repeatDelay>{delay}</repeatDelay>'
                             '<keybind key="W-A-C-S-F24"><action name="None"/></keybind></keyboard>', xml, flags=re.S)
                xml = re.sub(r"<mouse>.*?</mouse>", '<mouse><context name="Root"><mousebind button="Right" action="Press"><action name="None"/>'
                             '</mousebind></context></mouse>', xml, flags=re.S)
            with open(os.path.join(cfg, "rc.xml"), "w") as f:
                f.write(xml)
            # the keyboard layout is read from the compositor's environment file
            with open(os.path.join(cfg, "environment"), "w") as f:
                f.write(f"XKB_DEFAULT_LAYOUT={re.sub(r'[^a-z,]', '', str(inp.get('layout', 'us')).lower()) or 'us'}\n")
                f.write(f"XCURSOR_SIZE={int(inp.get('cursor_size', 24))}\n")
                if inp.get("variant"):
                    f.write(f"XKB_DEFAULT_VARIANT={re.sub(r'[^a-z0-9_,]', '', str(inp['variant']).lower())}\n")
            subprocess.run(["labwc", "--reconfigure"], capture_output=True, timeout=10, env=self._child_env())
        except Exception as e:
            sys.stderr.write(f"desk: compositor settings not applied: {e}\n")

    def stop_all(self):
        """Stop: the request in progress stops, a question it was asking is answered no, and what was waiting behind it
        is dropped (pressing Stop means stop, not 'go on with the next one')."""
        self.ctx.cancel.set()
        llm.abort()                   # (the model may still be reading the request: that stops too)
        self.decline_dialogs()
        dropped = 0
        while True:
            try:
                done = self.requests.get_nowait()[1]
                dropped += 1
            except queue.Empty:
                break
            with self._pending_lock:              # a dropped request never reaches the worker: count it off here
                self._req_pending = max(0, self._req_pending - 1)
            if done:
                done.set()
        if hasattr(self, "_waiting"):
            with self._pending_lock:
                self._waiting, self._dropped = [], set()
            self._emit_queue()
        if dropped:
            self.emit({"t": "toast", "text": f"Stopped. {dropped} waiting request{'s' if dropped != 1 else ''} cancelled too."})

    def lock(self):
        self.lock_stuck = False
        self.stop_all()                     # a turn in progress stops; nothing queued runs behind the lock
        self._keybinds(False)
        # locking closes every program of this session (a browser with its profile in the vault, a terminal
        # sitting in the home folder, a player on a file in it would otherwise keep the vault open)
        for pid in list(self.apps):
            self.close_app(pid)
        try:
            media.stop()
        except Exception:
            pass
        try:
            from . import mcp           # connectors (MCP subprocesses) may hold files inside the vault
            mcp.shutdown()
        except Exception:
            pass
        deadline = time.time() + 4
        while time.time() < deadline and (self.apps or self._session_pids()):
            time.sleep(0.2)
        for pid in self._session_pids():
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        time.sleep(0.3)
        note = ""
        try:
            vault.lock()
        except Exception as e:
            # the screen locks regardless; the passphrase is verified against the header on unlock
            # and the desk never comes back by itself while the vault is still mounted
            self.lock_stuck = True
            sys.stderr.write(f"desk: the vault could not be closed: {e}\n")
            note = T("lock_failed")
        for wid in list(self.windows):
            self.close_window(wid)
        self.chats = {}                     # read again from the vault after unlocking
        self.set_screen("lock", {"note": note})
        self.push_status()

    def unlock(self, passphrase):
        # only from the lock screen (a repeat that arrives after the desk opened is not a failed attempt), one at
        # a time; vault.unlock checks the passphrase against the header even when the vault is still mounted
        if self.screen == "lock" and not config.settings.get("vault"):
            self._keybinds(True)                # a screen lock without a passphrase: back to the desk
            self.enter_desk()
            return
        if not passphrase or self.screen != "lock":
            return
        if not self._unlocking.acquire(blocking=False):
            return                          # already trying this passphrase (Enter pressed twice)
        try:
            self.emit({"t": "unlock.busy"})
            try:
                ok = vault.unlock(passphrase)
            except Exception:
                ok = False
        finally:
            self._unlocking.release()
        if ok:
            self.unlock_failures = 0
            self.lock_stuck = False
            self._keybinds(True)
            self.enter_desk()
        else:
            self.unlock_failures += 1
            self.emit({"t": "unlock.error", "text": T("wrong_passphrase")})
            if self.unlock_failures >= 5:
                self.shutdown("poweroff")

    def shutdown(self, how):
        self.set_screen("bye", {"text": T("shutting_down") if how == "poweroff" else T("restarting")})
        time.sleep(0.8)
        if config.settings.get("vault") and vault.unlocked():
            try:
                vault.lock()
            except Exception:
                pass
        system.power("poweroff" if how == "poweroff" else "reboot")

    # ---- onboarding (one step at a time; the page drives the order)

    def wizard_step(self, step, value):
        ok = lambda **extra: self.emit({"t": "wizard.ok", "step": step, **extra})
        err = lambda text: self.emit({"t": "wizard.error", "step": step, "text": text})
        if isinstance(value, str) and value[:1] == "{":      # the control socket passes JSON for the slider/account steps
            try:
                value = json.loads(value)
            except ValueError:
                pass
        try:
            if step == "welcome":
                ok()
            elif step == "wifi":
                v = value if isinstance(value, dict) else {}
                if isinstance(value, str):
                    ssid, _, pw = value.partition(" / ")
                    v = {"ssid": ssid, "password": pw}
                if not v.get("ssid"):
                    ok()
                    return
                good, note = _wifi_connect(str(v["ssid"]), str(v.get("password", "")))
                if good:
                    ok(note=note)
                else:
                    err(note)
            elif step == "language":
                lang = str(value or "").strip()
                if lang:
                    config.settings.set("language", i18n.display_name(lang))
                    if i18n.lang_code(lang) not in i18n.BUILTIN:
                        self.emit({"t": "toast", "text": T("loading_model"), "sticky": "i18n"})
                        i18n.table_for(lang)
                        self.emit({"t": "toast", "text": "", "sticky": "i18n"})
                self.apply_theme()
                ok()
            elif step == "name":
                if str(value or "").strip():
                    config.Profile().set("name", str(value).strip()[:60])
                ok()
            elif step == "timezone":
                v = str(value or "").strip()
                if v and v != system.timezone():
                    zone = system.set_timezone(v)
                    ok(value=zone)
                else:
                    ok(value=system.timezone())
            elif step == "profile":
                # six sliders (0-100) decide the autonomy, the internet policy, where it thinks, the on-device
                # model, the guidance and the motion. Each maps to the same settings words can change later.
                p = value if isinstance(value, dict) else {}

                def num(k, d):
                    try:
                        return max(0, min(100, int(float(p.get(k, d)))))
                    except (TypeError, ValueError):
                        return d
                auto, net, brain = num("autonomy", 0), num("internet", 0), num("brain", 0)
                cap, guide, motion = num("capability", 30), num("guidance", 0), num("motion", 100)
                config.settings.set("profile", {"autonomy": auto, "internet": net, "brain": brain, "capability": cap, "guidance": guide, "motion": motion})
                config.settings.set("autonomy", "hands-off" if auto < 34 else "balanced" if auto < 67 else "hands-on")
                net_pol = "yes" if net < 34 else "ask" if net < 67 else "no"
                config.settings.set("internet", net_pol)
                system.apply_firewall(net_pol)
                brain_pol = "local" if net_pol == "no" or brain < 34 else "ask" if brain < 67 else "cloud"
                config.settings.set("brain", brain_pol)
                config.settings.set("guidance", "owner" if guide < 50 else "standard")
                config.settings.set("appearance.motion", "full" if motion >= 67 else "reduced" if motion >= 34 else "off")
                # the on-device model: among those that fit the memory, the smallest / the middle / the biggest
                # (offline, only what is already installed can be chosen: nothing could be downloaded)
                ram = models.ram_gb()
                inst = {m["id"] for m in models.installed()}
                want = str(p.get("model") or "")
                pick = None
                tiers = _model_tiers(net_pol != "no")
                if want and any(x["id"] == want for x in tiers + _model_all(net_pol != "no")):
                    pick = next((m for m in models.catalog() if m["id"] == want), None)
                elif tiers:
                    # no model named (an older page): the tier the capability slider points at
                    name = "fast" if cap < 34 else "balanced" if cap < 67 else "capable"
                    pick = next((t for t in tiers if t["tier"] == name), tiers[-1])
                cur = models.active()
                self.wizard_model = pick["id"] if pick and (not cur or pick["id"] != cur["id"]) else None
                self.apply_theme()
                ok(autonomy=config.settings.get("autonomy"), internet=net_pol, brain=brain_pol, guidance=config.settings.get("guidance"),
                   motion=config.settings.get("appearance.motion"), model=pick["name"] if pick else "",
                   download=bool(self.wizard_model and pick["id"] not in {m["id"] for m in models.installed()}),
                   wifi=bool(net_pol != "no" and _wifi_device() and not _online()),
                   cloud_setup=bool(brain_pol != "local" and not config.cloud()))
            elif step == "cloud":
                # the online-model account (only shown when the brain slider asked for one); skipping keeps the
                # brain setting, and everything is answered here until an account is added in settings
                v = value if isinstance(value, dict) else {}
                if v.get("connected") and config.cloud():
                    ok()
                    return
                if not v.get("key"):
                    ok(skipped=True)
                    return
                good, note = llm.cloud_setup(v, adopt=False)
                if good:
                    store.audit("online_model", {"provider": v.get("provider"), "model": v.get("model"), "key": "…" + str(v["key"])[-4:]},
                                "account added", who="owner")
                    ok(note=note)
                else:
                    err(note)
            elif step == "autonomy":
                v = str(value or "hands-off")
                config.settings.set("autonomy", v if v in ("hands-off", "balanced", "hands-on") else "balanced")
                ok()
            elif step == "internet":
                v = "no" if value in (False, "no", "n", 0, "offline") else "yes"
                config.settings.set("internet", v)
                system.apply_firewall()
                if value == "tor":
                    self.emit({"t": "toast", "text": T("loading_model"), "sticky": "tor"})
                    system.set_tor(True)
                    self.emit({"t": "toast", "text": "", "sticky": "tor"})
                ok(wifi=bool(v == "yes" and _wifi_device() and not _online()))
            elif step == "tor":
                if value in (True, "yes", "y", 1):
                    self.emit({"t": "toast", "text": T("loading_model"), "sticky": "tor"})
                    system.set_tor(True)
                    self.emit({"t": "toast", "text": "", "sticky": "tor"})
                ok()
            elif step == "passphrase":
                p = str(value or "")
                if p:
                    self.emit({"t": "toast", "text": T("creating_vault"), "sticky": "vault"})
                    try:
                        vault.create(p)
                    finally:
                        self.emit({"t": "toast", "text": "", "sticky": "vault"})
                ok()
            elif step == "done":
                config.settings.set("onboarded", True)
                mid = getattr(self, "wizard_model", None)
                if mid:
                    def fetch(mid=mid):
                        try:
                            self.emit({"t": "toast", "text": T("loading_model"), "sticky": "model"})
                            tools.manage_models({"action": "download", "model": mid}, self.ctx)
                            tools.manage_models({"action": "use", "model": mid}, self.ctx)
                            self.push_status()
                        except Exception as e:
                            sys.stderr.write(f"desk: the chosen model could not be fetched: {e}\n")
                        finally:
                            self.emit({"t": "toast", "text": "", "sticky": "model"})
                    self.ctx.background(fetch)
                store.remember(f"set up LLM OS on {time.strftime('%Y-%m-%d')}")
                ok()
                self.enter_desk()
                if config.settings.get("brain", "local") != "local" and not config.cloud():
                    self.open_connect_panel()
                else:
                    self.open_panel("help")
            else:
                err("unknown step")
        except (ValueError, vault.VaultError) as e:
            err(str(e))
        except Exception as e:
            err(agent._plain_error(str(e)))

    # ---- apps and terminals (windows in the compositor)

    def _child_env(self):
        env = dict(os.environ, MOZ_ENABLE_WAYLAND="1", GDK_BACKEND="wayland", QT_QPA_PLATFORM="wayland",
                   SDL_VIDEODRIVER="wayland", XDG_SESSION_TYPE="wayland")
        env.update(config.personal_env())
        return env

    def _app_evt(self):
        if not hasattr(self, "_app_event"):
            self._app_event = threading.Event()
        return self._app_event

    def app_call(self, what, text="", app_id=""):
        """Ask the open app (the front one, or app_id) to press a control by its label or to report its page."""
        if not any(w.get("kind") == "app" for w in self.windows.values()):
            return None
        evt = self._app_evt()
        evt.clear()
        self._app_res = None
        self.emit({"t": "eval", "js": f"window.llmosApp && window.llmosApp({json.dumps(what)}, {json.dumps(text)}, {json.dumps(app_id)})"})
        return self._app_res if evt.wait(3) else None

    def _focus_or_reopen(self, argv, name=""):
        """A running program whose window was closed (Telegram keeps running in the background) is opened again:
        clicking it must never do nothing. A program that is still open is brought to the front."""
        ok, _ = wm.focus_program(argv)
        if not ok:
            self.launch_app(argv, name)

    def launch_app(self, argv, name=""):
        log = open(os.path.join(config.RUN, "gui.log"), "a")
        if argv and os.path.basename(argv[0]) == "foot" and not any(a.startswith("--working-directory") for a in argv) \
                and (not config.settings.get("vault") or vault.unlocked()):
            argv = [argv[0], "--working-directory=" + config.home()] + list(argv[1:])     # a terminal starts at home, as everywhere
        argv = _root_ok(list(argv))
        deadline = time.monotonic() + 3.0       # the whole launch, from here, takes 3 s at most
        # wm.windows() has no timeout of its own: each window check runs in a short-lived thread and gets at most
        # 0.3 s (never past the deadline). A check that does not return turns window detection off for this launch.
        detect = True
        before = set()                          # the program windows open before this launch
        snap = self._windows_within(min(0.3, deadline - time.monotonic()))
        if snap is None:
            detect = False
        else:
            before = set(snap)
        try:
            start = log.tell()
            p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True, env=self._child_env(), cwd="/")   # never inside the vault
        except OSError as e:
            return f"could not start {argv[0]}: {e}"
        name = name or os.path.basename(argv[0])
        # a program that closes again at once did not open: say so instead of "opened". Its window showing up
        # (a window that was already open before the launch does not count) ends the wait early; 3 s at most.
        while time.monotonic() < deadline:
            if p.poll() is not None:
                break
            if detect:
                now = self._windows_within(min(0.3, deadline - time.monotonic()))
                if now is None:
                    detect = False              # no answer in time: the plain wait for the rest of the 3 s
                elif self._launch_window_up(argv, before, now):
                    break
            time.sleep(max(0.0, min(0.1, deadline - time.monotonic())))
        if p.poll() not in (None, 0):
            try:
                with open(os.path.join(config.RUN, "gui.log"), errors="replace") as f:
                    f.seek(start)
                    tail = " ".join(f.read().strip().splitlines()[-2:])[-200:]
            except OSError:
                tail = ""
            return f"could not start {name}: it closed at once" + (f" ({tail})" if tail else "")
        self.apps[p.pid] = {"name": name, "popen": p, "argv": argv}
        self._push_apps()
        threading.Thread(target=self._reap, args=(p,), daemon=True).start()
        return p.pid

    def _windows_within(self, limit):
        """wm.windows() within `limit` seconds: its list ([] if it raised), or None when it did not return in time."""
        box = {}

        def work():
            try:
                box["w"] = list(wm.windows())
            except Exception:
                box["w"] = []
        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(max(0.0, limit))
        if t.is_alive():
            return None
        return box.get("w", [])

    def _launch_window_up(self, argv, before, now=None):
        """True when a program window that is NEW since the launch belongs to the program started (wm.PROCS and
        focus_program name the same ids). No window tools, or any error: False, so the 3 s wait runs as before."""
        try:
            name = os.path.basename(str(argv[0])) if argv else ""
            if now is None:
                now = wm.windows()
            new = [a for a in now if a not in before]
            if not new or not name:
                return False
            want = [a for a, pr in wm.PROCS.items() if pr == name] + [name, name.lower()]
            return any(a in new for a in want)
        except Exception:
            return False

    def _reap(self, p):
        p.wait()
        self.apps.pop(p.pid, None)
        self._push_apps()

    def _push_apps(self):
        self.emit({"t": "apps", "items": [{"pid": pid, "name": a["name"]} for pid, a in self.apps.items()]})
        if self.apps and not getattr(self, "_chip_watch", False):
            self._chip_watch = True
            threading.Thread(target=self._watch_app_windows, daemon=True).start()

    def _watch_app_windows(self):
        """A program's dock button goes when its window does. Some programs (the text editor) keep running after
        their window is closed, so waiting for the process left a button with nothing behind it."""
        try:
            while self.apps:
                time.sleep(3)
                try:
                    wins = set(wm.windows())
                except Exception:
                    continue
                gone = []
                for pid, a in list(self.apps.items()):
                    name = os.path.basename(str((a.get("argv") or [""])[0]))
                    want = {x for x, pr in wm.PROCS.items() if pr == name} | {name, name.lower()}
                    if want & wins:
                        a["seen"], a["missed"] = True, 0
                    elif a.get("seen"):
                        a["missed"] = a.get("missed", 0) + 1
                        if a["missed"] >= 2:
                            gone.append(pid)
                for pid in gone:
                    self.apps.pop(pid, None)
                if gone:
                    self._push_apps_only()
        finally:
            self._chip_watch = False

    def _push_apps_only(self):
        self.emit({"t": "apps", "items": [{"pid": pid, "name": a["name"]} for pid, a in self.apps.items()]})

    def close_app(self, pid):
        a = self.apps.get(pid)
        if not a:
            return
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass

    def _focus_desk(self):
        """The desk comes back in front of programs, ready to type (the Super key, and after a test reset)."""
        if shutil.which("wlrctl"):
            subprocess.run(["wlrctl", "toplevel", "focus", "app_id:org.llmos.desk"], capture_output=True, timeout=5,
                           env=dict(os.environ, **(media.desk_env() or {})))
        self.GLib.idle_add(lambda: (self.gtkwin.present() if getattr(self, "gtkwin", None) else None, False)[1])
        self.emit({"t": "eval", "js": "document.getElementById('in') && document.getElementById('in').focus()"})

    def run_in_terminal(self, cmd):
        """Interactive programs and !commands get a terminal window."""
        if not shutil.which("foot"):
            return 127
        script = f"cd \"$HOME\" 2>/dev/null; {cmd}; printf '\\n[{T('d_done')} — Enter]'; read _x"
        self.launch_app(["foot", "--title", cmd[:60], "-e", "/bin/sh", "-c", script], name=cmd.split()[0][:20])
        return 0

    # ---- media (mpv as a window, controlled over its IPC socket)

    def media_action(self, action, **kw):
        if action == "skip":
            q, pick = getattr(self, "_np_query", ""), getattr(self, "_np_pick", 1) + 1
            if not q:
                return "nothing to skip to"
            return self.media_action("play", query=q, pick=pick)
        if action == "play":
            q = kw.get("query", "")
            pick = int(kw.get("pick") or 1)
            if not re.match(r"^https?://", q):
                self._np_query, self._np_pick = q, pick
            info = media.find(q, pick)
            media.stop()
            audio_only = bool(kw.get("audio_only"))
            p = media.play_windowed(info, audio_only, self._child_env())
            info["video"] = not audio_only
            info["audio"] = media.has_audio()
            self._now_playing(info, "playing")
            return info
        if action in ("pause", "resume", "stop"):
            if action == "stop":
                ok = media.stop()
                self.close_window("nowplaying")
                return "stopped" if ok else "nothing was playing"
            ok = media.ipc({"command": ["set_property", "pause", action == "pause"]})
            if ok:
                self._refresh_now_playing("paused" if action == "pause" else "playing")
                if (getattr(self, "_np", None) or {}).get("video"):
                    # asking the desk brought it in front of the video: the picture comes back to the front
                    threading.Timer(0.4, lambda: wm.act("focus", "llmos-media")).start()
            return (action + "d") if ok else "nothing is playing"
        if action == "volume":
            v = kw.get("value")
            try:
                v = max(0, min(130, int(v)))
            except (TypeError, ValueError):
                return "volume must be a number"
            return "volume set" if media.ipc({"command": ["set_property", "volume", v]}) else "nothing is playing"
        return "unknown media action"

    def _now_playing(self, info, state):
        self._np = info
        self.open_window({"id": "nowplaying", "replace": True, "title": T("d_now_playing"), "kind": "media", "size": "s",
                          "blocks": [{"type": "media", "title": info.get("title", ""), "subtitle": info.get("channel", "") +
                                      (f" · {info['duration']}" if info.get("duration") else ""),
                                      "thumbnail": info.get("thumbnail", ""), "state": state, "link": info.get("url", "")}]})

    def _refresh_now_playing(self, state):
        if getattr(self, "_np", None):
            self._now_playing(self._np, state)

    # ---- control socket (tests, the text console)

    def _control_socket(self):
        try:
            os.unlink(SOCK)
        except OSError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(SOCK)
        os.chmod(SOCK, 0o600)
        srv.listen(4)
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=self._control_conn, args=(conn,), daemon=True).start()

    def _state(self):
        return {"screen": self.screen, "busy": self.busy, "reply": self.last_reply,
                "queued": self.requests.qsize(), "done": self._req_done,
                "dialogs": [{"id": k, "title": v[2], "text": v[3]} for k, v in self.dialogs.items() if len(v) > 3],
                "windows": [{"id": w["id"], "title": w["title"], "kind": w["kind"],
                             "blocks": [b["type"] for b in w["blocks"]], "rows": uispec.to_rows(w)[:40],
                             "actions": [a["say"] for b in w["blocks"] if b["type"] in ("buttons", "choices")
                                         for a in b["items"]][:20]}
                            for w in self.windows.values()],
                "apps": [a["name"] for a in self.apps.values()]}

    def _control_conn(self, conn):
        try:
            conn.settimeout(900)
            f = conn.makefile("r", encoding="utf-8")
            line = f.readline().strip()
            cmd, _, arg = line.partition(" ")
            if cmd == "say":
                before = set(self.windows)
                done = threading.Event()
                self.say(arg, done)
                done.wait(880)
                st = self._state()
                st["new_windows"] = [w["title"] for wid, w in self.windows.items() if wid not in before]
                out = st
            elif cmd == "state":
                out = self._state()
            elif cmd == "wait":            # until the request(s) asked for are finished, not only queued
                # "wait N after M": M = requests finished before this one was sent (the desk-state "done" count)
                words = arg.split()
                after = None
                if len(words) == 3 and words[1] == "after" and words[2].isdigit():
                    arg, after = words[0], int(words[2])
                start_reply = self.last_reply
                if after is None:
                    # grace: up to 3 s for a request to start (a shortcut can finish before busy is ever set)
                    for _ in range(30):
                        if self._req_pending > 0 or self.busy or self.last_reply != start_reply:
                            break
                        time.sleep(0.1)
                    for _ in range(int(arg or 600) * 4):
                        if self._req_pending == 0 and not self.busy and self.requests.empty():
                            break
                        time.sleep(0.25)
                else:
                    # with "after": the grace lasts until the line sent after M starts or finishes, bounded only by the
                    # timeout (the typed line can reach say() late); the idle wait is bounded by the same deadline
                    deadline = time.monotonic() + int(arg or 600)
                    while time.monotonic() < deadline:
                        if self._req_done > after or self._req_pending > 0 or self.busy:
                            break
                        time.sleep(max(0.0, min(0.1, deadline - time.monotonic())))
                    while time.monotonic() < deadline:
                        if self._req_pending == 0 and not self.busy and self.requests.empty():
                            break
                        time.sleep(max(0.0, min(0.25, deadline - time.monotonic())))
                out = self._state()
            elif cmd == "dialog":          # answer every pending confirmation (tests)
                for did, d in list(self.dialogs.items()):
                    d[1] = arg or "yes"
                    d[0].set()
                    self.emit({"t": "dialog.close", "id": did})
                out = {"ok": True}
            elif cmd == "cancel":
                self.stop_all()
                out = {"ok": True}
            elif cmd == "close":
                self.close_window(arg)
                out = {"ok": True}
            elif cmd == "wizard":
                step, _, value = arg.partition(" ")
                self.wizard_step(step, value)
                out = {"ok": True}
            elif cmd == "signin-test" and _fwcfg("testshell"):   # tests: "signin-test <provider> <clipboard text>"
                pid, _, text = arg.partition(" ")

                def fake(pid=pid, text=text):
                    # as if Copy were pressed on the service's page: with the sign-in window open, its clipboard
                    # watch does the rest (closes the window on a key); without one, as if it had just closed
                    self.Gdk.Display.get_default().get_clipboard().set(text)
                    if getattr(self, "_signin_win", None) is None:
                        self._signin_closed(pid)
                    return False
                self.GLib.idle_add(fake)
                out = {"ok": True}
            elif cmd == "unlock":
                self.unlock(arg)
                out = {"ok": True, "screen": self.screen}
            elif cmd == "launch":          # llmos desk-ctl launch <command line>
                first = arg.split()[0] if arg.split() else ""
                r = self.launch_app(["/bin/sh", "-c", arg], name=os.path.basename(first) or "app")
                out = {"ok": isinstance(r, int), "pid": r if isinstance(r, int) else None, "error": None if isinstance(r, int) else r}
            elif cmd == "lock":
                self.lock()
                out = {"ok": True}
            elif cmd == "testreset" and _fwcfg("testshell"):   # tests: the same clean state before every case
                self.decline_dialogs()
                for wid in list(self.windows):
                    self.close_window(wid)
                try:                          # program windows the last task left open (not the desk itself)
                    ext = [a for a in wm.windows() if a and a != "org.llmos.desk"]
                except Exception:
                    ext = []
                for aid in ext:
                    try:
                        wm.act("close", aid)
                    except Exception:
                        pass
                deadline = time.time() + 3
                while ext and time.time() < deadline:
                    time.sleep(0.2)
                    try:
                        ext = [a for a in wm.windows() if a and a != "org.llmos.desk" and a in ext]
                    except Exception:
                        ext = []
                for aid in ext:
                    if aid in NEVER_KILL or aid not in wm.PROCS:   # only known programs are force-quit
                        print("desk: testreset left %s open (unknown program)" % aid, file=sys.stderr)
                        continue
                    try:
                        wm.force_quit(aid)
                    except Exception:
                        pass
                for pid in list(self.apps):   # the programs the desk launched
                    try:
                        self.close_app(pid)
                    except Exception:
                        pass
                self._focus_desk()
                for k, v in (("autonomy", "balanced"), ("internet", "yes"), ("brain", "local"), ("guidance", "owner"), ("tor", False),
                             ("screen_off", 0), ("sleep_after", 0), ("do_not_disturb", False), ("language", "English"), ("autolock", 0)):
                    config.settings.set(k, v)
                self.apply_theme()            # (a test that changed the language must not leave the next one in Spanish)
                self.start_idle()             # tests drive the desk without touching the keyboard: the screen must stay on
                system.apply_firewall("yes")
                if self.screen == "lock":
                    self.unlock("x")
                record.stop()                 # (a recording one case started must not run on through the rest)
                self.chat().new_topic()
                self.last_reply = ""
                self.push_status()
                out = {"ok": True}
            elif cmd == "testreset-min" and _fwcfg("testshell"):   # tests: only close the open windows and start a new topic (no settings, no blanking)
                self.decline_dialogs()
                for wid in list(self.windows):
                    self.close_window(wid)
                try:                          # program windows the last task left open (not the desk itself)
                    ext = [a for a in wm.windows() if a and a != "org.llmos.desk"]
                except Exception:
                    ext = []
                for aid in ext:
                    try:
                        wm.act("close", aid)
                    except Exception:
                        pass
                deadline = time.time() + 3
                while ext and time.time() < deadline:
                    time.sleep(0.2)
                    try:
                        ext = [a for a in wm.windows() if a and a != "org.llmos.desk" and a in ext]
                    except Exception:
                        ext = []
                for aid in ext:
                    if aid in NEVER_KILL or aid not in wm.PROCS:   # only known programs are force-quit
                        print("desk: testreset left %s open (unknown program)" % aid, file=sys.stderr)
                        continue
                    try:
                        wm.force_quit(aid)
                    except Exception:
                        pass
                for pid in list(self.apps):   # the programs the desk launched
                    try:
                        self.close_app(pid)
                    except Exception:
                        pass
                self._focus_desk()
                self.chat().new_topic()
                self.last_reply = ""
                self.push_status()
                out = {"ok": True}
            elif cmd == "rect" and _fwcfg("testshell"):   # tests: "rect <id> <css selector>": the element's box on the page, for a real click
                words = line.split()
                rid = words[1] if len(words) > 1 else ""
                sel = " ".join(words[2:])
                ev = threading.Event()
                self._rect_wait[rid] = [ev, None]
                js = ('(function(){var e=document.querySelector(' + json.dumps(sel) + ');var r=e?e.getBoundingClientRect():null;'
                      'window.webkit.messageHandlers.llmos.postMessage({t:"rect.result",id:' + json.dumps(rid) + ',found:!!e,x:r?r.x:0,y:r?r.y:0,w:r?r.width:0,h:r?r.height:0,'
                      'text:e?(e.innerText||"").slice(0,500):"",value:e&&("value" in e)?String(e.value).slice(0,500):null,'
                      'dpr:window.devicePixelRatio,vw:window.innerWidth,vh:window.innerHeight});})()')
                self.emit({"t": "eval", "js": js})
                ev.wait(5)
                got = self._rect_wait.pop(rid, [ev, None])[1]
                out = got if got is not None else {"ok": False, "error": "timeout"}
            elif cmd == "rects" and _fwcfg("testshell"):   # tests: "rects <id> <css selector>": every match's box, text and state on the page
                words = line.split()
                rid = words[1] if len(words) > 1 else ""
                sel = " ".join(words[2:])
                ev = threading.Event()
                self._rect_wait[rid] = [ev, None]
                js = ('(function(){var post=function(m){window.webkit.messageHandlers.llmos.postMessage(m);};var list;'
                      'try{list=document.querySelectorAll(' + json.dumps(sel) + ');}catch(err){post({t:"rects.result",id:' + json.dumps(rid) + ',error:"bad selector"});return;}'
                      'var items=[];for(var i=0;i<list.length&&i<200;i++){var e=list[i];var r=e.getBoundingClientRect();'
                      'items.push({i:i,x:r.x,y:r.y,w:r.width,h:r.height,'
                      'text:String(e.innerText||e.value||e.getAttribute("aria-label")||e.title||"").slice(0,80),'
                      'tag:e.tagName.toLowerCase(),id:e.id,cls:String(e.className||"").slice(0,80),'
                      'visible:r.width>0&&r.height>0&&getComputedStyle(e).visibility!=="hidden",disabled:!!e.disabled});}'
                      'post({t:"rects.result",id:' + json.dumps(rid) + ',items:items,vw:window.innerWidth,vh:window.innerHeight,dpr:window.devicePixelRatio});})()')
                self.emit({"t": "eval", "js": js})
                ev.wait(5)
                got = self._rect_wait.pop(rid, [ev, None])[1]
                out = got if got is not None else {"ok": False, "error": "timeout"}
            elif cmd == "act":            # press a button by its words, as the page does (tests)
                self.act(arg)
                out = {"ok": True, "windows": [w.get("title", "") for w in self.windows.values()], "reply": getattr(self, "last_reply", "")}
            elif cmd == "focus":         # the Super key: the desk comes back in front of programs, ready to type
                self._focus_desk()
                out = {"ok": True}
            elif cmd == "js":
                self.emit({"t": "eval", "js": arg})
                out = {"ok": True}
            elif cmd == "dictating":       # llmos dictate (Super+D): show what dictation is doing; never takes focus
                state, _, note = arg.partition(" ")
                if state in ("listening", "transcribing"):
                    self.emit({"t": "toast", "text": T("d_dictate_" + state), "sticky": "dictate"})
                else:
                    self.emit({"t": "toast", "text": "", "sticky": "dictate"})
                    note = note.strip()
                    if note and note != "typed":
                        self.emit({"t": "toast", "text": T("d_dictate_note", note=note)})
                out = {"ok": True}
            else:
                out = {"error": "unknown command"}
            conn.sendall((json.dumps(out, ensure_ascii=False) + "\n").encode())
        except Exception as e:
            try:
                conn.sendall((json.dumps({"error": str(e)}) + "\n").encode())
            except OSError:
                pass
        finally:
            conn.close()


def control(argv):
    """`llmos say TEXT` / `llmos desk-state`: talk to the running desk."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCK)
    s.settimeout(900)
    s.sendall((" ".join(argv) + "\n").encode())
    data = b""
    while True:
        part = s.recv(65536)
        if not part:
            break
        data += part
        if data.endswith(b"\n"):
            break
    sys.stdout.write(data.decode("utf-8", "replace"))


def main():
    Desk().run()


if __name__ == "__main__":
    main()


class _QuietCtx(DeskCtx):
    """Re-runs a read-only tool to rebuild its window: everything but the window is silent."""

    def status(self, text):
        pass

    def begin_tool(self, *a, **k):
        pass

    def end_tool(self, *a, **k):
        pass

    def on_text(self, *a, **k):
        pass

    def show_ui(self, spec):
        return self.d.open_window(spec)
