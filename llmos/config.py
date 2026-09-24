"""Paths and runtime flags. Everything can be redirected with env vars so the
whole system can run unprivileged on a development machine."""
import os

RUN = os.environ.get("LLMOS_RUN", "/run/llmos")
DATA_MOUNT = os.environ.get("LLMOS_DATA_MOUNT", "/data")
DATA = os.path.join(DATA_MOUNT, "llmos")
SOCK = os.path.join(RUN, "sock")
LIB = os.environ.get("LLMOS_LIB", "/usr/lib/llmos")
SYS_MEDIA = os.environ.get("LLMOS_SYS_MEDIA", "/run/llmos/sys")
LLM_HOST = os.environ.get("LLMOS_LLM_HOST", "127.0.0.1")
LLM_PORT = int(os.environ.get("LLMOS_LLM_PORT", "8080"))
LLM_CTX = int(os.environ.get("LLMOS_LLM_CTX", "4096"))
LLAMA_SERVER = os.environ.get("LLMOS_LLAMA_SERVER", "llama-server")


def cmdline():
    try:
        with open("/proc/cmdline") as f:
            return f.read().split()
    except OSError:
        return []


def flag(name):
    """True if llmos.<name> is on the kernel command line or LLMOS_<NAME>=1."""
    if os.environ.get("LLMOS_" + name.upper()) == "1":
        return True
    return ("llmos." + name) in cmdline()


FAKE_HW = flag("fakehw")
DEV = os.environ.get("LLMOS_DEV") == "1"  # running outside the real OS


def models_json():
    for p in (os.path.join(LIB, "models.json"),
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models.json")):
        if os.path.exists(p):
            return p
    raise FileNotFoundError("models.json")


def data_ready():
    return os.path.isdir(DATA)


def dpath(*parts):
    return os.path.join(DATA, *parts)


def rpath(*parts):
    return os.path.join(RUN, *parts)
