#!/usr/bin/env python3
"""Host-side test of what the first-run set-up works out from the computer itself (llmos/desk.py): the screen's
scale from its pixels per inch, the on-device models behind Fast / Balanced / Most capable for its memory, and the
choices its specs suggest; and that every string the set-up page shows exists in all six languages, with the same
{placeholders}. Run: python3 tools/test-setup-wizard.py  (no VM needed)."""
import os
import re
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import desk, i18n, models  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Mon:
    """A screen as GTK describes it: its width in millimetres and in the compositor's pixels."""
    def __init__(self, mm, px):
        self.mm, self.px = mm, px

    def get_width_mm(self):
        return self.mm

    def get_geometry(self):
        return type("R", (), {"width": self.px})()


print("the screen's scale, the way a PC picks its default")
for name, mm, px, want in (("24-inch 1080p monitor", 531, 1920, 1.0), ("27-inch 1440p monitor", 597, 2560, 1.0),
                           ("15.6-inch 1080p laptop", 344, 1920, 1.25), ("14-inch 1080p laptop", 309, 1920, 1.5),
                           ("13.3-inch 1080p laptop", 294, 1920, 1.5), ("27-inch 4K monitor", 597, 3840, 1.5),
                           ("13-inch 2560x1600 laptop", 286, 2560, 2.0), ("15.6-inch 4K laptop", 344, 3840, 2.0),
                           ("old 15.6-inch 1366x768 laptop", 344, 1366, 1.0),
                           ("a VM (no size)", 0, 1280, 1.0), ("a TV that says 160 cm", 1600, 3840, 1.0), ("a nonsense 1 cm", 10, 1920, 1.0),
                           ("a 4K laptop the compositor already scales 2x", 344, 1920, 1.25)):
    got = desk._display_scale(Mon(mm, px))
    check(got == want, f"{name}: {int(got * 100)}%")
check(desk._display_scale(None) == 1.0, "no screen information: 100%")

print("on-device model choices from this computer's memory")
installed = {"ministral-3-3b"}
models.ram_gb = lambda: RAM[0]
models.installed = lambda: [m for m in models.catalog() if m["id"] in installed]
RAM = [15.3]
on, off = desk._model_tiers(True), desk._model_tiers(False)
names = {t["tier"]: t["name"] for t in on}
check([t["tier"] for t in on] == ["fast", "balanced", "capable"], f"16 GB: three tiers {names}")
check(on[0]["installed"] and on[0]["id"] == "ministral-3-3b", "Fast is the installed model (ready at once)")
check(all(t["need_gb"] <= 15.3 - 1 for t in on), "every choice fits the memory with 1 GB left for the system")
check(all(not t.get("tight") for t in on), "nothing is marked tight when it fits")
check([t["id"] for t in off] == ["ministral-3-3b"], "offline: only what is already installed")
rec = desk._recommend({"cores": 8, "ram_real": 15.3, "accel": True}, on)
check(rec == {"capability": "balanced", "motion": 2}, f"8 cores, 16 GB, real graphics: Balanced, full animation {rec}")
rec = desk._recommend({"cores": 4, "ram_real": 15.3, "accel": False}, on)
check(rec == {"capability": "fast", "motion": 1}, f"4 cores, no graphics acceleration: Fast, gentle animation {rec}")
check(desk._recommend({"cores": 16, "ram_real": 31, "accel": True}, on)["capability"] != "capable", "Most capable is never the default (slow on a processor)")
RAM[0] = 7.6
on = desk._model_tiers(True)
check(1 <= len(on) <= 3 and all(t["need_gb"] <= 6.6 for t in on), f"8 GB: {[(t['tier'], t['name']) for t in on]}")
check(len({t["id"] for t in on}) == len(on), "no model offered twice")
RAM[0] = 3.7
on = desk._model_tiers(True)
check(len(on) == 1 and on[0]["id"] == "ministral-3-3b" and on[0].get("tight"), "4 GB: the installed model, marked as tight (slow) instead of nothing")
check(desk._recommend({"cores": 2, "ram_real": 3.7, "accel": False}, on)["capability"] == "fast", "4 GB: Fast")
installed = set()
check(desk._model_tiers(False) == [], "nothing installed and offline: no choice (the page says so)")

print("the set-up page's strings, in every language")
src = open(os.path.join(_ROOT, "usr/share/llmos/desk/desk.js"), encoding="utf-8").read()
start, end = src.index("const wizard = {"), src.index("// ---------------------------------------------------------------- windows")
wiz = src[start:end]
used = set(re.findall(r'\bt\("([a-z0-9_]+)"', wiz)) | set(re.findall(r'\bfmt\("([a-z0-9_]+)"', wiz))
used = {k for k in used if not k.endswith("_")}      # t("q_" + q.k): a prefix, its keys are checked below
for tpl in re.findall(r"t\(`([a-z0-9_]*)\$\{[^}]+\}([a-z0-9_]*)`\)", wiz):     # t(`q_${q.k}_${i}_s`) and the like
    pre, post = tpl
    used |= {k for k in i18n.EN if k.startswith(pre) and k.endswith(post)}
page = set(desk._PAGE_KEYS)
check(not (used - page - {"settings"}), f"every string the wizard uses is sent to the page {sorted(used - page)}")
for code, tab in i18n.BUILTIN.items():
    missing = sorted(k for k in used if k in i18n.EN and k not in tab)
    ph = sorted(k for k in used if k in i18n.EN and k in tab and set(re.findall(r"\{\w+\}", i18n.EN[k])) != set(re.findall(r"\{\w+\}", tab[k])))
    check(not missing and not ph, f"{code}: all {len([k for k in used if k in i18n.EN])} wizard strings, same placeholders {missing or ''}{ph or ''}")
for k in ("q_autonomy", "q_internet", "q_brain", "q_capability", "q_guidance", "q_motion"):
    n = 2 if k == "q_guidance" else 3
    check(all(f"{k}_{i}_s" in i18n.EN and f"{k}_{i}" in i18n.EN for i in range(n)), f"{k}: a label and a meaning for each of its {n} choices")

print("connecting an online model: which window each request opens")
import types  # noqa: E402
opened = []
stub = types.SimpleNamespace(open_connect_panel=lambda: opened.append("panel"), open_window=lambda spec: opened.append(spec["id"]), cloud_nonce="")
ctx = types.SimpleNamespace(d=stub, _provider=desk.DeskCtx._provider)
for prov, want in ((None, "panel"), ("claude", "panel"), ("chatgpt", "panel"), ("openai", "panel"), ("other", "cloud-form")):
    opened.clear()
    desk.DeskCtx.setup_cloud(ctx, prov)
    check(opened == [want], f"set up with provider {prov!r}: {want}")
from llmos import intent, tools  # noqa: E402
got = intent.match("connect another online service")
opened.clear()
desk.DeskCtx.setup_cloud(ctx, got[1].get("provider"))
check(opened == ["cloud-form"], "the panel's 'Another service (paste a key)' opens the form, not the panel again")
check(desk.DeskCtx._provider("Claude") == "anthropic" and desk.DeskCtx._provider("OpenAI") == "chatgpt" and desk.DeskCtx._provider("x") == "",
      "sign-in names: Claude -> anthropic, ChatGPT/OpenAI -> chatgpt")

print("what the owner reads when the OS answers these itself (no notes meant for the model)")
from llmos import agent  # noqa: E402
R = agent._shortcut_reply
opened.clear()
sctx = types.SimpleNamespace(d=types.SimpleNamespace(GLib=types.SimpleNamespace(idle_add=lambda fn, pid: opened.append(("signin", pid))),
                                                     _signin_open=None), _provider=desk.DeskCtx._provider)
check(R("online_model", {}, desk.DeskCtx.signin(sctx, "chatgpt")) == "Sign in there, create a key and press Copy next to it; the window closes by itself."
      and opened == [("signin", "chatgpt")], "sign in to ChatGPT: the window opens; the reply says what to do there")
check(R("online_model", {}, desk.DeskCtx.setup_cloud(ctx, None)) == "Here it is.", "the connect panel: 'Here it is.'")
check(R("online_model", {}, desk.DeskCtx.setup_cloud(ctx, "other")) == "Here it is.", "the other-service form: 'Here it is.'")
for out in ("the trash is empty (2 item(s) deleted for good). Say one sentence at most.",
            "3 item(s) in ~ are listed on the owner's screen; do not repeat them, say one sentence at most.",
            "shown: the Alps (CC BY). Source: https://x. Say one sentence at most; do not describe the photo."):
    check("sentence" not in R("anything", {}, out).lower(), f"no model note: {R('anything', {}, out)!r}")

tool = types.SimpleNamespace(name="online_model")
labels = [desk.Desk.describe_tool(None, tool, {"action": "sign in", "provider": "chatgpt"}),
          desk.Desk.describe_tool(None, tool, {"action": "set up", "provider": "other"}),
          desk.Desk.describe_tool(None, tool, {"action": "forget"}, confirm=True)]
check(labels == ["sign in to ChatGPT", "connect an online model", "Forget the online model?"] and not any("{" in x for x in labels),
      f"the activity line says it in words, not raw arguments {labels}")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
