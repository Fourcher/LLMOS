#!/usr/bin/env python3
"""The shipped model, the tier list and the empty-setting fallback agree.

Hermes 3 3B is the file preinstall.env fetches (the small model a 4 GB machine can run).
At 4 GB the fast tier is that model. At 16 GB Dolphin and Huihui, the uncensored models,
appear in the tier list, and Ministral 3 14B stays selectable. With no model chosen,
active() is Dolphin, then Huihui, when they are installed and fit, else Hermes.
No download, no llama-server. Run: python3 tools/test-default-model.py
"""
import os
import sys
import tempfile
from unittest import mock

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import config, desk, models  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


def env_file():
    out = {}
    with open(os.path.join(_ROOT, "usr/share/llmos/preinstall.env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
    return out


hermes = models.by_id(models.SHIPPED_MODEL)
env = env_file()
check(hermes is not None and hermes["id"] == "hermes-3-3b", "catalog has Hermes 3 3B")
check(env.get("MODEL_FILE") == hermes["file"] and env.get("MODEL_SHA256") == hermes["sha256"],
      f"preinstall.env is the Hermes file and hash ({env.get('MODEL_FILE')})")
check("Ministral-3-3B" not in env.get("MODEL_FILE", ""), "preinstall.env does not fetch Ministral 3 3B")
check("checksum mismatch" in open(os.path.join(_ROOT, "usr/lib/llmos/llmos/models.py"), encoding="utf-8").read(),
      "models.download still rejects a checksum mismatch")

CAT = {m["id"]: m for m in models.catalog()}
RAM = [4.0]
INSTALLED = set()
models.ram_gb = lambda: RAM[0]
models.installed = lambda: [m for m in models.catalog() if m["id"] in INSTALLED]

print("4 GB")
RAM[0] = 4.0
INSTALLED = set()
on = desk._model_tiers(True)
check(on and on[0]["tier"] == "fast" and on[0]["id"] == "hermes-3-3b",
      f"4 GB, nothing installed: fast tier is Hermes {[t['id'] for t in on]}")
INSTALLED = {"hermes-3-3b", "ministral-3-3b"}
on = desk._model_tiers(True)
check(on and on[0]["id"] == "hermes-3-3b",
      f"4 GB, Hermes and Ministral installed: fast tier is still Hermes {[t['id'] for t in on]}")
check("dolphin-3-8b" not in {t["id"] for t in on} and "huihui-ornith-1.5-9b" not in {t["id"] for t in on},
      "4 GB: Dolphin and Huihui do not fit the tier list")

print("16 GB")
RAM[0] = 16.0
INSTALLED = set()
on = desk._model_tiers(True)
ids = [t["id"] for t in on]
check("dolphin-3-8b" in ids and "huihui-ornith-1.5-9b" in ids, f"16 GB: Dolphin and Huihui are in the tier list {ids}")
check(ids.index("dolphin-3-8b") < ids.index("huihui-ornith-1.5-9b"), "16 GB: Dolphin comes before Huihui")
allm = {m["id"]: m for m in desk._model_all(True)}
check("ministral-3-14b" in allm and not allm["ministral-3-14b"]["bigger"],
      "16 GB: Ministral 3 14B is still selectable and is not marked running from disk")

desk.system.apply_firewall = lambda policy: None
events = []
ctx = type("C", (), {})()
ctx.emit = events.append
ctx.apply_theme = lambda: None
ctx.wizard_model = None
events.clear()
desk.Desk.wizard_step(ctx, "profile", {"autonomy": 0, "internet": 0, "brain": 0, "capability": 100,
                                        "guidance": 0, "motion": 100, "model": "ministral-3-14b"})
check(ctx.wizard_model == "ministral-3-14b", f"16 GB: the set-up accepts Ministral 3 14B ({ctx.wizard_model})")

print("active() with no chosen model")
config.settings.set("model", "")


def chosen(ram, installed):
    rows = [CAT[i] for i in installed]
    with mock.patch.object(models, "host_mode", return_value=False), \
            mock.patch.object(models, "ram_gb", return_value=ram), \
            mock.patch.object(models, "installed", return_value=rows):
        return (models.active() or {}).get("id")


check(chosen(4, ["ministral-3-3b", "hermes-3-3b"]) == "hermes-3-3b",
      "4 GB, both small models installed: Hermes, not the first catalog entry")
check(chosen(4, ["hermes-3-3b"]) == "hermes-3-3b", "4 GB, only the shipped model: Hermes")
check(chosen(16, ["hermes-3-3b", "dolphin-3-8b", "huihui-ornith-1.5-9b"]) == "dolphin-3-8b",
      "16 GB, Dolphin installed and it fits: Dolphin")
check(chosen(16, ["hermes-3-3b", "huihui-ornith-1.5-9b"]) == "huihui-ornith-1.5-9b",
      "16 GB, Dolphin absent, Huihui fits: Huihui")
check(chosen(16, ["hermes-3-3b"]) == "hermes-3-3b", "16 GB, neither uncensored model installed: Hermes")
check(chosen(8, ["dolphin-3-8b", "hermes-3-3b"]) == "hermes-3-3b",
      "8 GB: Dolphin does not leave 1 GB spare, so the shipped model is used")
config.settings.set("model", "ministral-3-14b")
check(chosen(16, ["hermes-3-3b", "dolphin-3-8b", "ministral-3-14b"]) == "ministral-3-14b",
      "an explicit choice still wins")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
