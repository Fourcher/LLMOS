"""Paths and persistent state.

Two stores:
  public  /etc/llmos/settings.json  -- look, language, autonomy, model. Needed
                                        before the vault is unlocked (to draw the
                                        unlock screen in the user's language).
  private ~/.llmos/*                  -- who the user is, memory, tasks, inbox,
                                        audit log, mail account. Lives inside the
                                        encrypted vault when the user enabled one.
"""
import contextlib
import errno
import fcntl
import json
import os
import tempfile
import threading

ETC = os.environ.get("LLMOS_ETC", "/etc/llmos")
LIB = os.environ.get("LLMOS_LIB", "/var/lib/llmos")
SHARE = os.environ.get("LLMOS_SHARE", "/usr/share/llmos")
RUN = os.environ.get("LLMOS_RUN", "/run/llmos")
MODELS = os.path.join(LIB, "models")
HOST_MODEL_URL_FILE = os.path.join(RUN, "model_url")   # written by llmos-model in host mode
HOST_MODEL_ID_FILE = os.path.join(RUN, "model_id")


def llama_url():
    """Where the model server is. Normally the guest's own llama-server on
    127.0.0.1; under a VM launcher with host-GPU mode it is the host's server,
    reached over the VM's private link (still this machine, still offline)."""
    env = os.environ.get("LLMOS_LLAMA_URL")
    if env:
        return env
    try:
        with open(HOST_MODEL_URL_FILE) as f:
            url = f.read().strip()
        if url.startswith("http://"):
            return url
    except OSError:
        pass
    return "http://127.0.0.1:8080"


def host_model_id():
    try:
        with open(HOST_MODEL_ID_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def conduct_path():
    """The owner-editable conduct section of the assistant's system prompt (plain text). Public, like
    settings.json, so it can be edited from a terminal too. Absent by default (the OS uses a built-in
    default); present only when the owner has written their own. The OS never writes it on its own."""
    return os.path.join(ETC, "conduct.txt")


def home():
    return os.environ.get("LLMOS_HOME") or os.path.expanduser("~")


def personal_env():
    """For programs the owner runs (a browser, a terminal, a player): their caches and settings go to the home
    folder -- inside the vault when there is one -- not to /var/cache/llmos, where the desk keeps its own (so that
    locking can unmount the vault). Locking closes those programs first."""
    h = home()
    return {"HOME": h, "XDG_CACHE_HOME": os.path.join(h, ".cache"), "XDG_CONFIG_HOME": os.path.join(h, ".config")}


def vault_closed():
    """The owner has a vault and it is not open: nothing personal may be written to the bare disk below it
    (a scheduled task still running when the screen locked, a console left open)."""
    try:
        if not settings.get("vault"):
            return False
        from . import vault
        return not vault.unlocked()
    except Exception:
        return False


def data_dir():
    d = os.path.join(home(), ".llmos")
    if not vault_closed():
        os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def guard_write(path):
    """Refuse to write personal data under the home folder while the vault is closed (fail closed)."""
    if vault_closed() and os.path.abspath(path).startswith(home().rstrip("/") + "/"):
        raise OSError(errno.EACCES, "the vault is locked: personal data is not written outside it", path)


_lock_depth = threading.local()


@contextlib.contextmanager
def data_lock():
    """Serialise a read-modify-write of the owner's data files across processes (the desk, the console and the
    scheduler each run their own) and threads. Re-entrant within a thread."""
    if getattr(_lock_depth, "n", 0):
        _lock_depth.n += 1
        try:
            yield
        finally:
            _lock_depth.n -= 1
        return
    path = os.path.join(data_dir(), ".lock")
    guard_write(path)
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        _lock_depth.n = 1
        try:
            yield
        finally:
            _lock_depth.n = 0
            fcntl.flock(f, fcntl.LOCK_UN)


def data(name):
    return os.path.join(data_dir(), name)


PUBLIC_DEFAULTS = {
    "onboarded": False,
    "language": "English",
    "settings_language": "",        # "" = same as language
    "autonomy": "balanced",         # hands-off | balanced | hands-on (balanced: asks before anything irreversible)
    "internet": "yes",              # yes | ask | no
    "tor": False,
    "model": "",                    # catalog id; "" = whatever is installed
    "think": False,                 # let the model reason before answering
    "appearance": {
        "color": "",                # text color ("" = terminal default)
        "background": "",           # background color ("" = terminal default)
        "accent": "",               # prompt / frames / highlights
        "corners": "rounded",       # rounded | square | none
        "prompt": "›",
        "scale": 100,               # text/interface size on the desk, percent
        "motion": "full",           # animations on the desk: full | reduced | off
        "font": "sans",             # sans | serif | mono | pixel (themes.FONTS)
        "backdrop": "living",       # behind the windows: living (animated) | still | photo (the wallpaper) | plain
        "layout": "clean",          # the desk's arrangement: clean (LLM OS) | windows (taskbar + start menu) | mac (menu bar + dock)
    },
    "speak_replies": False,
    "guidance": "owner",            # owner: does what the owner asks on their machine, no lectures | standard: the model's own caution
    "brain": "local",               # where requests are answered: local (this computer only) | ask (here; asks before a big one goes
                                    # to the online model) | cloud (the online model for everything; here when it can't be reached)
    "profile": {},                  # the first-run sliders (0-100 each), kept for reference
    "vault": False,
    "focus": {"on": False, "until": 0},
}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj, mode=0o600):
    guard_write(path)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _merge(defaults, value):
    out = dict(defaults)
    for k, v in (value or {}).items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings:
    """Public settings, re-read on every access so all consoles and the
    scheduler agree without any IPC."""

    path = os.path.join(ETC, "settings.json")

    _cache = (None, None)

    def all(self):
        # re-read whenever the file changed (all consoles and the scheduler agree), parsed once otherwise
        try:
            st = os.stat(self.path)
            key = (st.st_mtime_ns, st.st_size)
        except OSError:
            key = None
        cache_key, cached = Settings._cache
        if key is not None and key == cache_key and cached is not None:
            return cached
        val = _merge(PUBLIC_DEFAULTS, load_json(self.path, {}))
        Settings._cache = (key, val)
        return val

    def get(self, key, default=None):
        cur = self.all()
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def set(self, key, value):
        cur = load_json(self.path, {})
        node = cur
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        save_json(self.path, cur, mode=0o644)


settings = Settings()


class Profile:
    """Private facts about the user (inside the vault)."""

    def __init__(self):
        self.path = data("profile.json")

    def get(self, key, default=None):
        return load_json(self.path, {}).get(key, default)

    def set(self, key, value):
        cur = load_json(self.path, {})
        cur[key] = value
        save_json(self.path, cur)


# ---- the optional online model: an account the owner adds. Private (inside the vault with the rest
# of the owner's data), so it is unreachable while the vault is locked, like everything else of theirs.

def cloud():
    """{"provider", "url", "model", "key"} or None when no account is set up."""
    c = load_json(data("cloud.json"), None)
    if not isinstance(c, dict) or not c.get("key") or not c.get("model"):
        return None
    return c


def save_cloud(c):
    save_json(data("cloud.json"), c)


def forget_cloud():
    try:
        os.unlink(data("cloud.json"))
    except OSError:
        pass


def llm_language(area=None):
    """Language for an area of the interface ('settings' can differ)."""
    s = settings.all()
    if area == "settings" and s.get("settings_language"):
        return s["settings_language"]
    return s.get("language") or "English"
