#!/usr/bin/env python3
"""Host-side test of the owner's data files (llmos/store.py, config.py): the desk, the console and the scheduler
are separate processes that change the same files, so concurrent changes must all survive; and while the vault is
closed nothing personal may be written to the bare disk below it. Run: python3 tools/test-store.py (no VM)"""
import multiprocessing
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = tempfile.mkdtemp(prefix="llmos-etc-")   # /etc/llmos: not under the home folder
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import config, store  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


def writer(k, n):
    for i in range(n):
        store.add_note(f"item {k}-{i}", "shopping")


print("concurrent changes from separate processes are all kept")
mp = multiprocessing.get_context("fork")      # the OS forks too (Linux); macOS would otherwise re-run this file
procs = [mp.Process(target=writer, args=(k, 25)) for k in range(6)]
for p in procs:
    p.start()
for p in procs:
    p.join()
texts = {n.get("text") for n in store.notes()}
check(len(texts) == 150, f"6 processes x 25 notes -> {len(texts)} kept (150 expected)")

print("while the vault is closed, nothing personal is written under the home folder")
config.settings.set("vault", True)          # a vault that is not mounted (there is none on this host)
before = set(os.listdir(config.data_dir()))
try:
    store.add_note("written while locked", "shopping")
    wrote = "no error"
except OSError as e:
    wrote = str(e)
check("vault is locked" in wrote, f"a change is refused: {wrote}")
store.audit("test", {}, "x")
check(set(os.listdir(config.data_dir())) == before, "the audit line is not written to the bare disk either")
check(all(n.get("text") != "written while locked" for n in store.notes()), "the note is not there")
config.settings.set("vault", False)
store.add_note("after unlock", "shopping")
check(any(n.get("text") == "after unlock" for n in store.notes()), "writes work again once the vault is open")

print("all good" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
