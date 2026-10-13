#!/usr/bin/env python3
"""Host-side test of the set-up's on-device model choices at four memory sizes (llmos/desk.py): the slider's tiers
are as before where models fit; with nothing that fits, the slider has one stop, the smallest model, marked as
running from disk ("bigger"); "More models" (all_models) lists every allowed model with the same flags; and the
chat pick accepts any allowed model id, including one that runs from disk. Memory, the catalog and the installed set
are patched; no VM, no firewall change. Run: python3 tools/test-model-tiers.py"""
import os
import sys
import tempfile
import types

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import desk, models  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


RAM = [15.3]
INSTALLED = {"ministral-3-3b"}
models.ram_gb = lambda: RAM[0]
models.installed = lambda: [m for m in models.catalog() if m["id"] in INSTALLED]
desk.system.apply_firewall = lambda policy: None      # the chat pick runs the set-up's profile step; never touch the host's firewall
CAT = {m["id"]: m for m in models.catalog()}

# (memory GB, online tier ids, offline tier ids) as the set-up offered them before this change, with the installed model
EXPECT = {
    3.5: (["hermes-3-3b"], ["ministral-3-3b"]),                      # nothing fits: the one slow stop
    7.6: (["ministral-3-3b", "gemma-4-e4b"], ["ministral-3-3b"]),
    15.3: (["ministral-3-3b", "lfm2.5-8b-a1b", "ministral-3-14b"], ["ministral-3-3b"]),
    31.0: (["ministral-3-3b", "lfm2.5-8b-a1b", "underdog-27b"], ["ministral-3-3b"]),
}

for ram, (want_on, want_off) in EXPECT.items():
    RAM[0] = ram
    print(f"{ram} GB memory")
    on, off = desk._model_tiers(True), desk._model_tiers(False)
    got_on, got_off = [t["id"] for t in on], [t["id"] for t in off]
    if ram == 3.5:
        check(got_on == want_on and len(on) == 1 and on[0]["bigger"] and not on[0]["installed"],
              f"tiers online: one slow stop {got_on}")
        check(got_off == want_off and off[0]["bigger"] and off[0]["installed"],
              f"tiers offline: the installed model, slow {got_off}")
    else:
        check(got_on == want_on, f"tiers online as before {got_on}")
        check(got_off == want_off, f"tiers offline as before {got_off}")
        check(all(not t.get("bigger") for t in on + off), "nothing fitting is marked running from disk")
    check(all(set(t) >= {"tier", "id", "name", "need_gb", "size_gb", "installed"} and "tight" not in t for t in on + off),
          "every tier has its fields; no old 'tight' flag")

    for allow, label in ((True, "online"), (False, "offline")):
        allowed = {m["id"] for m in models.catalog() if allow or m["id"] in INSTALLED}
        allm = desk._model_all(allow)
        check({m["id"] for m in allm} == allowed, f"all_models {label}: every allowed model ({len(allm)})")
        check(all(m["bigger"] == (CAT[m["id"]]["ram_gb"] > ram - 1) for m in allm),
              f"all_models {label}: bigger = needs more than memory minus 1 GB")
        check(all(m["need_gb"] == CAT[m["id"]]["ram_gb"] and m["installed"] == (m["id"] in INSTALLED) for m in allm),
              f"all_models {label}: need and installed are right")
        keys = [(m["bigger"], CAT[m["id"]]["size"]) for m in allm]
        check(keys == sorted(keys), f"all_models {label}: fitting models first, then by size")

# the chat pick: the set-up's profile step with a named model
print("the chat pick takes any allowed model")
RAM[0] = 3.5
INSTALLED = {"ministral-3-3b"}
events = []
ctx = types.SimpleNamespace(emit=events.append, apply_theme=lambda: None, wizard_model=None)


def profile(model, internet):
    events.clear()
    ctx.wizard_model = None
    desk.Desk.wizard_step(ctx, "profile", {"autonomy": 0, "internet": internet, "brain": 0, "capability": 50,
                                               "guidance": 0, "motion": 100, "model": model})
    return events[-1] if events else {}


ev = profile("underdog-27b", 0)                       # online: a model that runs from disk on 3.5 GB
check(ev.get("model") == CAT["underdog-27b"]["name"] and ctx.wizard_model == "underdog-27b",
      f"online: the 20 GB model is accepted and set to download {ev.get('model')!r}")
ev = profile("hermes-3-3b", 0)
check(ev.get("model") == CAT["hermes-3-3b"]["name"] and ctx.wizard_model == "hermes-3-3b", "online: the slow stop's model is accepted")
ev = profile("underdog-27b", 100)                      # offline: only installed models can be chosen
check(ctx.wizard_model is None or ctx.wizard_model != "underdog-27b", "offline: a model that is not installed is not accepted")
check(ev.get("model") == CAT["ministral-3-3b"]["name"], f"offline: falls back to the installed model {ev.get('model')!r}")
ev = profile("ministral-3-3b", 100)
check(ev.get("model") == CAT["ministral-3-3b"]["name"] and ctx.wizard_model is None, "offline: the installed model is the pick, nothing to download")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
