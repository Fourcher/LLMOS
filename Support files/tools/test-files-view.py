#!/usr/bin/env python3
"""Host-side check of the files view: 'show as list' / 'switch to icons' route to show_files with a view,
and show_files saves the owner's choice and emits it on the list block. Run: python3 tools/test-files-view.py"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent, tools as T, config  # noqa: E402
intent._note_exists = lambda ref: True


def route(text, want):
    got = intent._match(text)
    assert got == want, f"{text!r}: got {got!r}, want {want!r}"
    print(f"ok {text!r} -> {got!r}")


# the folder on screen: last one shown, else home
T._LAST_FOLDER = None
route("show as list", ("show_files", {"path": "~", "view": "list"}))
route("switch to icons", ("show_files", {"path": "~", "view": "icons"}))
route("show my files as big icons", ("show_files", {"path": "~", "view": "icons"}))
route("put them in thumbnails", ("show_files", {"path": "~", "view": "icons"}))
route("show these as a grid", ("show_files", {"path": "~", "view": "icons"}))
route("please show my files in details view", ("show_files", {"path": "~", "view": "list"}))
T._LAST_FOLDER = "/root/Downloads"
route("show as list", ("show_files", {"path": "/root/Downloads", "view": "list"}))
T._LAST_FOLDER = None

# bare view phrases (sweep)
route("show big icons", ("show_files", {"path": "~", "view": "icons"}))
route("big icons", ("show_files", {"path": "~", "view": "icons"}))
route("show icons", ("show_files", {"path": "~", "view": "icons"}))
route("icon view", ("show_files", {"path": "~", "view": "icons"}))
route("please use grid view.", ("show_files", {"path": "~", "view": "icons"}))
route("list view", ("show_files", {"path": "~", "view": "list"}))
route("show details view", ("show_files", {"path": "~", "view": "list"}))
T._LAST_FOLDER = "/root/Downloads"
route("list view", ("show_files", {"path": "/root/Downloads", "view": "list"}))
T._LAST_FOLDER = None
r = intent._match("show icons on the desktop")
assert r != ("show_files", {"path": "~", "view": "icons"}), r
print("ok 'show icons on the desktop' is not the bare view route ->", r)
print("print only: 'show list' ->", intent._match("show list"))

# not the view route: unchanged from before
r = intent._match("show me a list of my files")
assert r is None, r
print("ok 'show me a list of my files' ->", r)
r = intent._match("I'd like them as a list")
print("print only: 'I'd like them as a list' ->", r)

# the schema carries the view parameter
spec = T.REGISTRY.get("show_files")
assert spec is not None and "view" in spec.params, spec
assert spec.params["view"]["enum"] == ["list", "icons"], spec.params["view"]
print("ok schema view enum", spec.params["view"]["enum"])

# show_files: the choice is saved and emitted on the list block (stubbed settings and window)
class StubSettings:
    def __init__(self):
        self.d = {}

    def get(self, k, default=None):
        return self.d.get(k, default)

    def set(self, k, v):
        self.d[k] = v

    def all(self):
        return dict(self.d)


saved = config.settings
shown = []
real_show = T.show
config.settings = StubSettings()
T.show = lambda ctx, spec: shown.append(spec)
try:
    d = tempfile.mkdtemp()
    open(os.path.join(d, "a.txt"), "w").close()
    T.show_files({"path": d, "view": "icons"}, None)
    assert config.settings.get("files_view") == "icons"
    blk = [b for b in shown[-1]["blocks"] if b.get("type") == "list"][0]
    assert blk["view"] == "icons", blk
    print("ok show_files view=icons saved and emitted")
    T.show_files({"path": d}, None)
    blk = [b for b in shown[-1]["blocks"] if b.get("type") == "list"][0]
    assert blk["view"] == "icons", blk
    print("ok show_files without view keeps the saved choice")
finally:
    config.settings = saved
    T.show = real_show
print("all good")
