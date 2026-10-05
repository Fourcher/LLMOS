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

from . import agent, config, i18n, llm, media, models, store, system, tools, ui, uispec, vault, voice, devices, version_line

T = i18n.t
PAGE = os.path.join(config.SHARE, "desk", "index.html")
# what the page may send while each screen other than the desk is showing: nothing typed or spoken on the
# lock screen, the first-run wizard or the boot screen may reach the assistant (anything else is dropped)
SCREEN_MESSAGES = {
    "boot": {"ready", "active"},
    "bye": {"ready", "active"},
    "lock": {"ready", "active", "unlock", "cancel"},
    "wizard": {"ready", "active", "wizard", "tz.search", "wifi.scan", "dialog", "cancel", "signin"},
}
SOCK = os.path.join(config.RUN, "desk.sock")
DISPLAY_ENV = os.path.join(config.RUN, "display.env")
def _wallpaper():
    """The wallpaper file: private data, so inside the vault when there is one."""
    return config.data("wallpaper.img")



# strings the page needs (everything else is rendered in Python)
_PAGE_KEYS = ("hint", "while_away", "passphrase", "wrong_passphrase", "unlocking", "locked", "welcome",
              "ask_language", "ask_name", "ask_timezone", "ask_autonomy", "ask_internet", "ask_tor",
              "ask_passphrase", "ask_passphrase_again", "passphrase_mismatch", "creating_vault", "onboard_done",
              "v_hands-off", "v_balanced", "v_hands-on", "v_yes", "v_no", "v_ask", "listening", "heard",
              "no_mic", "stopped", "error", "model_down", "loading_model", "shutting_down", "restarting",
              "allow", "d_stop", "d_history", "d_close", "d_minimize", "d_next", "d_back", "d_skip", "d_done",
              "d_unlock", "d_working", "d_apps", "d_close_app", "d_conversation", "d_you", "d_dont",
              "d_other_language", "d_open", "d_pause", "d_resume", "d_volume", "d_now_playing", "d_yes_start",
              "d_no_thanks", "d_type_language", "d_keep", "d_send", "d_clear", "d_shortcuts", "d_empty",
              "settings", "models", "tasks", "memory", "audit", "help_1", "help_2",
              "w_title", "w_text", "w_begin", "w_step", "w_recommended", "w_tz_search", "w_tz_hint", "w_net_title",
              "w_net_yes", "w_net_yes_d", "w_net_tor", "w_net_tor_d", "w_net_no", "w_net_no_d", "w_wifi_title",
              "w_wifi_none", "w_wifi_scan", "w_wifi_pass", "w_wifi_connect", "w_wifi_skip", "w_wifi_ok",
              "w_auto_off_d", "w_auto_bal_d", "w_auto_on_d", "w_pass_hint", "w_show", "w_hide", "w_done_title",
              "w_done_text", "w_finish", "d_try", "d_try_btn", "g_ex1", "g_ex2", "g_ex3", "g_ex4", "g_ex5", "g_ex6", "g_ex7", "g_ex8", "g_ex9", "g_ex10",
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
              "w_rec_this", "w_rec_other", "w_model_none", "w_model_tight", "w_cloud_signin", "w_cloud_signin_how", "w_cloud_waiting", "w_cloud_none",
              "w_cloud_ok", "w_cloud_paste", "w_cloud_done", "w_cloud_other",
              "w_cloud_check", "w_cloud_checking", "w_cloud_key", "w_cloud_model", "w_cloud_url", "w_cloud_key_where", "w_cloud_none_note",
              "w_done_choices", "v_brain_local", "v_brain_ask", "v_brain_cloud", "v_guidance_owner", "v_guidance_standard", "v_not_set_up",
              "d_brain_chip_ask", "d_online_tag", "v_yes", "v_ask", "v_no", "v_hands-off", "v_balanced", "v_hands-on",
              "d_usually", "d_left", "d_start_files", "d_shutdown_item", "models", "memory", "tasks", "d_history", "d_lists")

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
    subprocess.run(["iwctl", "station", dev, "scan"], capture_output=True, timeout=30)
    time.sleep(3)
    p = subprocess.run(["iwctl", "station", dev, "get-networks"], capture_output=True, text=True, timeout=30)
    nets, seen = [], set()
    for ln in re.sub(r"\x1b\[[0-9;]*m", "", p.stdout).splitlines():
        m = re.match(r"\s*(?:>\s*)?(.+?)\s{2,}(psk|open|8021x|wep)\s+(\**)", ln.strip(), re.I)
        if m and m.group(1).strip() not in seen and not m.group(1).startswith("-"):
            seen.add(m.group(1).strip())
            nets.append({"ssid": m.group(1).strip(), "secured": m.group(2).lower() != "open", "signal": len(m.group(3))})
    return nets


def _wifi_connect(ssid, password):
    dev = _wifi_device()
    if not dev:
        return False, "no Wi-Fi adapter"
    cmd = ["iwctl"] + (["--passphrase", password] if password else []) + ["station", dev, "connect", ssid]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        return False, (p.stderr or p.stdout).strip()[:200] or "could not connect"
    for _ in range(15):
        if _online():
            return True, ""
        time.sleep(1)
    return True, "connected, waiting for an address"


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb)


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
    (1 GB left for the system); offline, only those already here. Fast is the smallest (the installed one first),
    Balanced the largest of the quick ones, Most capable the largest. A tier that would repeat a model is dropped."""
    ram = models.ram_gb()
    inst = {m["id"] for m in models.installed()}
    fits = [m for m in models.catalog() if m["ram_gb"] <= ram - 1 and (allow_download or m["id"] in inst)]
    fits.sort(key=lambda m: (round(m["size"] / 1e9, 1), m["id"] not in inst))
    if not fits:
        # too little memory for any of them: the installed one is what runs anyway (slowly), so it is the choice
        here = sorted((m for m in models.catalog() if m["id"] in inst), key=lambda m: m["size"])
        return [{"tier": "fast", "id": m["id"], "name": m["name"], "need_gb": m["ram_gb"], "size_gb": round(m["size"] / 1e9, 1),
                 "installed": True, "tight": True} for m in here[:1]]
    quick = [m for m in fits if m.get("speed") in ("fast", "fastest")]
    out, seen = [], set()
    for tier, m in (("fast", fits[0]), ("balanced", (quick or fits)[-1]), ("capable", fits[-1])):
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        out.append({"tier": tier, "id": m["id"], "name": m["name"], "need_gb": m["ram_gb"],
                    "size_gb": round(m["size"] / 1e9, 1), "installed": m["id"] in inst})
    return out


def _recommend(sysinfo, tiers):
    """The choices this computer's specs suggest: models run on the processor, so Balanced only with 8+ cores and
    16 GB; the most capable is slow on a processor and is never the default. Lively motion only with hardware
    graphics (software rendering stutters)."""
    have = {t["tier"] for t in tiers}
    cap = "balanced" if sysinfo["cores"] >= 8 and sysinfo["ram_real"] >= 15 and "balanced" in have else "fast"
    return {"capability": cap if cap in have else (tiers[0]["tier"] if tiers else ""), "motion": 2 if sysinfo["accel"] else 1}


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
        return object()

    def on_text(self, stream, text):
        if self.cancel.is_set():
            raise agent.Cancelled()
        self.d.emit({"t": "reply.delta", "text": text})

    def end_stream(self, stream):
        pass

    def status(self, text):
        # a progress line from inside a tool updates that tool's activity line in place; other notes append
        self.d.emit({"t": "activity", "text": str(text), "replace": bool(getattr(self, "_tool_open", False))})

    def begin_tool(self, tool, args, risk):
        self._tool_open = True
        self.d.emit({"t": "activity", "text": self.d.describe_tool(tool, args)})

    def end_tool(self, tool, result):
        self._tool_open = False

    def progress(self, phase, done, total):
        self.d.emit({"t": "progress", "label": {"download": "downloading", "verify": "verifying"}.get(phase, phase),
                     "done": int(done), "total": int(total)})

    def background(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def confirm_network(self, name, args):
        if name in self._net_ok:
            return True
        host = str(args.get("url", "") or args.get("query", ""))[:80]
        ok = self.d.ask({"title": T("s_internet", area="settings"), "text": f"{name} → {host}", "danger": False})
        if ok:
            self._net_ok.add(name)
        return ok

    def confirm_action(self, tool, args, risk):
        return self.d.ask({"title": self.d.describe_tool(tool, args, confirm=True),
                           "text": self.d.describe_args(tool, args), "danger": risk in ("destructive", "security"),
                           "mono": tool.name in ("run_command", "install_app", "write_file")})

    def confirm_online(self, text, reason):
        """'ask' brain mode: one dialog before a request leaves this computer, saying what goes."""
        label = llm.cloud_label()
        why = T("d_online_failed") if reason == "failed" else T("d_online_big")
        return self.d.ask({"title": T("d_online_title", model=label), "text": why + "\n\n" + T("d_online_shares"),
                           "danger": False, "yes": T("d_online_yes", model=label), "no": T("d_online_no")})

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

    def signin(self, provider=None):
        """"sign in to Claude / ChatGPT": the service's key page in a window; the copied key comes in by itself."""
        pid = self._provider(provider) or "anthropic"
        if not (llm.CLOUD_PROVIDERS.get(pid) or {}).get("signin"):
            return self.setup_cloud(pid)
        self.d.GLib.idle_add(self.d._signin_open, pid)
        return (f"a sign-in window for {llm.CLOUD_PROVIDERS[pid]['name']} is open: the owner signs in, creates a key and "
                "presses Copy; the window then closes by itself and the key is checked automatically. Say one sentence at most.")

    def setup_cloud(self, provider=None):
        """"set up the online model": the connect panel (sign in to a service, nothing to type); for another
        service ("connect another online service") a form whose submit posts straight to the OS (the key never
        passes through a model)."""
        if str(provider or "").strip().lower() not in ("other", "other service", "openai-compatible", "openai compatible"):
            self.d.open_connect_panel()
            return "the connect panel is on the owner's screen: they sign in to a service there. Say one sentence at most."
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
        return "an online-model form is on the owner's screen; they fill it in there. Say one sentence at most."

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
        return "a connector form is on the owner's screen; they fill it in there. Say one sentence at most."

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
        return "the conduct editor is on the owner's screen; they edit it there. Say one sentence at most."

    def interactive(self, cmd):
        return self.d.run_in_terminal(cmd)

    def redraw(self):
        self.d.apply_theme()
        self.d.push_status()

    def show_panel(self, panel):
        self.d.open_panel(panel)

    def show_box(self, title, rows):
        self.d.open_window({"title": title, "blocks": [{"type": "text", "text": "\n".join(rows)}]})

    is_desk = True

    def setup_vault(self):
        """"set up a passphrase" after first boot: a form whose submit posts straight to the OS."""
        import secrets
        if config.settings.get("vault"):
            return "the vault already exists (say 'lock' to lock it); the passphrase cannot be changed from here"
        self.d.vault_nonce = secrets.token_hex(12)
        self.d.open_window({"id": "vault-form", "replace": True, "title": T("passphrase"), "size": "s", "slot": "cascade", "blocks": [
            {"type": "text", "text": T("ask_passphrase")},
            {"type": "form", "fields": [{"name": "p1", "label": T("passphrase"), "kind": "password"},
                                        {"name": "p2", "label": T("ask_passphrase_again"), "kind": "password"},
                                        {"name": "nonce", "kind": "hidden", "value": self.d.vault_nonce}],
             "submit": {"label": T("d_set_passphrase"), "post": "vault.create"}},
            {"type": "text", "text": T("w_pass_hint"), "dim": True}]})
        return "a passphrase form is on the owner's screen; they type it there. Say one sentence at most."

    def show_ui(self, spec):
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
            th = ui.Theme()
            bg = th.bg or (11, 13, 20)
            self.webview.set_background_color(Gdk.RGBA(red=bg[0] / 255, green=bg[1] / 255, blue=bg[2] / 255, alpha=1))
            self._apply_proxy()
            self.webview.load_uri("file://" + PAGE)
            win.set_child(self.webview)
            win.fullscreen()
            win.present()
            GLib.timeout_add(400, self._apply_zoom)
            try:
                Gdk.Display.get_default().get_monitors().connect("items-changed", lambda *a: GLib.timeout_add(600, self._apply_zoom))
            except Exception:
                pass
            self._write_display_env()
            threading.Thread(target=self._control_socket, daemon=True).start()
            threading.Thread(target=self._worker, daemon=True).start()
            GLib.timeout_add_seconds(20, self._poll_away)
            GLib.timeout_add_seconds(30, self._poll_autolock)

        self.app = Gtk.Application(application_id="org.llmos.desk")
        self.app.connect("activate", activate)
        os.makedirs(config.RUN, exist_ok=True)
        with open(os.path.join(config.RUN, "desk.pid"), "w") as f:
            f.write(str(os.getpid()))
        try:
            self.app.run(None)
        finally:
            self._cleanup()

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
        if self.screen != "desk" and t not in SCREEN_MESSAGES.get(self.screen, SCREEN_MESSAGES["boot"]):
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
        elif t == "say":
            self.last_active = time.time()
            self.say(str(msg.get("text", "")))
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
                        self.emit({"t": "toast", "text": f"{T('error')}: {e}", "long": True})
                threading.Thread(target=make, daemon=True).start()
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
                        note = f"{T('error')}: {e}"
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
                        with open(config.conduct_path(), "w", encoding="utf-8") as f:
                            f.write(text + "\n")
                        note = T("d_conduct_saved")
                    else:
                        try:
                            os.unlink(config.conduct_path())
                        except OSError:
                            pass
                        note = T("d_conduct_reset")
                    store.audit("edit_conduct", {"chars": len(text)}, "conduct edited by owner" if text else "conduct reset", who="owner")
                    if "panel-settings" in self.windows:
                        self.open_panel("settings")
                except OSError as e:
                    note = f"{T('error')}: {e}"
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
            self.ctx.cancel.set()
            self.decline_dialogs()
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
            pass
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
                "recommend": {"on": _recommend(sysinfo, tiers_on), "off": _recommend(sysinfo, tiers_off)},
                "cloud_providers": [{"id": k, "name": p["name"], "key_hint": p["key_hint"], "console": p["console"], "models": p["models"],
                                     "signin": bool(p.get("signin"))} for k, p in llm.CLOUD_PROVIDERS.items()]}

    def set_screen(self, name, data=None):
        self.screen = name
        self.emit({"t": "screen", "name": name, "data": data or {}})

    def enter_desk(self):
        self.last_active = time.time()
        self.set_screen("desk", {"name": config.Profile().get("name", "")})
        self.push_status()
        self._model_watch()
        self.show_away()

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
        corners = th.corners if th.corners in ("rounded", "square", "double", "heavy", "none") else "rounded"
        css["--radius"] = {"rounded": "14px", "square": "0px", "none": "24px", "double": "6px", "heavy": "8px"}[corners]
        css["--radius-sm"] = {"rounded": "9px", "square": "0px", "none": "16px", "double": "4px", "heavy": "5px"}[corners]
        css["--border-w"] = {"double": "3px", "heavy": "2px"}.get(corners, "1px")
        css["--border-style"] = "double" if corners == "double" else "solid"
        motion = getattr(th, "motion", "full")
        lang = i18n.lang_code(config.llm_language())
        strings = {k: T(k) for k in _PAGE_KEYS}
        strings.update({k: T(k, area="settings") for k in ("settings",)})
        mode = "light" if (th.bg and ui._lum(th.bg) > 0.4) else "dark"
        return {"t": "theme", "css": css, "mode": mode, "corners": corners, "lang": lang, "motion": motion,
                "layout": config.settings.get("appearance.layout") or "clean",
                "software": os.environ.get("LIBGL_ALWAYS_SOFTWARE") == "1",
                "dir": "rtl" if lang in ("ar", "he", "fa", "ur") else "ltr", "strings": strings,
                "wallpaper": ("file://" + _wallpaper() + "?" + str(int(os.path.getmtime(_wallpaper())))) if (config.settings.get("onboarded") and (not config.settings.get("vault") or vault.unlocked()) and os.path.exists(_wallpaper())) else ""}

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
        self.emit(self.theme_payload())
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
                   "autonomy": s.get("autonomy", "hands-off"), "host_gpu": models.host_mode(),
                   "brain": s.get("brain", "local"), "cloud": llm.cloud_label() if vault.unlocked() or not s.get("vault") else "",
                   "tor": bool(s.get("tor")), "internet": s.get("internet", "yes"),
                   "vault": ("locked" if not vault.unlocked() else "on") if s.get("vault") else "off",
                   "focus": bool(s.get("focus", {}).get("on")), "name": config.Profile().get("name", ""),
                   "tz": system.timezone(), "busy": self.busy, "listening": self.listening,
                   "mic": voice.available(), "tasks": len(store.tasks())})

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

    def open_panel(self, which):
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
            auto = s.get("autonomy", "hands-off")
            pick = lambda k, v: {"label": L(k), "say": v}
            blocks = [
                {"type": "heading", "text": L("s_autonomy")},
                {"type": "choices", "selected": L("v_" + auto), "items": [
                    {"label": L("v_hands-off"), "say": "switch to hands-off mode"},
                    {"label": L("v_balanced"), "say": "switch to balanced mode"},
                    {"label": L("v_hands-on"), "say": "switch to hands-on mode"}]},
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
                {"type": "buttons", "items": [{"label": L("c_purple"), "say": "make everything purple"}, {"label": L("c_teal"), "say": "make everything teal"},
                                              {"label": L("c_orange"), "say": "make everything orange"}, {"label": L("c_green"), "say": "make everything green"},
                                              {"label": L("c_light"), "say": "make the background white and the text black"},
                                              {"label": L("v_default"), "say": "make everything default"}]},
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
            examples = [T(f"g_ex{i}") for i in range(1, 11)]
            return {"title": T("d_try"), "kind": "panel", "size": "l", "blocks": [
                {"type": "text", "text": T("g_intro")},
                {"type": "buttons", "items": [{"label": T("settings", area="settings"), "say": "settings"},
                                              {"label": T("models"), "say": "models"}, {"label": T("tasks"), "say": "tasks"},
                                              {"label": T("memory"), "say": "memory"}, {"label": T("d_lists"), "say": "show my lists"},
                                              {"label": T("audit"), "say": "audit"}]},
                {"type": "list", "columns": 2, "items": [{"title": f"“{e}”", "actions": [{"label": T("d_try_btn"), "say": e}]} for e in examples]},
                {"type": "text", "text": T("d_shortcuts"), "dim": True}]}
        return None

    def show_away(self):
        try:
            st = os.stat(config.data("inbox.json"))
            key = (st.st_mtime_ns, st.st_size)
        except OSError:
            key = None
        if key == getattr(self, "_inbox_key", "unset"):
            return
        self._inbox_key = key
        un = store.unseen()
        if not un:
            return
        items = [{"title": m["title"], "detail": ui.strip(m["text"])[:1200]} for m in un[-8:]]
        self.open_window({"id": "away", "replace": True, "title": T("while_away"), "size": "m", "slot": "cascade",
                          "blocks": [{"type": "list", "items": items}]})
        self.away_ids = [m["id"] for m in un]          # marked seen when the owner closes the card
        if getattr(self, "ready", False):
            self.emit({"t": "toast", "text": ui.strip(un[-1]["text"])[:120] or un[-1]["title"], "long": True})
            devices.chime()
            if config.settings.get("speak_replies"):
                self.ctx.background(lambda t=ui.strip(un[-1]["text"])[:400]: voice.speak(t))

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

    def ask(self, spec):
        if self.ctx.cancel.is_set():      # the owner pressed Stop: nothing more is allowed this turn
            return False
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
        for d in list(self.dialogs.values()):
            d[1] = "no"
            d[0].set()

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
        s = json.dumps(a, ensure_ascii=False)
        s = s if len(s) < 70 else s[:67] + "…"
        return (f"Allow {n}?" if confirm else f"{n} {s}")

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

    def say(self, text, done=None):
        """Queue a request; `done` (an Event) is set when its turn is over."""
        text = text.strip()
        if not text:
            if done:
                done.set()
            return
        self.last_active = time.time()
        self.requests.put((text, done))

    def _worker(self):
        while True:
            text, done = self.requests.get()
            try:
                self.turn(text)
            except Exception as e:      # never let the worker die
                self.emit({"t": "reply.error", "text": f"{T('error')}: {e}"})
            finally:
                self.turn_done.set()
                if done:
                    done.set()

    def shortcut(self, line):
        low = line.lower().strip()
        if low in ("settings", "models", "tasks", "memory", "audit", "help", "?"):
            self.open_panel("help" if low == "?" else low)
            return True
        if low == "clear":
            self.history.clear()
            for wid in list(self.windows):
                self.close_window(wid)
            self.emit({"t": "clear"})
            return True
        if low == "lock" and config.settings.get("vault"):
            self.lock()
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

    def turn(self, text):
        if self.shortcut(text):
            self.history.append({"role": "user", "content": text})
            self.history.append({"role": "assistant", "content": "(done)"})
            return
        self.busy = True
        self.ctx.after_turn = None
        self.ctx.cancel.clear()
        self.last_activity = []
        self.sources = []
        self.emit({"t": "reply.start", "request": text})
        self.push_status()
        final = ""
        try:
            final = agent.run(self.ctx, text, self.history)
            self.emit({"t": "reply.end", "text": final})
            if final and config.settings.get("speak_replies"):
                self.emit({"t": "speaking", "on": True})
                try:
                    voice.speak(final)
                finally:
                    self.emit({"t": "speaking", "on": False})
        except llm.ModelError as e:
            self.emit({"t": "reply.error", "text": f"{T('error')}: {e}"})
        except llm.ModelDown:
            self.emit({"t": "reply.error", "text": T("model_down")})
        except agent.Cancelled:
            self.emit({"t": "reply.error", "text": T("stopped")})
        except Exception as e:
            self.emit({"t": "reply.error", "text": f"{T('error')}: {e}"})
        finally:
            self.busy = False
            self.last_reply = final
            self.push_status()
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

    def _session_pids(self):
        """Every process of this desk session except the compositor, the desk itself and its WebKit helpers."""
        mine, keep = os.getpid(), set()
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
            if display and (b"WAYLAND_DISPLAY=" + display.encode()) in env.split(b"\0") and \
                    comm not in ("labwc", "python3", "WebKitWebProcess", "WebKitNetworkProcess", "seatd", "dbus-daemon", "at-spi2-registryd", "at-spi-bus-launcher", "xdg-dbus-proxy") \
                    and not comm.startswith("llmos"):
                out.append(int(d))
        return out

    def _keybinds(self, enabled):
        """While locked the compositor keeps no shortcuts (no new terminal, no Alt-Tab to an old one)."""
        cfg = os.path.join(os.environ.get("XDG_CONFIG_HOME", "/var/cache/llmos"), "labwc")
        try:
            os.makedirs(cfg, exist_ok=True)
            rc = os.path.join(cfg, "rc.xml")
            if enabled:
                if os.path.exists(rc):
                    os.unlink(rc)
            else:
                with open("/etc/xdg/labwc/rc.xml") as f:
                    xml = f.read()
                xml = re.sub(r"<keyboard>.*?</keyboard>", '<keyboard><keybind key="W-A-C-S-F24"><action name="None"/></keybind></keyboard>',
                             xml, flags=re.S)
                xml = re.sub(r"<mouse>.*?</mouse>", '<mouse><context name="Root"><mousebind button="Right" action="Press"><action name="None"/>'
                             '</mousebind></context></mouse>', xml, flags=re.S)
                with open(rc, "w") as f:
                    f.write(xml)
            subprocess.run(["labwc", "--reconfigure"], capture_output=True, timeout=10, env=self._child_env())
        except Exception as e:
            sys.stderr.write(f"desk: keybinds not switched: {e}\n")

    def lock(self):
        self.lock_stuck = False
        self.ctx.cancel.set()               # a turn in progress stops; nothing queued runs behind the lock
        self.decline_dialogs()
        while True:
            try:
                _, done = self.requests.get_nowait()
            except queue.Empty:
                break
            if done:
                done.set()
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
        self.history.clear()
        self.set_screen("lock", {"note": note})
        self.push_status()

    def unlock(self, passphrase):
        # only from the lock screen (a repeat that arrives after the desk opened is not a failed attempt), one at
        # a time; vault.unlock checks the passphrase against the header even when the vault is still mounted
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
        os.system("poweroff" if how == "poweroff" else "reboot")

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
                if want and any(x["id"] == want for x in _model_tiers(net_pol != "no")):
                    pick = next((m for m in models.catalog() if m["id"] == want), None)
                else:
                    fits = sorted([m for m in models.catalog() if m["ram_gb"] <= ram - 1 and (net_pol != "no" or m["id"] in inst)],
                                  key=lambda m: round(m["size"] / 1e9, 1))
                    if fits:
                        pick = fits[0] if cap < 34 else fits[len(fits) // 2] if cap < 67 else fits[-1]
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
                config.settings.set("autonomy", v if v in ("hands-off", "balanced", "hands-on") else "hands-off")
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
            err(f"{T('error')}: {e}")

    # ---- apps and terminals (windows in the compositor)

    def _child_env(self):
        env = dict(os.environ, MOZ_ENABLE_WAYLAND="1", GDK_BACKEND="wayland", QT_QPA_PLATFORM="wayland",
                   SDL_VIDEODRIVER="wayland", XDG_SESSION_TYPE="wayland")
        env.update(config.personal_env())
        return env

    def launch_app(self, argv, name=""):
        log = open(os.path.join(config.RUN, "gui.log"), "a")
        try:
            p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True, env=self._child_env(), cwd="/")   # never inside the vault
        except OSError as e:
            return f"could not start {argv[0]}: {e}"
        name = name or os.path.basename(argv[0])
        self.apps[p.pid] = {"name": name, "popen": p, "argv": argv}
        self._push_apps()
        threading.Thread(target=self._reap, args=(p,), daemon=True).start()
        return p.pid

    def _reap(self, p):
        p.wait()
        self.apps.pop(p.pid, None)
        self._push_apps()

    def _push_apps(self):
        self.emit({"t": "apps", "items": [{"pid": pid, "name": a["name"]} for pid, a in self.apps.items()]})

    def close_app(self, pid):
        a = self.apps.get(pid)
        if not a:
            return
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass

    def run_in_terminal(self, cmd):
        """Interactive programs and !commands get a terminal window."""
        if not shutil.which("foot"):
            return 127
        script = f"cd \"$HOME\" 2>/dev/null; {cmd}; printf '\\n[{T('d_done')} — Enter]'; read _x"
        self.launch_app(["foot", "--title", cmd[:60], "-e", "/bin/sh", "-c", script], name=cmd.split()[0][:20])
        return 0

    # ---- media (mpv as a window, controlled over its IPC socket)

    def media_action(self, action, **kw):
        if action == "play":
            info = media.find(kw.get("query", ""))
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
                "queued": self.requests.qsize(),
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
            elif cmd == "wait":            # until nothing is running or queued
                for _ in range(int(arg or 600)):
                    if not self.busy and self.requests.empty():
                        break
                    time.sleep(1)
                out = self._state()
            elif cmd == "dialog":          # answer every pending confirmation (tests)
                for did, d in list(self.dialogs.items()):
                    d[1] = arg or "yes"
                    d[0].set()
                    self.emit({"t": "dialog.close", "id": did})
                out = {"ok": True}
            elif cmd == "cancel":
                self.ctx.cancel.set()
                self.decline_dialogs()
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
