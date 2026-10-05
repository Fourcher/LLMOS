#!/usr/bin/env python3
"""Host-side test of LLM OS Setup (dist/setup/llmos-setup.py): its CSRF / cross-origin protection, and how it
recognises any computer and chooses for it.

Setup is a local web app on 127.0.0.1 that can erase USB sticks and start programs, so a web page the owner happens
to have open must not be able to drive it: every /api endpoint (read-only ones included) requires the per-launch
token in a custom header; cross-origin requests, DNS-rebinding hosts and CORS preflights are refused; the page
carries anti-framing / no-store headers and runs only its own script (by hash).

Recognising the computer: a Mac with Apple silicon (even when Python runs under Rosetta), an Intel Mac, a Windows
PC (x64 or ARM), a Linux PC (x86-64 or ARM) are simulated; the USB stick always gets the x86-64 image (the one PCs
and Intel Macs start), and "try it in a window" picks the right free app for each. Windows and Linux drive lists
are parsed from simulated system answers; Linux never offers a disk holding the running system.

Run: python3 tools/test-setup-csrf.py (a loopback server only; nothing is launched or erased)."""
import contextlib
import http.client
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("llmos_setup", os.path.join(ROOT, "dist/setup/llmos-setup.py"))
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)

ex.TOKEN = "a" * 32
BAD = "b" * 32
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ex.Handler)
PORT = srv.server_address[1]
HOST = f"127.0.0.1:{PORT}"
threading.Thread(target=srv.serve_forever, daemon=True).start()
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


def req(method, path, headers=None, body=None, host=HOST):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    h = {"Host": host}
    h.update(headers or {})
    c.request(method, path, body, h)
    r = c.getresponse()
    data = r.read()
    hd = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, data, hd


@contextlib.contextmanager
def patched(obj, **attrs):
    old = {k: getattr(obj, k) for k in attrs}
    for k, v in attrs.items():
        setattr(obj, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(obj, k, v)


TOK = {"X-LLMOS-Token": ex.TOKEN}
JSON = {"Content-Type": "application/json"}

print("the page")
s, b, h = req("GET", "/")
page = b.decode("utf-8")
check(s == 200 and ex.TOKEN not in page, "GET / serves the page without the token (it arrives in the #fragment, never sent to a server)")
want = ex._page_script_hash()
csp = h.get("content-security-policy", "")
check(want != "'none'" and "script-src " + want in csp and "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0],
      "the CSP allows only the page's own script, by its SHA-256")
check(" onclick=" not in page and " onload=" not in page and "javascript:" not in page, "no inline event handlers or javascript: links")
check(h.get("x-frame-options") == "DENY" and "frame-ancestors 'none'" in csp, "the page can't be framed by another site")
check(h.get("cache-control") == "no-store" and h.get("x-content-type-options") == "nosniff", "no caching, no content sniffing")

print("every /api endpoint requires the token (not only the actions)")
for ep in ("/api/status", "/api/drives", "/api/progress"):
    check(req("GET", ep, TOK)[0] == 200, f"GET {ep} with the token -> 200")
    check(req("GET", ep)[0] == 403, f"GET {ep} without it -> 403")
for ep, body in (("/api/write", b'{"drive":"x"}'), ("/api/open", b'{"what":"image"}'), ("/api/quit", b"{}")):
    check(req("POST", ep, JSON, body)[0] == 403, f"POST {ep} without the token -> 403")

print("cross-origin and DNS rebinding are refused even with the token")
check(req("GET", "/api/status", {**TOK, "Origin": "http://evil.example"})[0] == 403, "token + another site's Origin -> 403")
check(req("GET", "/api/status", {**TOK, "Referer": "http://evil.example/x"})[0] == 403, "token + another site's Referer -> 403")
check(req("GET", "/api/status", TOK, host=f"evil.example:{PORT}")[0] == 403, "Host: evil.example (DNS rebinding) -> 403")
check(req("GET", "/api/status", {"X-LLMOS-Token": BAD})[0] == 403, "a wrong token -> 403 (constant-time compare)")
s, _, h = req("OPTIONS", "/api/write", {"Origin": "http://evil.example", "Access-Control-Request-Method": "POST",
                                        "Access-Control-Request-Headers": "x-llmos-token"})
check(s == 403 and not any(k.startswith("access-control-allow") for k in h), "a CORS preflight -> 403, with no Access-Control-Allow-*")

print("the actions do only what they say")
s, b, _ = req("POST", "/api/write", {**TOK, **JSON}, b'{"drive":"/dev/disk0"}')
check(s == 200 and not json.loads(b)["ok"] and "isn't connected" in json.loads(b)["error"],
      "writing to a disk that isn't in the USB list is refused (e.g. the internal disk0)")
s, b, _ = req("POST", "/api/open", {**TOK, **JSON}, b'{"what":"rm -rf /"}')
check(not json.loads(b)["ok"], "an unknown action is refused")
s, b, _ = req("POST", "/api/write", {**TOK, **JSON}, b'[1,2,3]')
check(s == 200 and not json.loads(b)["ok"], "a malformed request is refused cleanly")
st = json.loads(req("GET", "/api/status", TOK)[1])
check(st["usb"]["image"] == "llmos-x86_64.iso", "status: the USB stick gets the x86-64 image")
check(st["host"]["os"] in ("mac", "windows", "linux") and st["host"]["arch"] in ("arm64", "x86_64"),
      f"status: this computer is {st['host']['kind']} / {st['host']['arch']}, {st['host']['ram_gb']} GB")
srv.shutdown()

print("recognising the processor, whatever Python runs it")
cases = [("mac", "x86_64", "1", "arm64", "Apple silicon Mac, Python under Rosetta (reports x86_64)"),
         ("mac", "arm64", "1", "arm64", "Apple silicon Mac"),
         ("mac", "x86_64", "", "x86_64", "Intel Mac (no hw.optional.arm64)"),
         ("linux", "aarch64", "", "arm64", "ARM Linux"),
         ("linux", "x86_64", "", "x86_64", "x86-64 Linux")]
for osname, machine, arm, expect, what in cases:
    with patched(ex, OS=osname, _sysctl=lambda name, a=arm: a if name == "hw.optional.arm64" else ""), \
         patched(ex.platform, machine=lambda m=machine: m):
        check(ex.native_arch() == expect, f"{what} -> {expect}")
for env, expect, what in (({"PROCESSOR_ARCHITECTURE": "AMD64"}, "x86_64", "Windows x64"),
                          ({"PROCESSOR_ARCHITECTURE": "ARM64"}, "arm64", "Windows on ARM"),
                          ({"PROCESSOR_ARCHITECTURE": "x86", "PROCESSOR_ARCHITEW6432": "ARM64"}, "arm64", "Windows on ARM, 32-bit Python")):
    saved = {k: os.environ.get(k) for k in ("PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432")}
    os.environ.pop("PROCESSOR_ARCHITEW6432", None)
    os.environ.update(env)
    with patched(ex, OS="windows"):           # off Windows, IsWow64Process2 is missing, so the variables decide
        check(ex.native_arch() == expect, f"{what} -> {expect}")
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
for arch, boots in (("x86_64", True), ("arm64", False)):
    with patched(ex, ARCH=arch):
        check(ex.host()["boots_usb"] is boots, f"a {arch} computer {'can' if boots else 'cannot'} start from the stick itself")

print("trying it in a window: the right free app for each computer")


def plan(osname, arch, have=(), apps=(), ram=16):
    files = {"llmos-arm64.iso", "llmos-x86_64.iso", *have}
    with patched(ex, OS=osname, ARCH=arch, ram_gb=lambda: ram), \
         patched(ex.shutil, which=lambda n: "/usr/bin/" + n if n in apps else None), \
         patched(ex.os.path, isfile=lambda p: os.path.basename(p) in files, isdir=lambda p: "UTM.app" in p and "utm" in apps,
                 exists=lambda p: any(a in p for a in apps)):
        return ex.vm_plan()


p = plan("mac", "arm64", have=("llmos-arm64.qcow2", "run-llmos.sh"), apps=("qemu-system-aarch64",))
check(p["method"] == "launcher", "Apple silicon Mac with QEMU and the VM disk -> starts it directly")
p = plan("mac", "arm64")
check(p["method"] == "utm" and p["image"] == "llmos-arm64.iso" and not p["installed"], "Apple silicon Mac without QEMU -> UTM, with the ARM image")
p = plan("mac", "arm64", apps=("utm",))
check(p["method"] == "utm" and p["installed"], "…and knows when UTM is already installed")
p = plan("mac", "x86_64")
check(p["method"] == "utm" and p["image"] == "llmos-x86_64.iso", "Intel Mac -> UTM, with the x86-64 image")
p = plan("windows", "x86_64")
check(p["method"] == "virtualbox" and p["image"] == "llmos-x86_64.iso", "Windows PC -> VirtualBox, with the x86-64 image")
check(plan("windows", "arm64")["method"] == "none", "Windows on ARM -> no window option (make a USB stick for a PC instead)")
check(plan("linux", "x86_64", apps=("gnome-boxes",))["method"] == "boxes", "Linux -> Boxes")
check(plan("mac", "arm64", ram=8)["low_memory"] is False and plan("mac", "arm64", ram=4)["low_memory"] is True,
      "warns only when memory is short (under 8 GB)")

print("Windows: the USB list as PowerShell reports it")
answers = [("[]", 0, "no USB disk"),
           ('{"Number":2,"Name":"SanDisk Ultra","Size":30752000000,"Bus":"USB","Labels":"STICK"}', 1, "one disk (PowerShell gives an object, not a list)"),
           ('[{"Number":2,"Name":"SanDisk","Size":30752000000,"Bus":"USB","Labels":["A","B"]},'
            '{"Number":3,"Name":"Card","Size":7000000000,"Bus":"SD","Labels":[]}]', 2, "two disks")]
for out, n, what in answers:
    with patched(ex, _ps=lambda script, timeout=60, o=out: subprocess.CompletedProcess([], 0, o, ""),
                 _win_self_disk_letter=lambda: "C"):
        got = ex._win_drives()
    check(len(got) == n and all(isinstance(d["labels"], list) for d in got), f"{what} -> {[(d['id'], d['name'], d['labels']) for d in got]}")
with patched(ex, _ps=lambda script, timeout=60: subprocess.CompletedProcess([], 0, "[]", ""), _win_self_disk_letter=lambda: "D"):
    seen = []
    with patched(ex, _ps=lambda script, timeout=60: (seen.append(script), subprocess.CompletedProcess([], 0, "[]", ""))[1]):
        ex._win_drives()
check(seen and "-DriveLetter 'D'" in seen[0] and "$_.Number -ne $own" in seen[0] and "-not $_.IsSystem -and -not $_.IsBoot" in seen[0],
      "the query leaves out the disk Setup runs from, the system disk and the boot disk")

print("Linux: never a disk that holds the running system")
here = ex.FILES
tree = [({"name": "sdb", "type": "disk", "rm": True, "tran": "usb",
          "children": [{"name": "sdb1", "type": "part", "mountpoint": "/media/me/STICK", "label": "STICK"}]}, "",
         "a stick the desktop mounted under /media is offered (it is unmounted first)"),
        ({"name": "mmcblk0", "type": "disk", "rm": "1", "children": [{"name": "mmcblk0p2", "type": "part", "mountpoint": "/"}]},
         "it holds / of this computer", "a disk holding / is never offered"),
        ({"name": "sdc", "type": "disk", "tran": "usb", "children": [{"name": "sdc1", "type": "part", "mountpoint": None,
          "children": [{"name": "luks-x", "type": "crypt", "mountpoint": None}]}]}, "encrypted", "a disk with an open LUKS volume is never offered"),
        ({"name": "sdd", "type": "disk", "tran": "usb", "children": [{"name": "sdd2", "type": "part", "mountpoint": "[SWAP]"}]},
         "[SWAP]", "a disk used as swap is never offered"),
        ({"name": "sde", "type": "disk", "tran": "usb", "children": [{"name": "sde1", "type": "part", "mountpoint": os.path.dirname(here)}]},
         "Setup itself runs from it", "the disk Setup runs from is never offered")]
for node, why, what in tree:
    reason = ex._linux_blocker(node)
    check((why in reason) if why else reason == "", f"{what}: {reason or 'allowed'}")
with patched(ex, _lsblk=lambda device=None: [n for n, _, _ in tree] + [{"name": "nvme0n1", "type": "disk", "rm": False, "tran": "nvme"}]):
    ids = [d["id"] for d in ex._linux_drives()]
check(ids == ["/dev/sdb"], f"the Linux list offers only the free USB stick: {ids}")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
