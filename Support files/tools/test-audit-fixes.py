#!/usr/bin/env python3
"""Host test of the 2026-11-06 audit fixes (docs/audit-20261106/VALIDATION.md): integrity and correctness only;
none of them asks the owner anything new or refuses the owner anything.

Checks: _in_home resolves symlinks; restore_backup brings back only the backed-up folders, never symlinks or
hidden folders, with plain modes; open_app runs a plain command line as its own argv (a quoted path with spaces
stays one argument) and keeps the shell for shell syntax; ImageMagick text is drawn as written ("@file", "%[...]");
ffmpeg is local-files only; web_security_scan keeps only real http(s):// schemes; the folder share and the local
website never follow a symlink out of their folder, hide dot-files for GET and HEAD, and the local website answers
only to localhost; a stale share.json pid is not a share; mail replies resolve to one sender; mpv titles are not
expanded; OTA refuses an older (replayed) or another machine's manifest; devlink's freshness check rejects NaN;
the desk's form substitution is one pass; run_command confirmations list every command; model-run keeps a path with
spaces whole.
Run: python3 tools/test-audit-fixes.py"""
import http.client
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "src/rootfs/usr/lib/llmos")
TMP = tempfile.mkdtemp(prefix="audit-fixes-")
HOME = os.path.join(TMP, "home")
os.makedirs(HOME)
os.environ["LLMOS_HOME"] = HOME
os.environ.setdefault("LLMOS_RUN", os.path.join(TMP, "run"))
os.environ.setdefault("LLMOS_OTA_DIR", os.path.join(TMP, "ota"))
sys.path.insert(0, LIB)
from llmos import config, tools, share, mail, media, ota  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


class Ctx:
    headless = False

    def __init__(self):
        self.launched = []

    def launch(self, argv, name=""):
        self.launched.append(list(argv))
        return None

    def status(self, *a):
        pass


try:
    # ---- H093: _in_home follows symlinks
    outside = os.path.join(TMP, "outside")
    os.makedirs(outside)
    os.symlink(outside, os.path.join(HOME, "link-out"))
    os.makedirs(os.path.join(HOME, "Documents"))
    check(tools._in_home(os.path.join(HOME, "Documents")), "a real folder in home is in home")
    check(not tools._in_home(os.path.join(HOME, "link-out")), "a symlink in home that points outside is not in home")
    check(not tools._in_home(os.path.join(HOME, "Documents", "..", "..", "outside")), ".. out of home is not in home")

    # ---- H084/H085/36: restore_backup
    usb = os.path.join(TMP, "usb")
    day = os.path.join(usb, "LLM OS backup", "2026-11-01")
    os.makedirs(os.path.join(day, "Documents", "sub"))
    os.makedirs(os.path.join(day, ".llmos"))
    os.makedirs(os.path.join(day, "Pictures"))
    open(os.path.join(day, "Documents", "a.txt"), "w").write("a")
    open(os.path.join(day, "Documents", "sub", "run.sh"), "w").write("#!/bin/sh\n")
    os.chmod(os.path.join(day, "Documents", "sub", "run.sh"), 0o4777)
    open(os.path.join(day, ".llmos", "tasks.json"), "w").write("[]")
    secret = os.path.join(TMP, "secret.txt")
    open(secret, "w").write("not yours")
    os.symlink(secret, os.path.join(day, "Documents", "evil.txt"))
    os.symlink(outside, os.path.join(day, "Pictures", "linkdir"))
    open(os.path.join(outside, "x.png"), "w").write("x")
    tools._usb_target = lambda: (usb, {"path": "/dev/sdz1"})
    r = tools.restore_backup({}, Ctx())
    check(os.path.isfile(os.path.join(HOME, "Documents", "a.txt")), f"a backed-up file comes back ({r})")
    check(not os.path.lexists(os.path.join(HOME, ".llmos", "tasks.json")), "a hidden folder on the stick is not restored")
    check(not os.path.lexists(os.path.join(HOME, "Documents", "evil.txt")), "a symlink on the stick is not followed")
    check(not os.path.lexists(os.path.join(HOME, "Pictures", "linkdir")), "a symlinked folder on the stick is not followed")
    mode = os.stat(os.path.join(HOME, "Documents", "sub", "run.sh")).st_mode & 0o7777
    check(mode == 0o755, f"restored modes are plain (no setuid, no world write): {oct(mode)}")

    # ---- 33/H087: open_app argv
    check(tools._open_argv("gimp '/home/me/My Photo.png'") == ["gimp", "/home/me/My Photo.png"],
          "a quoted path with spaces is one argument")
    check(tools._open_argv("foot -e htop") == ["foot", "-e", "htop"], "a plain command line runs without a shell")
    check(tools._open_argv("foot -e sh -c 'ls | less'")[:2] == ["/bin/sh", "-c"], "shell syntax still goes to the shell")
    check(tools._open_argv("echo $HOME")[:2] == ["/bin/sh", "-c"], "a variable still goes to the shell")
    check(tools._open_argv("ls ~/Music")[:2] == ["/bin/sh", "-c"], "~ still goes to the shell")

    # ---- H073: ImageMagick text
    ops = tools._image_step("add text '@/etc/passwd' at the top", 1000, 800)
    check(ops and ops[-1] == "\\@/etc/passwd", f"'@file' text is drawn, not read: {ops and ops[-1]!r}")
    ops = tools._image_step("add text '100%[hex:u]' at the bottom", 1000, 800)
    check(ops and ops[-1] == "100%%[hex:u]", f"% escapes are drawn literally: {ops and ops[-1]!r}")
    env = tools._magick_env()
    pol = os.path.join(env.get("MAGICK_CONFIGURE_PATH", "").split(":")[0], "policy.xml")
    check(os.path.isfile(pol) and 'pattern="URL"' in open(pol).read() and 'pattern="@*"' in open(pol).read(),
          "ImageMagick runs with LLM OS's no-network, no-@file policy")

    # ---- 30: ffmpeg local only
    check(tools._FFMPEG_LOCAL == "file,pipe", "ffmpeg protocol whitelist is local files only")
    src = open(os.path.join(LIB, "llmos", "tools.py"), encoding="utf-8").read()
    check(src.count('"-protocol_whitelist", _FFMPEG_LOCAL') >= 3, "every ffmpeg conversion uses the whitelist")

    # ---- H090: web_security_scan
    seen = []
    real_run, real_which = subprocess.run, shutil.which
    tools.subprocess.run = lambda argv, **k: (seen.append(argv), types.SimpleNamespace(stdout="", returncode=0))[1]
    tools.shutil.which = lambda n: "/usr/bin/nikto" if n == "nikto" else real_which(n)
    tools.web_security_scan({"address": "httpfoo.lan"}, Ctx())
    check(seen and seen[-1][2] == "http://httpfoo.lan", f"'httpfoo.lan' is a host name: {seen and seen[-1][2]}")
    tools.web_security_scan({"address": "https://my.site"}, Ctx())
    check(seen[-1][2] == "https://my.site", "https:// stays https://")
    tools.subprocess.run, tools.shutil.which = real_run, real_which

    # ---- 40/H054: share translate_path and hidden HEAD
    shared = os.path.join(TMP, "shared")
    os.makedirs(os.path.join(shared, ".hidden"))
    open(os.path.join(shared, "ok.txt"), "w").write("fine")
    open(os.path.join(shared, ".hidden", "k"), "w").write("key")
    os.symlink(secret, os.path.join(shared, "leak.txt"))
    import socket as _s
    so = _s.socket()
    so.bind(("127.0.0.1", 0))
    port = so.getsockname()[1]
    so.close()
    threading.Thread(target=share._serve, args=(shared, "CODE", port), daemon=True).start()

    def get(method, path, host=None, p=None):
        for _ in range(50):
            try:
                c = http.client.HTTPConnection("127.0.0.1", p or port, timeout=5)
                c.putrequest(method, path, skip_host=bool(host))
                if host:
                    c.putheader("Host", host)
                c.endheaders()
                r = c.getresponse()
                body = r.read()
                return r.status, body
            except ConnectionRefusedError:
                time.sleep(0.1)
        return None, b""
    check(get("GET", "/CODE/ok.txt")[0] == 200, "share: a file in the folder is served")
    st, body = get("GET", "/CODE/leak.txt")
    check(st == 404 and b"not yours" not in body, f"share: a symlink out of the folder is not served ({st})")
    check(get("HEAD", "/CODE/.hidden/k")[0] == 404, "share: HEAD of a hidden file is 404")

    # ---- H055: stale share pid
    os.makedirs(config.data(""), exist_ok=True)
    import json
    json.dump({"folder": shared, "code": "x", "port": 1, "pid": os.getpid()}, open(config.data("share.json"), "w"))
    check(share.current() is None, "share.json whose pid is another program is not a share")

    # ---- 24/H030: local website
    from llmos import webserve
    from http.server import ThreadingHTTPServer
    site = os.path.join(TMP, "site")
    os.makedirs(os.path.join(site, ".llmos"))
    open(os.path.join(site, "index.html"), "w").write("<p>hi</p>")
    os.makedirs(os.path.join(site, "sub", ".git"))
    open(os.path.join(site, "sub", "page.html"), "w").write("<p>sub</p>")
    open(os.path.join(site, ".llmos", "settings.json"), "w").write("{}")
    os.symlink(secret, os.path.join(site, "leak.txt"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), webserve.handler(site))
    wport = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    check(get("GET", "/index.html", p=wport)[0] == 200, "website: a page is served to 127.0.0.1")
    check(get("GET", "/index.html", host="localhost:%d" % wport, p=wport)[0] == 200, "website: localhost works too")
    check(get("GET", "/index.html", host="evil.example:%d" % wport, p=wport)[0] == 404, "website: a rebound host name gets nothing")
    check(get("GET", "/.llmos/settings.json", p=wport)[0] == 404, "website: hidden folders are not served")
    check(get("GET", "/leak.txt", p=wport)[0] == 404, "website: a symlink out of the folder is not served")
    st, body = get("GET", "/sub/", p=wport)
    check(st == 200 and b"page.html" in body and b".git" not in body, f"website: listing hides dot-files ({st})")
    srv.shutdown()

    # ---- 25: mail reply resolves to one sender
    hits = [{"uid": "9", "folder": "INBOX", "from": "Ann Lee <ann@a.com>", "subject": "Hi"},
            {"uid": "7", "folder": "INBOX", "from": "Ann Smith <ann@b.com>", "subject": "Yo"}]
    real_find = mail.find
    mail.find = lambda q, limit=5: [h for h in hits][:limit]
    try:
        mail.resolve("ann", exact=True)
        check(False, "two senders called Ann: the reply is not sent to the newest")
    except mail.MailError as e:
        check("[9]" in str(e) and "[7]" in str(e), "two senders called Ann: both are named, with their ids")
    check(mail.resolve("ann@b.com", exact=True) == ("INBOX", "7"), "an exact address picks that sender")
    check(mail.resolve("ann") == ("INBOX", "9"), "reading still takes the newest match")
    mail.find = lambda q, limit=5: [hits[0], dict(hits[0], uid="3")][:limit]
    check(mail.resolve("ann", exact=True) == ("INBOX", "9"), "one sender: their newest message")
    mail.find = real_find

    # ---- H082/H083: mpv
    msrc = open(os.path.join(LIB, "llmos", "media.py"), encoding="utf-8").read()
    check('.replace("$", "$$")' in msrc and "umask=0o077" in msrc and '["--", info["url"]]' in msrc,
          "mpv: title not expanded, socket owner-only, the address is never an option")

    # ---- 8: OTA freshness
    check(ota.manifest_fresh({"created": 200}, {"created": 100}) is True, "ota: a newer manifest is fresh")
    check(ota.manifest_fresh({"created": 50}, {"created": 100}) is not True, "ota: an older (replayed) manifest is refused")
    check(ota.manifest_fresh({}, {"created": 100}) is True, "ota: a manifest without a time still installs (older tools)")
    check(ota.manifest_fresh({"created": 1, "hosts": ["other"]}, {}, host="me") is not True, "ota: another machine's update is refused")
    check(ota.manifest_fresh({"created": 1, "hosts": ["me"]}, {}, host="me") is True, "ota: an update for this machine installs")
    check(ota.manifest_fresh({"created": float("nan")}, {"created": 1}) is not True, "ota: a NaN time is refused")

    # ---- H025: OTA archive folders
    import tarfile as _tar
    def member(name, kind):
        t = _tar.TarInfo(name)
        t.type = _tar.DIRTYPE if kind == "dir" else _tar.REGTYPE
        return t
    check(ota._member_ok(member("usr/lib/llmos/llmos", "dir")) == "usr/lib/llmos/llmos", "ota: LLM OS's own folder is accepted")
    check(ota._member_ok(member("usr/lib", "dir")) == "usr/lib", "ota: a parent folder is accepted (created, never re-permissioned)")
    for bad in ("etc/ssh", "root", "var/lib/llmos", "home/owner"):
        try:
            ota._member_ok(member(bad, "dir"))
            check(False, f"ota: folder {bad} is refused")
        except ValueError:
            check(True, f"ota: folder {bad} is refused")
    osrc = open(os.path.join(LIB, "llmos", "ota.py"), encoding="utf-8").read()
    check("if t.isdir() and not _dir_inside(name):" in osrc, "ota: parent folders are created, not chmod-ed")

    # ---- H026: devlink NaN
    dsrc = open(os.path.join(LIB, "llmos", "devlink.py"), encoding="utf-8").read()
    check("math.isfinite(ts)" in dsrc, "devlink: a NaN/inf timestamp is not fresh")

    # ---- H098: desk.js one-pass substitution (run with node when it is here)
    js = open(os.path.join(HERE, "..", "src/rootfs/usr/share/llmos/desk/desk.js"), encoding="utf-8").read()
    check('s.split("{" + k + "}").join(inp.value)' not in js, "desk.js: no sequential field substitution")
    if shutil.which("node"):
        prog = ("const inputs={a:{value:'{b}'},b:{value:'B'}};const t='say {a} and {b} and {c}';"
                "console.log(t.replace(/\\{([^{}]+)\\}/g,(all,k)=>Object.prototype.hasOwnProperty.call(inputs,k)?inputs[k].value:all));")
        out = subprocess.run(["node", "-e", prog], capture_output=True, text=True).stdout.strip()
        check(out == "say {b} and B and {c}", f"one pass: a typed '{{b}}' stays as typed: {out!r}")
        check("/\\{([^{}]+)\\}/g, (all, k) => Object.prototype.hasOwnProperty.call(inputs, k) ? inputs[k].value : all" in js,
              "desk.js uses that one-pass substitution")

    # ---- 4: run_command confirmation shows every command
    from llmos import desk as _desk
    fake = types.SimpleNamespace()
    text = _desk.Desk.describe_args(fake, tools.REGISTRY["run_command"], {"commands": ["touch a", "touch b"]})
    check("touch a" in text and "touch b" in text, f"both commands are shown: {text!r}")

    # ---- H080: format_drive with several drives erases only the one named
    from llmos import syspanels, system as _system
    two = [{"path": "/dev/sdb1", "label": "BACKUP", "size": "2 TB", "fstype": "ext4", "mountpoint": "", "disk": "/dev/sdb"},
           {"path": "/dev/sdc1", "label": "STICK", "size": "16 GB", "fstype": "vfat", "mountpoint": "", "disk": "/dev/sdc"}]
    erased = []
    real_rem, real_fmt, real_which2 = syspanels.removable, _system.format_drive, tools.shutil.which
    syspanels.removable = lambda: list(two)
    _system.format_drive = lambda disk, label: (erased.append(disk), (0, "", ""))[1]
    tools.shutil.which = lambda n: "/sbin/" + n if n.startswith("mkfs") else real_which2(n)
    r = tools.format_drive({}, Ctx())
    check(not erased and "/dev/sdb" in r and "/dev/sdc" in r, f"two drives, none named: nothing erased, both listed ({r[:80]})")
    tools.format_drive({"drive": "stick"}, Ctx())
    check(erased == ["/dev/sdc"], f"the drive named STICK is the one erased: {erased}")
    syspanels.removable = lambda: [two[1]]
    erased.clear()
    tools.format_drive({}, Ctx())
    check(erased == ["/dev/sdc"], "one drive: it is erased as before")
    syspanels.removable, _system.format_drive, tools.shutil.which = real_rem, real_fmt, real_which2

    # ---- 26: model path with spaces
    mr = open(os.path.join(HERE, "..", "src/rootfs/usr/bin/llmos-model-run"), encoding="utf-8").read()
    fake_bin = os.path.join(TMP, "bin")
    os.makedirs(fake_bin)
    script = mr.replace("/usr/bin/llmos serve-argv", "'" + os.path.join(fake_bin, "llmos") + "' serve-argv") \
               .replace("echo 800 > /proc/self/oom_score_adj", "true")
    # the fake prints argv[0]=python, -c, code; add a spaced argument through serve-argv's format
    open(os.path.join(fake_bin, "llmos"), "w").write(
        "#!/bin/sh\nprintf '%s\\n%s\\n%s\\n%s' '" + sys.executable + "' -c 'import sys; print(sys.argv[1])' '/m/My Model *.gguf'\n")
    os.chmod(os.path.join(fake_bin, "llmos"), 0o755)
    open(os.path.join(fake_bin, "run"), "w").write(script)
    out = subprocess.run(["/bin/sh", os.path.join(fake_bin, "run")], capture_output=True, text=True, timeout=30).stdout.strip()
    check(out == "/m/My Model *.gguf", f"model-run passes a path with spaces as one argument: {out!r}")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print("all ok" if not fails else f"{fails} failed")
sys.exit(1 if fails else 0)
