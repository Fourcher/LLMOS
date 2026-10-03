"""Paths and persistent state.

Two stores:
  public  /etc/llmos/settings.json  -- look, language, autonomy, model. Needed
                                        before the vault is unlocked (to draw the
                                        unlock screen in the user's language).
  private ~/.llmos/*                  -- who the user is, memory, tasks, inbox,
                                        audit log, mail account. Lives inside the
                                        encrypted vault when the user enabled one.
"""
import json
import os
import tempfile

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


def home():
    return os.environ.get("LLMOS_HOME") or os.path.expanduser("~")


def data_dir():
    d = os.path.join(home(), ".llmos")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def data(name):
    return os.path.join(data_dir(), name)


PUBLIC_DEFAULTS = {
    "onboarded": False,
    "language": "English",
    "settings_language": "",        # "" = same as language
    "autonomy": "hands-off",        # hands-off | balanced | hands-on
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
    },
    "speak_replies": False,
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

    def all(self):
        return _merge(PUBLIC_DEFAULTS, load_json(self.path, {}))

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


def llm_language(area=None):
    """Language for an area of the interface ('settings' can differ)."""
    s = settings.all()
    if area == "settings" and s.get("settings_language"):
        return s["settings_language"]
    return s.get("language") or "English"
