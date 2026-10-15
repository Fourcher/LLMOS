#!/usr/bin/env python3
"""Host-side test of models bigger than the machine's memory (no network, no VM): use() proceeds with a disclosed
note instead of refusing, serve_argv() never pins memory or disables mmap for such a model and uses the smallest
context, and a model that fits keeps the argv it always had. The manage_models tool reply carries the note.
Run: python3 tools/test-models-large.py"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import config, llm, models, system, tools  # noqa: E402

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
UNKNOWN_NOTE = ("I couldn't read how much memory this computer has, so I can't tell if it fits. "
                "If it's too big it will run from disk, slower.")
calls = []


def fake_service(*a, **kw):
    calls.append((a, kw))
    return 0


def fake_wait_ready(*a, **kw):
    return None


llm.wait_ready = fake_wait_ready          # the tool waits for the model server; there is none on the host


class Ctx:
    def status(self, t):
        pass

    def progress(self, *a, **k):
        pass

    def show_panel(self, *a, **k):
        pass


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


def use_with(m, mem, call=None):
    """Run models.use (or call(id), e.g. the manage_models tool) for model m on a machine with mem GB."""
    real = models.by_id, models.host_mode, models.ram_gb, models.path_of, system.service
    models.by_id = lambda mid: m if mid == m["id"] else None
    models.host_mode = lambda: False
    models.ram_gb = lambda: mem
    models.path_of = lambda _m: GGUF.name
    system.service = fake_service
    calls.clear()
    try:
        return (call or models.use)(m["id"])
    finally:
        models.by_id, models.host_mode, models.ram_gb, models.path_of, system.service = real


def tool_use(m, mem):
    return use_with(m, mem, lambda mid: tools.manage_models({"action": "use", "model": mid}, Ctx()))


# expected argv for a model that fits (8 GB machine, 4 GB model): recorded from the code before this change
FITS_ARGV = ["llama-server", "-m", GGUF.name, "--host", "127.0.0.1", "--port", "8080",
             "--jinja", "-c", "16384", "-t", "4", "-np", "1",
             "--no-webui", "--no-slots", "--cache-reuse", "256", "--cache-ram", "1024", "-ngl", "0"]

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

# 5. RAM unknown (ram_gb() == 0 or None): use() proceeds with the unknown-memory note, no exception, one restart
for unknown in (0, None):
    try:
        out = use_with(model(4), unknown)
        check(out.get("bigger_than_ram_note") == UNKNOWN_NOTE and out["id"] == "test-large",
              f"use unknown RAM ({unknown!r}): proceeds with the unknown-memory note")
    except Exception as e:  # noqa: BLE001
        check(False, f"use unknown RAM ({unknown!r}): raised {e!r}")
    check(calls == [(("llmos-model", "restart"), {"timeout": 60})],
          f"use unknown RAM ({unknown!r}): service restarted once: {calls!r}")
a = argv_for(model(4), 0)
check("--mlock" not in a and "--no-mmap" not in a and a[a.index("-c") + 1] == "4096", f"serve unknown RAM: {a}")

# 6. a catalog entry that already has a 'note' field keeps it; the disclosure goes in its own key
cat = dict(model(4), note="Catalog note")
out = use_with(cat, 2.0)
check(out.get("note") == "Catalog note" and out.get("bigger_than_ram_note") == NOTE,
      f"use big, catalog note kept: note={out.get('note')!r}")
out = use_with(dict(model(4), note="Catalog note"), 0)
check(out.get("note") == "Catalog note" and out.get("bigger_than_ram_note") == UNKNOWN_NOTE,
      f"use unknown RAM, catalog note kept: note={out.get('note')!r}")
fit_note = dict(model(4), note="Catalog note")
out = use_with(fit_note, 8.0)
check(out is fit_note and "bigger_than_ram_note" not in out and out["note"] == "Catalog note",
      "use fits with catalog note: same dict, no disclosure")

# 7. the manage_models tool: the reply carries the note for a big model; a fitting model's reply is unchanged
reply = tool_use(model(4), 2.0)
check(reply == f"now using Test Large. {NOTE}", f"tool use big: reply carries the note: {reply!r}")
reply = tool_use(model(4), 8.0)
check(reply == "now using Test Large", f"tool use fits: reply unchanged: {reply!r}")
reply = tool_use(model(4), 0)
check(reply == f"now using Test Large. {UNKNOWN_NOTE}" and not reply.startswith("error"),
      f"tool use RAM 0: unknown-memory note, no error: {reply!r}")

# 8. download(): free disk below the need is refused with the exact message; free disk equal to the need is not
#    refused (the curl call is replaced by a stop, so nothing is ever fetched)
class Reached(Exception):
    pass


def fake_popen(cmd, *a, **kw):
    raise Reached(cmd)


NEED = SIZE / 1024 ** 3 + 0.5
real_dl = models.by_id, models.host_mode, models.path_of, models.free_disk_gb, models._read_only, models.subprocess.Popen
models.by_id = lambda mid: dict(model(4), repo="example/none") if mid == "test-large" else None
models.host_mode = lambda: False
models.path_of = lambda _m: os.path.join(home, "absent.gguf")   # not on disk, so download() goes on to the disk check
models._read_only = lambda p: False
models.subprocess.Popen = fake_popen
real_models_dir = config.MODELS
config.MODELS = os.path.join(home, "models")                        # the temp home, never the real models folder
try:
    models.free_disk_gb = lambda path=None: 1.0
    try:
        models.download("test-large")
        check(False, "download low disk: no refusal")
    except ValueError as e:
        check(str(e) == f"not enough free disk: need {NEED:.1f} GB, have 1.0 GB", f"download low disk: refused with exact text: {e}")
    models.free_disk_gb = lambda path=None: NEED                    # exactly equal: allowed
    try:
        models.download("test-large")
        check(False, "download equal disk: did not reach the fetch")
    except Reached as e:
        check("curl" in e.args[0], "download equal disk: not refused, reached the fetch")
    except ValueError as e:
        check(False, f"download equal disk: refused: {e}")
finally:
    models.by_id, models.host_mode, models.path_of, models.free_disk_gb, models._read_only, models.subprocess.Popen = real_dl
    config.MODELS = real_models_dir

# 9. manage_models list: the note only on rows bigger than memory; none when memory is unknown
cat_models = [dict(model(4), maker="m", origin="o", license="l", note="n", size=SIZE),
              dict(model(16), id="big-one", name="Big", maker="m", origin="o", license="l", note="n", size=SIZE)]
real_list = models.catalog, models.installed, models.active, models.ram_gb
models.catalog = lambda: cat_models
models.installed = lambda: []
models.active = lambda: None
models.host_mode = lambda: False
try:
    models.ram_gb = lambda: 8.0
    rows = tools.manage_models({"action": "list"}, Ctx()).split("\n")
    small_row = next(r for r in rows if r.startswith("test-large:"))
    big_row = next(r for r in rows if r.startswith("big-one:"))
    check("runs from disk, slow" not in small_row, f"list fits (4 GB model, 8 GB RAM): no note")
    check("needs 16 GB RAM, runs from disk, slow, n [" in big_row, f"list bigger (16 GB model, 8 GB RAM): note in row: {big_row!r}")
    models.ram_gb = lambda: 16.0
    rows = tools.manage_models({"action": "list"}, Ctx()).split("\n")
    check("runs from disk" not in next(r for r in rows if r.startswith("big-one:")), "list exactly equal (16 GB model, 16 GB RAM): no note")
    models.ram_gb = lambda: 0
    rows = tools.manage_models({"action": "list"}, Ctx()).split("\n")
    check(not any("runs from disk" in r for r in rows), "list RAM unknown (0): no note on any row")
finally:
    models.catalog, models.installed, models.active, models.ram_gb = real_list

# 10. add_model: the note only when the new model is bigger than memory (RAM known); equal and unknown get none
real_add = tools._hf_json, models.add_catalog_entry, models.ram_gb
SHA = "a" * 64
tree = [{"path": "big-Q4_K_M.gguf", "size": 6_000_000_000, "lfs": {"oid": "sha256:" + SHA, "size": 6_000_000_000}}]
tools._hf_json = lambda url: tree
models.add_catalog_entry = lambda entry: entry
ADD_NOTE = " It's bigger than this computer's memory, so it will run from disk, slowly."
try:
    models.ram_gb = lambda: 4.0          # new model needs 7 GB: bigger
    reply = tools.add_model({"repo": "owner/big"}, Ctx())
    check(reply.startswith("added ") and reply.endswith(ADD_NOTE),
          f"add_model bigger: note appended: ...{reply[-120:]!r}")
    models.ram_gb = lambda: 7.0          # exactly equal: no note
    reply = tools.add_model({"repo": "owner/big"}, Ctx())
    check(ADD_NOTE not in reply and reply.startswith("added "), f"add_model equal RAM: no note: ...{reply[-80:]!r}")
    models.ram_gb = lambda: 0            # unknown: no note
    reply = tools.add_model({"repo": "owner/big"}, Ctx())
    check(ADD_NOTE not in reply and reply.startswith("added "), f"add_model RAM unknown: no note: ...{reply[-80:]!r}")
finally:
    tools._hf_json, models.add_catalog_entry, models.ram_gb = real_add

os.unlink(GGUF.name)
print("all good" if fails == 0 else f"{fails} FAILED")
sys.exit(1 if fails else 0)
