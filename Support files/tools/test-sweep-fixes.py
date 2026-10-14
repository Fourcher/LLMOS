#!/usr/bin/env python3
"""Host-side regression tests for the bugs the 2026-10-14 feature sweep found (docs/research/feature-sweep-2026-10-14).
Run: python3 tools/test-sweep-fixes.py  (exit status 0 = pass)"""
import os
import sys
import tempfile

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
HOME = tempfile.mkdtemp(prefix="sweep-home-")
os.environ["LLMOS_HOME"] = HOME
os.environ["LLMOS_ETC"] = os.path.join(HOME, "etc")      # settings written here, not through the root helper
os.makedirs(os.environ["LLMOS_ETC"], exist_ok=True)
for d in ("Documents/Sweep Test", "Downloads", "Desktop"):
    os.makedirs(os.path.join(HOME, d), exist_ok=True)
open(os.path.join(HOME, "Documents", "my-notes.txt"), "w").write("x\n")

from llmos import agent, everyday, intent  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(("ok " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


# 1. delete: the model sends its arguments as JSON text; execute read .get on that text ("'str' object has no attribute 'get'")
from llmos import desk  # noqa: E402


class _Desk:
    windows = {}

    def emit(self, m):
        pass

    def describe_tool(self, *a, **k):
        return "x"

    def __getattr__(self, k):
        return lambda *a, **kw: None


class Ctx(desk.DeskCtx):
    def confirm_action(self, *a, **k):
        return True

    def confirm_network(self, *a, **k):
        return True


def ctx():
    c = Ctx(_Desk())
    c.current_request = "delete it"
    return c


target = os.path.join(HOME, "Documents", "gone.txt")
open(target, "w").write("x")
try:
    out = agent.execute(ctx(), "delete_file", '{"path": "%s"}' % target)
except Exception as e:
    out = f"EXCEPTION {type(e).__name__}: {e}"
check("delete with arguments as JSON text works", "moved" in out and not os.path.exists(target), out)
out = agent.execute(ctx(), "delete_file", '{"path": "%s"}' % os.path.join(HOME, "nothing-here.txt"))
check("delete of a missing file says so", "nothing called" in out, out)

# 2. a new file "in <a folder the owner made>" goes into that folder, not into the name
r = intent.match("make a new text file called notes.txt in Sweep Test")
check("new file in a named folder", r == ("write_file", {"path": "~/Documents/Sweep Test/notes.txt", "content": "", "append": True}), r)
r = intent.match("make a text file called todo on my desktop")
check("new file on the desktop unchanged", r and r[1]["path"] == "~/Desktop/todo.txt", r)

# 3. move a file into a folder the owner made (the model's own shell command split the path at the space)
for q in ("move my-notes.txt into Sweep Test", "put my-notes.txt inside the Sweep Test folder",
          "move the file my-notes.txt into the Sweep Test folder"):
    r = intent.match(q)
    check(f"move: {q!r}", r == ("move_files", {"what": "my-notes.txt", "from": "home", "to": "~/Documents/Sweep Test", "copy": False}), r)
r = intent.match("copy my-notes.txt to the Sweep Test folder")
check("copy into a named folder", r and r[0] == "move_files" and r[1]["copy"] is True, r)
r = intent.match("move my-notes.txt into Nowhere Special")
check("move into a folder that does not exist is left to the assistant", r is None or r[0] != "move_files", r)


# 4. "write a note to my neighbour and save it as thanks.txt" is not "append to a file called 'neighbour and save it as ...'"
class D:
    said = None

    def instant_reply(self, line, text):
        D.said = text


for q in ("write a short thank-you note to my neighbour and save it as thanks.txt",):
    D.said = None
    low = q.lower()
    try:
        handled = everyday.handle(D(), q)
    except Exception:
        handled = False
    check(f"compose request is not an append: {q!r}", not (D.said or "").startswith("Added"), D.said)
check("no file named after the request", not any("save it as" in f for f in os.listdir(os.path.join(HOME, "Documents"))))
D.said = None
everyday.handle(D(), "add call the bank to todo.txt")
check("a real append still works", (D.said or "").startswith("Added"), D.said)

# 5. a program's own name opens that program (/usr/bin/Thunar made "Thunar File Manager" run as Thunar + 2 files)
from llmos import programs  # noqa: E402
a = programs.argv({"exec": "mpv --player-operation-mode=pseudo-gui --"})
check("mpv as a program gets Wayland output, no stray --", a[:3] == ["mpv", "--vo=gpu,wlshm", "--gpu-context=wayland"] and a[-1] != "--", a)
check("other programs unchanged", programs.argv({"exec": "thunar"}) == ["thunar"])

# 6. wallpaper: "a picture of mountains" searches mountains; putting it back is the default
check("wallpaper subject without 'a picture of'", intent.match("set my wallpaper to a picture of mountains") == ("set_wallpaper", {"subject": "mountains"}))
for q, want in (("put the wallpaper back to how it was", "previous"), ("undo the wallpaper", "previous"),
                ("change the wallpaper back to the original one", "default"), ("reset my wallpaper", "default")):
    check(f"wallpaper back: {q!r}", intent.match(q) == ("set_wallpaper", {"subject": want}), intent.match(q))

# 7. settings back: language and colours (they changed other settings before)
check("language back to English", intent.match("change the language back to English") == ("set_appearance", {"language": "english"}))
check("switch back to english", intent.match("switch back to english") == ("set_appearance", {"language": "english"}))
check("colour back to dark", intent.match("change the colour back to dark") == ("set_appearance", {"theme": "dark"}))
check("not a language", intent.match("switch back to blue") is None)

# 8. a question searched on the web gets an answer (the assistant), not just a browser window
check("search the web for a question -> answer", intent.match("search the web for the population of Tokyo") is None)
check("search the web for a thing -> browser", intent.match("search the web for cheap flights to Denver") == ("browse", {"search": "cheap flights to Denver"}))

# 9. which model / what version: instant answers
check("which model are you using: instant", bool(everyday.MATCH.search("which model are you using")) and bool(everyday._MODEL_Q.match("which model are you using")))

# 10. "delete notes.txt" when the file is inside a folder: the one file of that name
os.makedirs(os.path.join(HOME, "Documents", "Sweep Test"), exist_ok=True)
inner = os.path.join(HOME, "Documents", "Sweep Test", "inner-notes.txt")
open(inner, "w").write("x")
out = agent.execute(ctx(), "delete_file", '{"path": "inner-notes.txt"}')
check("delete by bare name finds the file in a folder", "moved" in out and not os.path.exists(inner), out)

# 11. "put the wallpaper back to how it was" restores the previous picture (it reset to the default)
from llmos import tools as T, config as C  # noqa: E402
pa, pb = os.path.join(HOME, "a.png"), os.path.join(HOME, "b.png")
open(pa, "wb").write(b"AAAA")
open(pb, "wb").write(b"BBBB")
T.set_wallpaper({"subject": pa}, ctx())
T.set_wallpaper({"subject": pb}, ctx())
T.set_wallpaper({"subject": "previous"}, ctx())
dest = C.data("wallpaper.img")
check("previous wallpaper comes back", open(dest, "rb").read() == b"AAAA" and C.settings.get("appearance.backdrop") == "photo")
T.set_wallpaper({"subject": "previous"}, ctx())
check("putting it back twice undoes", open(dest, "rb").read() == b"BBBB")

print("all good" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
