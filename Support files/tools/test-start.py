#!/usr/bin/env python3
"""Tests of the Start Here launchers on this Mac (the Windows ones are checked for structure only).

  * "Start Here (Mac).command" finds this Mac's Python and opens Setup
  * with no usable Python, the starter fetches a private copy, checks its SHA-256, unpacks it (keeping the
    python3 -> python3.13 symlink, as in the real archive) and runs Setup with it -- a local stand-in server
    serves the archive, so nothing is downloaded from the internet
  * a download that doesn't match its checksum is refused, and nothing broken is left behind
  * the folder layout: LICENSE, README.md, three Start Here files and one "Support files" folder; the Windows
    file has CRLF endings and every launcher points at a starter that exists

Run: python3 tools/test-start.py
"""
import hashlib
import http.server
import io
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading

TOOLS = os.path.dirname(os.path.abspath(__file__))
SUPPORT = os.path.dirname(TOOLS)
TOP = os.path.dirname(SUPPORT)
SETUP_DIR = os.path.join(SUPPORT, "dist", "setup")
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what, flush=True)
    if not cond:
        fails += 1


def launch(cmd, env, timeout=60):
    """Start a launcher; return its output up to Setup's banner (then stop it), or all of it if it exits."""
    p = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = []
    try:
        for line in p.stdout:
            out.append(line)
            if "paste this address" in line:
                break
    finally:
        p.kill()
        p.wait()
    return "".join(out)


base_env = dict(os.environ, LLMOS_SETUP_NO_BROWSER="1", TERM="dumb")

print("the folder a friend opens")
top = sorted(n for n in os.listdir(TOP) if not n.startswith(".") and n != "packages")   # packages/: local build output (git-ignored), never shipped
# LICENSE and README.md are the GitHub checkout (the license and the overview). Dotfiles stay ignored.
check(top == ["LICENSE", "README.md", "Start Here (Linux).sh", "Start Here (Mac).command",
              "Start Here (Windows).bat", "Support files"],
      f"LICENSE, README, the three Start Here files and one folder: {top}")
bat = open(os.path.join(TOP, "Start Here (Windows).bat"), "rb").read()
check(b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b""), "the Windows file has Windows line endings throughout")
for name in os.listdir(TOP):
    if name.startswith("Start Here"):
        text = open(os.path.join(TOP, name), encoding="utf-8", errors="replace").read()
        rel = re.search(r"Support files[\\/]dist[\\/]setup[\\/](start\.(?:sh|ps1))", text)
        check(bool(rel) and os.path.isfile(os.path.join(SETUP_DIR, rel.group(1))), f"{name} points at a starter that exists")
        check(os.access(os.path.join(TOP, name), os.X_OK), f"{name} is executable (double-click runs it)")

print("Start Here on this Mac, with its own Python")
if platform.system() != "Darwin":
    print("SKIP: this check needs macOS, where Start Here looks for the Mac's own Python. This machine is not macOS.")
else:
    out = launch(["/bin/bash", os.path.join(TOP, "Start Here (Mac).command")], base_env)
    check("LLM OS Setup is open in your web browser" in out, "opens Setup")

print("a Mac without Python: the starter fetches a private copy")
tmp = tempfile.mkdtemp(prefix="llmos-start-")
system_py = shutil.which("python3") or sys.executable
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:      # the real archive's shape: python/bin/python3 -> python3.13
    real = f'#!/bin/sh\nexec "{system_py}" "$@"\n'.encode()
    ti = tarfile.TarInfo("python/bin/python3.13")
    ti.size, ti.mode = len(real), 0o755
    tar.addfile(ti, io.BytesIO(real))
    link = tarfile.TarInfo("python/bin/python3")
    link.type, link.linkname = tarfile.SYMTYPE, "python3.13"
    tar.addfile(link)
blob = buf.getvalue()
serve = os.path.join(tmp, "www")
os.makedirs(serve)
with open(os.path.join(serve, "py.tar.gz"), "wb") as f:
    f.write(blob)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=serve, **kw)

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/py.tar.gz"
cache = os.path.join(tmp, "cache")
env = dict(base_env, LLMOS_PY_SKIP_SYSTEM="1", LLMOS_PY_CACHE=cache, LLMOS_PY_URL=url,
           LLMOS_PY_SHA256=hashlib.sha256(blob).hexdigest(), LLMOS_PY_NO_FALLBACK="1")
out = launch(["/bin/sh", os.path.join(SETUP_DIR, "start.sh"), "mac"], env)
check("Getting Python for this setup" in out, "says it is getting Python, once")
check("LLM OS Setup is open in your web browser" in out, "Setup runs on the fetched copy")
check(os.path.islink(os.path.join(cache, "python", "bin", "python3")), "the archive's python3 symlink was kept")
check(not os.path.exists(os.path.join(cache, "python.tar.gz.part")), "the download was tidied away")
out = launch(["/bin/sh", os.path.join(SETUP_DIR, "start.sh"), "mac"], env)
check("Getting Python" not in out and "open in your web browser" in out, "the next start reuses it without downloading again")

shutil.rmtree(cache)
env["LLMOS_PY_SHA256"] = "0" * 64
out = launch(["/bin/sh", os.path.join(SETUP_DIR, "start.sh"), "mac"], env)
check("didn't match its published checksum" in out, "a download that doesn't match its checksum is refused")
check("open in your web browser" not in out and not os.path.exists(os.path.join(cache, "python")), "…and nothing from it is used or kept")
check("command line developer tools" in out, "…and it explains the way forward")
srv.shutdown()
shutil.rmtree(tmp, ignore_errors=True)

print("the Windows starter (structure; it runs on Windows only)")
ps = open(os.path.join(SETUP_DIR, "start.ps1"), encoding="utf-8").read()
for flavor, sha in (("amd64", "97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297"),
                    ("arm64", "790d097697a2020477549a6764d89d22194c88d6e42caebcb2db63791e004c94")):
    check(sha in ps, f"pins python.org's published SHA-256 for the {flavor} embeddable Python")
check("Get-FileHash" in ps and "-ne $sums[$flavor]" in ps, "refuses a download whose SHA-256 differs")
check("python-3.13.16-embed-$flavor.zip" in ps and "https://www.python.org/ftp/python/3.13.16/" in ps, "fetches from python.org only")

print("all good" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
