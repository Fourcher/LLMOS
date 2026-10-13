#!/usr/bin/env python3
"""Host-side test of the owner-facing wording in llmos/tools.py: tool results must not use the technical words
'firewall error' or 'GGUF files' or 'the model's own caution'; they say 'couldn't change it', 'model files' and
'the assistant's own caution' instead. Checks the source text, then calls the affected tool functions with the
config and firewall patched and checks the returned text. Run: python3 tools/test-tools-words.py (no VM)."""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ["LLMOS_HOME"] = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_ETC"] = tempfile.mkdtemp(prefix="llmos-etc-")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import tools  # noqa: E402

SRC = open(os.path.join(_ROOT, "usr/lib/llmos/llmos/tools.py"), encoding="utf-8").read()
fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


OLD = ["firewall error", "GGUF files", "the model keeps its own caution", "the model's own caution"]
NEW = ["(couldn't change it: {err})", "its model files are:", "the assistant keeps its own caution",
       "the assistant's own caution"]
for phrase in OLD:
    check(phrase not in SRC, f"old phrase gone from tools.py: {phrase!r}")
for phrase in NEW:
    check(SRC.count(phrase) == 1, f"new phrase present once in tools.py: {phrase!r}")


class Ctx:
    current_request = ""
    is_desk = False

    def status(self, *_a, **_k):
        pass

    def redraw(self):
        pass


class Settings:
    def set(self, key, value):
        pass

    def all(self):
        return {}

    def get(self, key, default=None):
        return default


class Firewall:
    def __init__(self, ok, err):
        self.ok, self.err = ok, err

    def __call__(self, v=None):
        return self.ok, self.err


real_settings, real_fw, real_hf = tools.config.settings, tools.system.apply_firewall, tools._hf_json
tools.config.settings = Settings()
try:
    tools._hf_json = lambda url, timeout=20: [{"path": "model-Q4_K_M.gguf", "size": 5}]
    got = tools.add_model({"repo": "owner/name", "file": "nope.gguf"}, Ctx())
    want = "error: 'nope.gguf' is not in owner/name; its model files are: model-Q4_K_M.gguf"
    check(got == want, f"add_model unknown file says model files: {got!r}")

    tools.system.apply_firewall = Firewall(False, "boom")
    got = tools.change_setting({"setting": "internet", "value": "yes"}, Ctx())
    check(got == "internet is now 'yes' (couldn't change it: boom)", f"internet failure wording: {got!r}")

    tools.system.apply_firewall = Firewall(True, "")
    got = tools.change_setting({"setting": "internet", "value": "yes"}, Ctx())
    check(got == "internet is now 'yes'", f"internet success wording: {got!r}")

    got = tools.change_setting({"setting": "guidance", "value": "standard"}, Ctx())
    check(got == "guidance is now 'standard': the assistant keeps its own caution", f"guidance standard: {got!r}")

    got = tools.change_setting({"setting": "guidance", "value": "bogus"}, Ctx())
    check(got == "error: guidance must be 'owner' (does what you ask on your machine) or "
                 "'standard' (the assistant's own caution)", f"guidance error: {got!r}")
finally:
    tools.config.settings = real_settings
    tools.system.apply_firewall = real_fw
    tools._hf_json = real_hf

print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
