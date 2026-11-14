#!/usr/bin/env python3
"""On-device self-improvement: local llama.cpp only, a capped light gate, signed install, rollback.

No cloud API and no full host suite. Run: python3 tools/test-selfloop-device.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src/rootfs/usr/lib/llmos")
state = tempfile.mkdtemp(prefix="llmos-selfloop-device-")
os.environ["LLMOS_SELFLOOP_DIR"] = state
os.environ["LLMOS_HOME"] = state
os.environ["LLMOS_ETC"] = os.path.join(state, "etc")
os.environ["LLMOS_SELFLOOP_CONFIG"] = os.path.join(state, "no-such-config.json")
os.environ["LLMOS_OTA_ROOT"] = os.path.join(state, "ota-root-unused")
os.environ["LLMOS_OTA_DIR"] = os.path.join(state, "ota-state-unused")
os.environ["LLMOS_BOOT_FAILED"] = os.path.join(state, "no-boot-failed")
os.environ["LLMOS_HEALTH_CHECK"] = ""
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)

import selfdev  # noqa: E402
import selfloop  # noqa: E402
import selfloop_local  # noqa: E402
from llmos import selfloop_ctl  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


def cfg(**over):
    base = {"mode": "device", "backend": "local", "require_approval": True, "max_per_day": 8,
            "min_interval_sec": 0, "max_iterations": 3, "max_light_tests": 24, "nice": 19,
            "local_transport": "server", "local_url": "http://127.0.0.1:8080", "local_timeout_sec": 30,
            "local_max_tokens": 64, "local_temperature": 0}
    base.update(over)
    return base


def make_package(text='VALUE = "old"\n'):
    """A throwaway install root whose package directory is .../usr/lib/llmos (what the signed installer requires)."""
    root = tempfile.mkdtemp(prefix="pkg-", dir=state)
    pkg = os.path.join(root, "usr", "lib", "llmos")
    os.makedirs(os.path.join(pkg, "llmos"))
    open(os.path.join(pkg, "llmos", "marker.py"), "w", encoding="utf-8").write(text)
    open(os.path.join(pkg, "llmos", "__init__.py"), "w", encoding="utf-8").write('VERSION = "1.8.7"\n')
    return pkg


def marker(root):
    return open(os.path.join(root, "llmos", "marker.py"), encoding="utf-8").read()


# --- config: approval stays on, device mode defaults to the local backend, bad values are ignored ---
missing = selfloop_ctl.load_config(os.path.join(state, "missing.json"))
check(missing["require_approval"] is True and missing["backend"] == "configured" and missing["max_iterations"] == 3,
      "a missing config requires approval, keeps the existing backend, and bounds iterations")
device_cfg = os.path.join(state, "device.json")
json.dump({"mode": "device", "require_approval": True, "max_per_day": 4, "min_interval_sec": 1800,
           "local": {"transport": "auto", "url": "http://10.0.2.2:8080", "nice": 40, "temperature": 0.2}},
          open(device_cfg, "w"))
loaded = selfloop_ctl.load_config(device_cfg)
check(loaded["mode"] == "device" and loaded["backend"] == "local" and loaded["require_approval"] is True,
      "device mode with no backend uses the local model and still requires approval")
check(loaded["local_url"] == "http://10.0.2.2:8080", "a bad URL is kept so the backend can refuse it")
check(loaded["nice"] == 19 and loaded["local_temperature"] == 0.2, "an out-of-range nice is ignored; temperature is kept")
cloud_cfg = os.path.join(state, "cloud.json")
json.dump({"mode": "device", "backend": "cloud", "require_approval": "no"}, open(cloud_cfg, "w"))
cloud_loaded = selfloop_ctl.load_config(cloud_cfg)
check(cloud_loaded["backend"] == "cloud" and cloud_loaded["require_approval"] is True,
      "an explicit cloud backend is not silently rewritten, and a non-bool approval stays on")
check("dev" in selfloop_ctl.summary().lower() and "approval" in selfloop_ctl.summary().lower(),
      "status for the default config still names dev-machine mode and approval")
os.environ["LLMOS_SELFLOOP_CONFIG"] = device_cfg
check("staging" in selfloop_ctl.summary().lower() and "network" in selfloop_ctl.summary().lower(),
      "device status names the staging copy and that network services are not restarted")
os.environ["LLMOS_SELFLOOP_CONFIG"] = os.path.join(state, "no-such-config.json")

# --- the local backend never leaves the machine ---
local_src = open(selfloop_local.__file__, encoding="utf-8").read()
loop_src = open(selfloop.__file__, encoding="utf-8").read()
check("cloud_chat" not in local_src and "api.openai" not in local_src and "anthropic" not in local_src,
      "the local backend has no cloud client")
check("rc-service" not in local_src, "the local installer does not restart services")
check("def complete_existing" in loop_src and "cloud_chat" in loop_src and "def default_implement" in loop_src,
      "the existing cloud, llama, and selfdev backends are still in the loop")
worker, rounds = selfloop.resolve_worker({"backend": "configured", "mode": "dev"}, None)
check(worker is selfloop.default_implement and rounds == 1, "configured still runs selfdev once")
worker, rounds = selfloop.resolve_worker({"backend": "local", "max_iterations": 3}, None)
check(worker is None and rounds == 3, "the local backend is bounded by max_iterations")
worker, rounds = selfloop.resolve_worker({"backend": "llama", "max_iterations": 4}, lambda *_a: None)
check(rounds == 1, "an injected worker stays one shot, including for the llama backend")

lookups = []
real_getaddrinfo = socket.getaddrinfo


def spy_dns(host, *args, **kwargs):
    lookups.append(host)
    raise AssertionError("should not resolve " + str(host))


socket.getaddrinfo = spy_dns
for bad in ("http://10.0.2.2:8080", "http://192.168.1.5:8080", "http://example.com:8080",
            "https://127.0.0.1:8080", "http://user:pass@127.0.0.1:8080", ""):
    try:
        selfloop_local.assert_loopback(bad)
        check(False, "refused " + (bad or "(empty)"))
    except selfloop_local.LocalModelError:
        check(True, "refused " + (bad or "(empty)"))
check(lookups == [], "a non-loopback host is refused before any name lookup")
socket.getaddrinfo = real_getaddrinfo

host, port = selfloop_local.split_loopback("http://[::1]:8080")
check(host == "::1" and port == 8080, "an IPv6 loopback URL is recognized without connecting")
try:
    selfloop_local.assert_loopback("http://127.0.0.1:9")
    check(True, "127.0.0.1 is a loopback address")
except selfloop_local.LocalModelError as e:
    check(False, "127.0.0.1 is a loopback address: " + str(e))


def lie_dns(*_a, **_k):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 8080))]


socket.getaddrinfo = lie_dns
try:
    selfloop_local.assert_loopback("http://localhost:8080")
    check(False, "localhost that resolves off-machine is refused")
except selfloop_local.LocalModelError as e:
    check("8.8.8.8" in str(e), "localhost that resolves off-machine is refused")
socket.getaddrinfo = real_getaddrinfo

# a real loopback server, then the CLI, and auto must not call the CLI while the server is up
seen = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        seen["body"] = raw
        seen["client"] = self.client_address[0]
        body = json.dumps({"choices": [{"message": {"content": "from-server"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_address[1]}"
text = selfloop_local.complete(cfg(local_url=url, local_transport="server"),
                              [{"role": "user", "content": "edit"}])
check(text == "from-server" and seen.get("client") == "127.0.0.1", "the server backend talks to loopback only")
body = json.loads(seen["body"])
check(body.get("stream") is False and body["messages"][0]["content"] == "edit",
      "the server request is one local completion")

cli_flag = os.path.join(state, "cli-ran")
cli = os.path.join(state, "llama-cli")
model = os.path.join(state, "model.gguf")
open(model, "wb").write(b"gguf")
open(cli, "w", encoding="utf-8").write(
    "#!/bin/sh\nprintf '%s\\n' \"$@\" > " + json.dumps(os.path.join(state, "cli-args")) +
    "\ntouch " + json.dumps(cli_flag) + "\necho from-cli\n")
os.chmod(cli, 0o755)
auto = selfloop_local.complete(cfg(local_url=url, local_transport="auto", local_cli=cli, local_model=model),
                              [{"role": "user", "content": "edit"}])
check(auto == "from-server" and not os.path.exists(cli_flag),
      "auto uses the loopback server and does not start the CLI while it is up")
server.shutdown()
fallen = selfloop_local.complete(cfg(local_url=url, local_transport="auto", local_cli=cli, local_model=model,
                                    local_timeout_sec=30),
                                [{"role": "user", "content": "edit"}])
check(fallen.strip() == "from-cli" and os.path.exists(cli_flag), "auto uses the CLI only when the server is down")
args = open(os.path.join(state, "cli-args"), encoding="utf-8").read().splitlines()
check("-m" in args and model in args and not any(a.startswith("http") for a in args),
      "the CLI is given a local file and no URL")
nice_cmd = selfloop_local.nice_argv([cli, "-m", model])
check("nice" in nice_cmd and "19" in nice_cmd, "heavy local work is run under nice")
try:
    selfloop_local.chat_cli(cfg(local_transport="cli", local_cli=cli, local_model="https://example.com/m.gguf"), [])
    check(False, "a model URL is refused")
except selfloop_local.LocalModelError as e:
    check("file" in str(e).lower(), "a model URL is refused")
try:
    selfloop_local.complete(cfg(local_url="http://10.0.2.2:8080", local_transport="auto", local_cli=cli,
                               local_model=model), [])
    check(False, "auto does not fall back to the CLI for a non-loopback URL")
except selfloop_local.LocalModelError:
    check(True, "auto does not fall back to the CLI for a non-loopback URL")

# --- edits stay in the staging package and cannot touch the rails ---
pkg = make_package("alpha\n")
n, problems, changed = selfloop_local.apply_edits(pkg, [
    {"path": "llmos/marker.py", "search": "alpha\n", "replace": "beta\n"},
    {"path": "llmos/selfloop_ctl.py", "search": "a", "replace": "b"},
])
check(n == 0 and marker(pkg) == "alpha\n" and any("cannot edit" in p for p in problems),
      "a rails hunk rejects the whole patch and the package file stays untouched")
n, problems, changed = selfloop_local.apply_edits(pkg, [
    {"path": "llmos/../../etc/passwd", "search": "a", "replace": "b"}])
check(n == 0 and any("escapes" in p for p in problems), "a path with .. is not applied")
n, _problems, changed = selfloop_local.apply_edits(pkg, [
    {"path": "llmos/marker.py", "search": "alpha\n", "replace": "beta\n"}])
check(n == 1 and marker(pkg) == "beta\n" and changed == ["src/rootfs/usr/lib/llmos/llmos/marker.py"],
      "a matching edit is applied only inside the package copy")
messages = selfloop_local.prompt_messages(pkg, {"title": "marker change", "detail": "do not weaken the gate"})
blob = "\n".join(m["content"] for m in messages)
check("http://" not in blob and "selfloop_ctl.py" in blob and "TASK: marker change" in blob,
      "the local prompt asks for an edit and does not name an off-machine URL")

# --- light gate is capped and will not start the full suite ---
kept, dropped = selfloop.cap_light(
    list(selfdev.CORE_TESTS) + [f"tools/test-extra-{i}.py" for i in range(30)],
    ["tools/test-extra-1.py"], 10)
check(len(kept) == 10 and kept[:len(selfdev.CORE_TESTS)] == list(selfdev.CORE_TESTS),
      "the cap keeps the core tests and stops at the limit")
check(dropped[0] == "tools/test-extra-1.py" or "tools/test-extra-1.py" in kept,
      "a test that names the module is preferred when the cap cuts")
check("tools/test-extra-1.py" in kept, "a test that names the module is kept ahead of the rest")
sel, info = selfloop.tests_for_package(["src/rootfs/usr/lib/llmos/llmos/selfloop_ctl.py"], 24, ROOT)
all_tests = [name for name in os.listdir(HERE) if name.startswith("test-") and name.endswith(".py")]
check(sel and len(sel) <= 24 and len(sel) < len(all_tests) and "capped" in info,
      "the on-device gate is a capped subset, not every host test")
check(sel and all(t in sel for t in selfdev.CORE_TESTS), "the capped gate still includes the core seatbelt")
try:
    selfloop.gate_command(ROOT, [])
    check(False, "an empty test list is refused")
except RuntimeError as e:
    check("full suite" in str(e), "an empty test list is refused")
refused_gate, why = selfloop.run_light_gate(ROOT, [])
check(refused_gate is False and "full suite" in why, "the runner refuses an empty list instead of starting every suite")
cmd = selfloop.gate_command(ROOT, ["tools/test-selfloop-device.py"])
check("nice" in cmd and "tools/test-selfloop-device.py" in cmd, "the light gate runs under nice and names its tests")

# --- on-device flow: stage, do not touch the live tree, queue, cap iterations, refuse cloud ---
outs = os.path.join(state, "stages")
installs = []
impl_calls = []


def implement(support, item):
    impl_calls.append(item.get("id"))
    path = os.path.join(support, "src", "rootfs", "usr", "lib", "llmos", "llmos", "marker.py")
    open(path, "w", encoding="utf-8").write('VALUE = "new"\n')
    return {"changed": ["src/rootfs/usr/lib/llmos/llmos/marker.py"]}


def select(_paths):
    return ["tools/test-selfloop-device.py"], "one test"


def gate(_support, tests):
    check(tests == ["tools/test-selfloop-device.py"], "the device gate is the targeted list")
    return True, "host suites: 1 run, 0 failed"


def install(support, package):
    installs.append((support, package))
    return True, "installed by the test"


def kw(now, **over):
    d = dict(backlog=[{"id": "item", "title": "touch the marker", "status": "open"}],
             log_text="", now=now, package_src=pkg, dest_parent=outs, implement=implement,
             select=select, gate=gate, install=install)
    d.update(over)
    return d


selfloop_ctl.set_killed(True)
killed = selfloop.run_once(cfg=cfg(), **kw(10_000_000, backlog=[{"id": "k", "title": "no", "status": "open"}]))
check(killed["action"] == "refused" and "kill switch" in killed["detail"] and impl_calls == [],
      "the kill switch refuses on-device mode before any edit")
check(marker(pkg) == "beta\n", "a refused on-device run leaves the live package as it was")
selfloop_ctl.set_killed(False)

cloud = selfloop.run_once(cfg=cfg(backend="cloud"), **kw(11_000_000, backlog=[{"id": "c", "title": "no", "status": "open"}]))
check(cloud["action"] == "refused" and "cloud" in cloud["detail"] and impl_calls == [],
      "on-device mode refuses a cloud backend and does not call it")

selfloop.selfdev._is_live_install = lambda: True
live_pkg = make_package('VALUE = "live"\n')
live = selfloop.run_once(cfg=cfg(), **kw(12_000_000, package_src=live_pkg,
                                        backlog=[{"id": "live", "title": "stage it", "status": "open"}]))
check(live["action"] == "queued" and installs == [], "a live install is where on-device mode runs, and approval queues it")
check(marker(live_pkg) == 'VALUE = "live"\n', "the live package is not edited while the change is queued")
staged = []
for dirpath, _dirs, files in os.walk(outs):
    if "marker.py" in files and dirpath.endswith(os.path.join("llmos", "llmos")):
        staged.append(open(os.path.join(dirpath, "marker.py"), encoding="utf-8").read())
check(staged == ['VALUE = "new"\n'], "the change exists only in the staging copy")
check(live.get("ship") and "&&" in live["ship"] and "|" not in live["ship"] and "--install-local" in live["ship"],
      "the queued command is the light gate && the local installer")
selfloop_ctl.assert_gated(live["ship"])
selfloop.selfdev._is_live_install = lambda: False

installed = selfloop.run_once(cfg=cfg(require_approval=False),
                             **kw(13_000_000, package_src=live_pkg,
                                  backlog=[{"id": "go", "title": "install", "status": "open"}]))
check(installed["action"] == "installed" and len(installs) == 1, "with approval off, the local install runs after the gate")
check(marker(live_pkg) == 'VALUE = "live"\n', "the injected install is what would write; the test's live file stays put")

impl_calls.clear()


def gate_fail(_support, _tests):
    return False, "FAIL tools/test-selfloop-device.py"


limited = selfloop.run_once(cfg=cfg(max_iterations=2, require_approval=False),
                           **kw(14_000_000, package_src=live_pkg, gate=gate_fail,
                                backlog=[{"id": "rounds", "title": "retry", "status": "open"}]))
check(limited["action"] == "discarded" and impl_calls == ["rounds", "rounds"] and len(installs) == 1,
      "a failing gate retries up to max_iterations and does not install")
check(marker(live_pkg) == 'VALUE = "live"\n', "a discarded on-device run leaves the live package as it was")
check(selfloop._device_refused({"mode": "device", "backend": "local"}, os.path.join(ROOT, "src/rootfs/usr/lib/llmos"), None),
      "on-device mode will not install into the source tree")

# --- signed install, health-check rollback, and the network-service refusal ---
for name in ("desk",):
    check(selfloop_local.assert_restart([name]) == [name], name + " may be named")
check(selfloop_local.assert_restart([]) == [], "an empty restart list is the one the loop uses")
for blocked in ("iwd", "networking", "sshd", "nftables", "tailscaled", "llmos-model", "wpa_supplicant"):
    try:
        selfloop_local.assert_restart([blocked])
        check(False, "refused restart of " + blocked)
    except selfloop_local.LocalModelError as e:
        check("refusing" in str(e), "refused restart of " + blocked)
try:
    selfloop_local.assert_restart(["not-a-service"])
    check(False, "an unknown service is refused")
except selfloop_local.LocalModelError:
    check(True, "an unknown service is refused")


def health_script(code):
    path = os.path.join(state, f"health-{code}.sh")
    open(path, "w", encoding="utf-8").write(f"#!/bin/sh\nexit {code}\n")
    os.chmod(path, 0o755)
    return path


def run_install(live, staging_text, hook, restart=None):
    staging = make_package(staging_text)
    # staging here is a package root; install_local compares package roots, so copy the live tree's shape
    os.environ["LLMOS_HEALTH_CHECK"] = hook
    os.environ["LLMOS_BOOT_FAILED"] = os.path.join(state, "no-boot-failed")
    ota_state = tempfile.mkdtemp(prefix="ota-", dir=state)
    ok, detail = selfloop_local.install_local(live, staging, ota_state, restart=restart)
    return ok, detail, marker(live)


live_ok = make_package('VALUE = "old"\n')
ok, detail, text = run_install(live_ok, 'VALUE = "new"\n', health_script(0))
check(ok and text == 'VALUE = "new"\n' and "installed" in detail, "a signed update with a passing health check is installed")
spy = []
real_run = selfloop_local.subprocess.run


def wrapped(argv, *args, **kwargs):
    spy.append(list(argv))
    return real_run(argv, *args, **kwargs)


selfloop_local.subprocess.run = wrapped
try:
    ok_net, detail_net, text_net = run_install(live_ok, 'VALUE = "nope"\n', health_script(0), restart=["iwd"])
finally:
    selfloop_local.subprocess.run = real_run
check(not ok_net and "network" in detail_net and text_net == 'VALUE = "new"\n',
      "naming a network service installs nothing")
check(not any("rc-service" in part for argv in spy for part in argv), "that refusal does not restart anything")

live_bad = make_package('VALUE = "old"\n')
ok, detail, text = run_install(live_bad, 'VALUE = "new"\n', health_script(1))
check(not ok and text == 'VALUE = "old"\n' and "put back" in detail,
      "a failed health check rolls the previous files back")
live_syntax = make_package('VALUE = "old"\n')
os.environ["LLMOS_HEALTH_CHECK"] = ""
ok, detail, text = run_install(live_syntax, "def (\n", "")
check(not ok and text == 'VALUE = "old"\n' and "put back" in detail,
      "files that do not compile are rolled back")

# a private key that does not match the pin must not install
live_key = make_package('VALUE = "pinned"\n')
ok, _detail, text = run_install(live_key, 'VALUE = "first"\n', health_script(0))
check(ok and text == 'VALUE = "first"\n', "the first install pins the signing key")
# find the pin written beside that install's state. The last ota-* dir holds it; recreate via a known dir.
key_live = make_package('VALUE = "first"\n')
key_state = tempfile.mkdtemp(prefix="keys-", dir=state)
selfloop_local.ensure_signing_key(os.path.join(key_state, "keys"))
pin = open(os.path.join(key_state, "keys", "pinned.pub"), encoding="utf-8").read()
priv = os.path.join(key_state, "keys", "selfloop")
os.remove(priv)
os.remove(priv + ".pub")
subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "other", "-f", priv], check=True,
               stdout=subprocess.DEVNULL)
os.chmod(priv, 0o600)
os.environ["LLMOS_SELFLOOP_SIGNING_KEY"] = priv
# pin a different public key than the one we just generated, in the directory install_local will use
swap_state = tempfile.mkdtemp(prefix="swap-", dir=state)
os.makedirs(os.path.join(swap_state, "keys"))
open(os.path.join(swap_state, "keys", "pinned.pub"), "w", encoding="utf-8").write(pin)
shutil.copy(priv, os.path.join(swap_state, "keys", "selfloop"))
shutil.copy(priv + ".pub", os.path.join(swap_state, "keys", "selfloop.pub"))
os.chmod(os.path.join(swap_state, "keys", "selfloop"), 0o600)
staging_swap = make_package('VALUE = "second"\n')
os.environ["LLMOS_SELFLOOP_SIGNING_KEY"] = ""
os.environ.pop("LLMOS_SELFLOOP_SIGNING_KEY", None)
os.environ["LLMOS_HEALTH_CHECK"] = health_script(0)
ok, detail = selfloop_local.install_local(key_live, staging_swap, swap_state)
check(not ok and "signature" in detail and marker(key_live) == 'VALUE = "first"\n',
      "a signature that does not match the pinned key installs nothing")

print("all good" if not fails else f"{fails} failed")
shutil.rmtree(state, ignore_errors=True)
sys.exit(1 if fails else 0)
