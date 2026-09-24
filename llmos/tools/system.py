import os
import re
import signal
import subprocess
import time

from .. import config, hw, theme, i18n
from . import tool, ToolError, s, i, b, arr, obj, R, C, D, E, N

DESTRUCTIVE = re.compile(
    r"(\brm\s+(-\w*[rf]\w*\s+)*|\bmkfs|\bdd\s|\bcryptsetup\b|\bfdisk\b|\bsfdisk\b|\bsgdisk\b|\bparted\b|"
    r"\bwipefs\b|\bshred\b|\bpoweroff\b|\breboot\b|\bshutdown\b|\bhalt\b|\bapk\s+del\b|>\s*/data|"
    r"\bkill(all)?\b|\bpkill\b|\bchmod\s+-R|\bchown\s+-R|\btruncate\b|\bmv\s)")
UPLOAD = re.compile(r"(\bcurl\b.*\s(-T|--upload-file|-F|--form|-d|--data\S*)\s|\bscp\b|\brsync\b.*:|\bnc\b|\bncat\b|\bsftp\b|\bssh\b|\bmail\b|\bsendmail\b)")
NETWORK = re.compile(r"\b(curl|wget|git|apk\s+(add|update|upgrade|fetch)|yt-dlp|ping|nslookup|dig|pip|npm)\b")


def shell_class(args):
    cmd = args.get("cmd", "")
    if DESTRUCTIVE.search(cmd):
        return D
    if UPLOAD.search(cmd):
        return E
    if NETWORK.search(cmd):
        return N
    return C


def run_cmd(ctx, cmd, timeout_s=60, env=None, stdin=None):
    """Run a shell command as root, interruptible by the user."""
    e = dict(os.environ)
    e.update(ctx.net_env() if ctx else {})
    if env:
        e.update(env)
    p = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                         env=e, start_new_session=True)
    if stdin is not None:
        try:
            p.stdin.write(stdin.encode())
            p.stdin.close()
        except OSError:
            pass
    deadline = time.time() + max(1, int(timeout_s))
    while p.poll() is None:
        if ctx and ctx.cancelled():
            os.killpg(p.pid, signal.SIGKILL)
            raise ToolError("stopped by user")
        if time.time() > deadline:
            os.killpg(p.pid, signal.SIGKILL)
            out = p.stdout.read().decode(errors="replace")
            raise ToolError("timed out after %ss\n%s" % (timeout_s, out[-1500:]))
        time.sleep(0.05)
    out = p.stdout.read().decode(errors="replace")
    return p.returncode, out


@tool("shell", "Run any shell command as root (busybox + Alpine Linux). Use for anything no other tool covers.",
      {"cmd": s(), "timeout_s": i(minimum=1, maximum=3600)}, ["cmd"], klass=shell_class)
def shell(ctx, cmd, timeout_s=120):
    rc, out = run_cmd(ctx, cmd, timeout_s)
    out = out.strip() or "(no output)"
    if rc != 0:
        raise ToolError("exit %d\n%s" % (rc, out[-3000:]))
    return out


@tool("set_brightness", "Set screen brightness in percent.", {"percent": i(minimum=0, maximum=100)}, klass=C)
def set_brightness(ctx, percent):
    return hw.set_brightness(percent)


@tool("set_volume", "Set sound volume in percent, or mute/unmute.",
      {"percent": i(minimum=0, maximum=100), "mute": b()}, [], klass=C)
def set_volume(ctx, percent=None, mute=None):
    if percent is None and mute is None:
        v, m = hw.get_volume()
        return "volume %d%%%s" % (v, " (muted)" if m else "")
    return hw.set_volume(percent, mute)


@tool("set_theme", "Change how everything looks. patch keys: palette{bg,fg,accent,muted,error,ok or all} as colour names or #hex, "
      "corners rounded|square|none, font, font_size, padding, density compact|normal|roomy, theme light|dark|default.",
      {"patch": obj()}, klass=C)
def set_theme(ctx, patch):
    try:
        new, restart = theme.apply_patch(ctx.theme(), patch)
    except (ValueError, TypeError) as e:
        raise ToolError(str(e))
    ctx.set_theme(new, restart)
    return "theme now: " + theme.summary(new)


@tool("set_language", "Set the language of the whole interface (section all) or one section: settings, system, answers, errors, prompts.",
      {"lang": s(), "section": s(enum=["all", "settings", "system", "answers", "errors", "prompts"])}, ["lang"], klass=C)
def set_language(ctx, lang, section="all"):
    code = i18n.code(lang)
    if section == "all":
        patch = {"lang": {"default": code, "sections": {}}}
        t = ctx.theme()
        t["lang"]["sections"] = {}
    else:
        patch = {"lang": {"sections": {section: code}}}
    new, _ = theme.apply_patch(ctx.theme() if section != "all" else t, patch)
    ctx.set_theme(new, False)
    if not i18n.has(code):
        ctx.translate_strings(code)
    return "%s is now %s" % ("interface" if section == "all" else section, i18n.name(code))


@tool("set_profile", "Change how much the computer may do without asking: autonomous, balanced or careful.",
      {"profile": s(enum=["autonomous", "balanced", "careful"])}, klass=C)
def set_profile(ctx, profile):
    ctx.perms.set_profile(profile)
    return "profile " + profile


@tool("power", "Shut down, reboot, or lock the screen (lock asks for the passphrase again).",
      {"action": s(enum=["shutdown", "reboot", "lock"])}, klass=lambda a: C if a.get("action") == "lock" else D)
def power(ctx, action):
    if action == "lock":
        ctx.lock()
        return "locked"
    ctx.after_turn(lambda: subprocess.Popen(["/sbin/" + ("poweroff" if action == "shutdown" else "reboot")]))
    return action + " in a moment"


@tool("install_package", "Install Alpine Linux packages (apk). persist=true reinstalls them at every boot.",
      {"names": arr(s(), minItems=1, maxItems=10), "persist": b()}, ["names"], klass=N)
def install_package(ctx, names, persist=False):
    ctx.require_network()
    bad = [n for n in names if not re.fullmatch(r"[A-Za-z0-9._+-]+", n)]
    if bad:
        raise ToolError("bad package name %s" % bad)
    rc, out = run_cmd(ctx, "apk add --no-progress " + " ".join(names), 900)
    if rc != 0:
        raise ToolError(out[-1500:])
    if persist and config.data_ready():
        p = config.dpath("packages")
        have = set(open(p).read().split()) if os.path.exists(p) else set()
        with open(p, "w") as f:
            f.write("\n".join(sorted(have | set(names))) + "\n")
    return "installed " + " ".join(names)


@tool("notify", "Leave a short note the user sees at their next prompt (use in scheduled tasks).", {"text": s()}, klass=R)
def notify(ctx, text):
    ctx.notify(text)
    return "noted"


@tool("ask_user", "Ask the user one short question when the request is truly ambiguous. Ends your turn.",
      {"question": s(), "choices": arr(s(), maxItems=6)}, ["question"], klass=R)
def ask_user(ctx, question, choices=None):
    return ctx.ask_user(question, choices or [])


@tool("system_info", "Battery, memory, disk, uptime, time, network mode, active model.", {}, klass=R)
def system_info(ctx):
    lines = []
    try:
        for bat in os.listdir("/sys/class/power_supply"):
            p = "/sys/class/power_supply/" + bat
            if os.path.exists(p + "/capacity"):
                lines.append("battery %s%% %s" % (open(p + "/capacity").read().strip(),
                                                   open(p + "/status").read().strip().lower()))
    except OSError:
        pass
    try:
        mem = dict(l.split(":", 1) for l in open("/proc/meminfo"))
        tot = int(mem["MemTotal"].split()[0]) // 1024
        av = int(mem["MemAvailable"].split()[0]) // 1024
        lines.append("memory %d MB free of %d MB" % (av, tot))
    except (OSError, KeyError, ValueError):
        pass
    try:
        st = os.statvfs(config.DATA_MOUNT if os.path.isdir(config.DATA_MOUNT) else "/")
        lines.append("storage %.1f GB free" % (st.f_bavail * st.f_frsize / 1e9))
    except OSError:
        pass
    try:
        up = float(open("/proc/uptime").read().split()[0])
        lines.append("uptime %dh%02dm" % (up // 3600, up % 3600 // 60))
    except OSError:
        pass
    lines.append("time " + time.strftime("%Y-%m-%d %H:%M %Z"))
    lines.append("brightness %d%%" % hw.get_brightness())
    v, m = hw.get_volume()
    lines.append("volume %d%%%s" % (v, " muted" if m else ""))
    lines.append("network " + ctx.net_mode())
    lines.append("model " + ctx.model_name())
    lines.append("profile " + ctx.perms.profile)
    return "\n".join(lines)
