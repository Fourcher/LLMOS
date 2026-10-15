#!/usr/bin/env python3
"""Host-side test of the model manager additions (no network): the owner-added catalog overlay, the agentic
refresh (check_new_models) and add_model against a mocked Hugging Face, and online-model switching. Every
added model must stay pinned to a real SHA-256. Run: python3 tools/test-models.py"""
import json
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
from llmos import config, llm, models, tools, web  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Ctx:
    is_desk = False

    def status(self, t):
        pass

    def redraw(self):
        pass


ctx = Ctx()
SHA = "a" * 64

# a fake Hugging Face: the model-list search and the file tree
TREE = {
    "TheLab/Cool-Model-GGUF": [
        {"path": "Cool-Model-Q8_0.gguf", "size": 123, "lfs": {"oid": "sha256:" + ("b" * 64), "size": 9_000_000_000}},
        {"path": "Cool-Model-Q4_K_M.gguf", "size": 123, "lfs": {"oid": SHA, "size": 4_000_000_000}},
        {"path": "README.md", "size": 10},
    ],
    "NoSha/Plain-GGUF": [{"path": "plain-Q4_K_M.gguf", "size": 4_000_000_000}],   # no lfs oid -> not pinnable
    "mistralai/Ministral-3-3B-Instruct-2512-GGUF": [{"path": "x-Q4_K_M.gguf", "lfs": {"oid": SHA, "size": 2_000_000_000}}],
}


def fake_fetch(url, max_bytes=2_000_000, timeout=20, data=None, dest=None):
    body = b"[]"
    if "/api/models/" in url and "/tree/main" in url:
        repo = url.split("/api/models/")[1].split("/tree/main")[0]
        body = json.dumps(TREE.get(repo, [])).encode()
    elif "/api/models?" in url:
        author = url.split("author=")[1].split("&")[0]
        rows = []
        if author == "TheLab":
            rows = [{"id": "TheLab/Cool-Model-GGUF", "lastModified": "2026-09-30T00:00:00", "downloads": 1234}]
        if author == "mistralai":
            rows = [{"id": "mistralai/Ministral-3-3B-Instruct-2512-GGUF", "lastModified": "2026-01-01"},  # already in catalog
                    {"id": "mistralai/Ministral-9-99B-GGUF", "lastModified": "2026-10-01", "downloads": 50}]
        body = json.dumps(rows).encode()
    return 200, "application/json", url, body


web.fetch = fake_fetch
tools.web.fetch = fake_fetch
# authors to scan: keep it small and deterministic
tools._catalog_authors = lambda: ["mistralai", "TheLab"]

print("catalog overlay")
n_builtin = len(models.catalog())
check(n_builtin == 13, f"built-in catalog has 13 models ({n_builtin})")
entry = {"id": "my-model", "name": "My Model", "maker": "Me", "repo": "Me/My-GGUF", "file": "m.gguf",
         "size": 3_000_000_000, "sha256": SHA, "ram_gb": 4, "note": "mine", "good_at": [], "limits": []}
models.add_catalog_entry(entry)
check(any(m["id"] == "my-model" for m in models.catalog()) and len(models.catalog()) == n_builtin + 1, "an added model appears in the catalog")
check(models.by_id("my-model") is not None, "by_id finds an added model")
try:
    models.add_catalog_entry({"id": "ministral-3-3b", "name": "fake", "repo": "x/y"})
    check(False, "a built-in id is refused")
except ValueError:
    check(True, "a built-in id cannot be overridden")

print("add_model (mocked Hugging Face)")
r = tools.add_model({"repo": "TheLab/Cool-Model-GGUF"}, ctx)
check("added" in r.lower() and "4.0 GB" in r, f"adds, prefers the Q4_K_M build, reports size: {r}")
added = models.by_id(tools._slug("TheLab/Cool-Model-GGUF", "Cool-Model-Q4_K_M.gguf"))
check(added and added["sha256"] == SHA, f"pinned to the file's LFS sha256: {added and added['sha256'][:8]}")
check(added and added["file"] == "Cool-Model-Q4_K_M.gguf" and added["ram_gb"] >= 4, "picked the Q4_K_M file; ram estimated")
r = tools.add_model({"repo": "TheLab/Cool-Model-GGUF", "file": "Cool-Model-Q8_0.gguf"}, ctx)
check("added" in r.lower() and "9.0 GB" in r, f"an exact file name is honoured: {r}")
r = tools.add_model({"repo": "NoSha/Plain-GGUF"}, ctx)
check("hash-pinned" in r.lower() and "not adding" in r.lower(), f"a file with no SHA-256 is refused: {r}")
r = tools.add_model({"repo": "not a repo"}, ctx)
check(r.startswith("error"), f"a malformed repo is rejected: {r}")

print("check_new_models (mocked Hugging Face)")
os.unlink(config.data("catalog-extra.json"))   # start clean so just-added repos count as new again
r = tools.check_new_models({}, ctx)
check("TheLab/Cool-Model-GGUF" in r, "surfaces a new repo not in the catalog")
check("Ministral-3-3B-Instruct-2512-GGUF" not in r, "does not list a repo already in the catalog")
check("Ministral-9-99B-GGUF" in r, "lists a newer repo from a trusted maker")

print("online model switching")
config.save_cloud({"provider": "anthropic", "model": "claude-opus-5-5", "url": "https://api.anthropic.com", "key": "sk-ant-x"})
ok, note = llm.switch_cloud_model("claude-opus-5-5")
check(ok and config.cloud()["model"] == "claude-opus-5-5", f"switches the online model, keeps the key: {note}")
check(config.cloud()["key"] == "sk-ant-x", "the key is unchanged after a switch")
ok, note = llm.switch_cloud_model("opus")
check(ok and config.cloud()["model"] == "claude-opus-5-5", f"fuzzy name resolves: {note}")
ok, note = llm.switch_cloud_model("gpt-9")
check(not ok and "not one of" in note, f"an unknown model for the provider is refused: {note}")
r = tools.online_model({"action": "use", "model": "claude-haiku-4-5"}, ctx)
check(config.cloud()["model"] == "claude-haiku-4-5", f"the online_model tool switches too: {r}")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
