#!/usr/bin/env python3
"""Host-side test of models bigger than the machine's memory (no network, no VM): use() proceeds with a disclosed
note instead of refusing, serve_argv() never pins memory or disables mmap for such a model and uses the smallest
context, and a model that fits keeps the argv it always had. Run: python3 tools/test-models-large.py"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import config, models, system  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


GGUF = tempfile.NamedTemporaryFile(delete=False, suffix=".gguf")
GGUF.close()
SIZE = 3_000_000_000                      # about 2.8 GB of weights
NOTE = "This model is bigger than memory (4 GB vs 2.0 GB). It will run from disk, much slower."
calls = []


def fake_service(*a, **kw):
    calls.append((a, kw))
    return 0


def model(ram):
    return {"id": "test-large", "name": "Test Large", "file": "x.gguf", "size": SIZE, "ram_gb": ram}


def argv_for(m, mem):
    """serve_argv() with a fixed memory size and CPU count, for the active model m."""
    real = models.ram_gb, models.active, models.path_of, os.cpu_count
    models.ram_gb = lambda: mem
    models.active = lambda: m
    models.path_of = lambda _m: GGUF.name
    os.cpu_count = lambda: 4
    try:
        return models.serve_argv()
    finally:
        models.ram_gb, models.active, models.path_of, os.cpu_count = real


def use_with(m, mem):
    real = models.by_id, models.host_mode, models.ram_gb, models.path_of, system.service
    models.by_id = lambda mid: m if mid == m["id"] else None
    models.host_mode = lambda: False
    models.ram_gb = lambda: mem
    models.path_of = lambda _m: GGUF.name
    system.service = fake_service
    calls.clear()
    try:
        return models.use(m["id"])
    finally:
        models.by_id, models.host_mode, models.ram_gb, models.path_of, system.service = real


# expected argv for a model that fits (8 GB machine, 4 GB model): recorded from the code before this change
FITS_ARGV = ["llama-server", "-m", GGUF.name, "--host", "127.0.0.1", "--port", "8080",
             "--jinja", "-c", "16384", "-t", "4", "-np", "1",
             "--no-webui", "--no-slots", "--cache-reuse", "256", "--cache-ram", "1024"]

# 1. a model bigger than memory: use() proceeds, one service restart, the note is attached
big = model(4)
out = use_with(big, 2.0)
check(calls == [(("llmos-model", "restart"), {"timeout": 60})], f"use big: service restart called once: {calls!r}")
check(out.get("bigger_than_ram_note") == NOTE, f"use big: note text: {out.get('bigger_than_ram_note')!r}")
check(out["id"] == "test-large", "use big: returns the model with its id")
check(config.settings.get("model") == "test-large", "use big: model id stored")

# 2. serve_argv for that model: no memory pinning, no mmap off, smallest context
a = argv_for(big, 2.0)
check("--mlock" not in a and "--no-mmap" not in a, f"serve big: no --mlock/--no-mmap: {a}")
check(a[a.index("-c") + 1] == "4096", f"serve big: context 4096: {a[a.index('-c') + 1]}")
check(a[a.index("--cache-ram") + 1] == "0", "serve big: cache-ram 0 (no spare memory)")

# 3. exactly equal to memory: fits, no note, argv as before
eq = model(4)
out = use_with(eq, 4.0)
check("bigger_than_ram_note" not in out and out is eq, "use equal-to-RAM: no note, same dict returned")
check(argv_for(eq, 4.0)[argv_for(eq, 4.0).index("-c") + 1] == "4096", "serve equal-to-RAM: context 4096 (spare 0.2)")

# 4. a model that fits: use() returns the same object as before, argv byte-identical to before
fit = model(4)
out = use_with(fit, 8.0)
check(out is fit and "bigger_than_ram_note" not in out, "use fits: same dict, no note")
got = argv_for(fit, 8.0)
check(got == FITS_ARGV, f"serve fits: argv identical to before: {got}")

# 5. RAM unknown (ram_gb() == 0): use() refuses exactly as before; serve_argv gives the old argv for it
try:
    use_with(model(4), 0)
    check(False, "use unknown RAM: refused as before")
except ValueError as e:
    check("needs about 4 GB of memory; this machine has 0.0 GB" in str(e), f"use unknown RAM: refused as before: {e}")
check(calls == [], "use unknown RAM: service not restarted")
a = argv_for(model(4), 0)
check("--mlock" not in a and "--no-mmap" not in a and a[a.index("-c") + 1] == "4096", f"serve unknown RAM: {a}")

os.unlink(GGUF.name)
print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
