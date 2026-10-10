#!/usr/bin/env python3
"""Host-side test of set_default_app (llmos/tools.py) and its intent routes (llmos/intent.py):
the kind and app are found, ~/.config/mimeapps.list gets the [Default Applications] lines and keeps
everything else, unknown kinds and apps give the error strings, and the routes fire only for known kinds.
Run: python3 tools/test-default-app.py"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
apps_dir = tempfile.mkdtemp(prefix="llmos-apps-")
# never touch a real home or real mime config: xdg-mime (if present) reads these
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"),
                  HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config"))
from llmos import intent, tools  # noqa: E402

tools.APP_DIRS = [apps_dir]
with open(os.path.join(apps_dir, "firefox.desktop"), "w") as f:
    f.write("[Desktop Entry]\nType=Application\nName=Firefox\nExec=firefox %u\n")
with open(os.path.join(apps_dir, "vlc.desktop"), "w") as f:
    f.write("[Desktop Entry]\nType=Application\nName=VLC media player\nExec=vlc %U\n")

mimeapps = os.path.join(home, ".config", "mimeapps.list")
fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print(f"ok {name}")
    else:
        fails += 1
        print(f"FAIL {name} {detail}")


def read():
    with open(mimeapps) as f:
        return f.read()


# existing file: another section and a [Default Applications] line that must survive
os.makedirs(os.path.dirname(mimeapps), exist_ok=True)
with open(mimeapps, "w") as f:
    f.write("[Added Associations]\nimage/png=vlc.desktop;\n\n[Default Applications]\ntext/plain=gedit.desktop\n")
r = tools.set_default_app({"kind": "pdfs", "app": "Firefox"}, None)
txt = read()
check("pdfs+firefox reply", r == "Done: Pdfs now open in Firefox.", repr(r))
check("pdfs+firefox line written", "application/pdf=firefox.desktop" in txt.splitlines(), repr(txt))
check("other section kept", "[Added Associations]\nimage/png=vlc.desktop;" in txt, repr(txt))
check("other default line kept", "text/plain=gedit.desktop" in txt.splitlines(), repr(txt))

# missing file: created with the section
os.remove(mimeapps)
r = tools.set_default_app({"kind": "videos", "app": "VLC media player"}, None)
txt = read()
check("videos+vlc by Name reply", r == "Done: Videos now open in VLC media player.", repr(r))
check("missing file created with section", txt.startswith("[Default Applications]") and "video/mp4=vlc.desktop" in txt.splitlines(), repr(txt))

# errors
r = tools.set_default_app({"kind": "spreadsheets", "app": "firefox"}, None)
check("unknown kind error", r == "error: I don't know that kind of file yet: spreadsheets", repr(r))
r = tools.set_default_app({"kind": "pdfs", "app": "gimp"}, None)
check("unknown app error", r == "error: no installed program called gimp", repr(r))

# intent routes
got = intent.match("always open pdfs in firefox")
check("route open pdfs in firefox", got == ("set_default_app", {"kind": "pdfs", "app": "firefox"}), repr(got))
got = intent.match("make vlc my default for videos")
check("route make vlc default for videos", got == ("set_default_app", {"kind": "videos", "app": "vlc"}), repr(got))
got = intent.match("always open the door")
check("no route for unknown kind", not (got and got[0] == "set_default_app"), repr(got))
print("info contraction:", repr(intent.match("I'd like to always open pdfs in firefox")))

print("all good" if fails == 0 else f"{fails} failed")
sys.exit(1 if fails else 0)
