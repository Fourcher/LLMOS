#!/usr/bin/env python3
"""Host-side test of the new routes in llmos/intent.py (_new_words, after every other route):
"open the file manager" / "open word" / "open excel" (open_app with the name programs.find resolves),
"open /etc/hosts" / "open ~/notes.txt" (open_file path), "uninstall foo" / "remove the foo app" (remove_software name),
"apt install foo" / "apt-get install foo" / "apk add foo" (install_app packages).
Phrases that had no route before keep none where they must (the door, a file's name, the update, the background);
phrases that routed before keep their route (open calculator, install vlc, open firefox, open my documents).
Run: python3 tools/test-open-words.py  (no VM needed)."""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))   # the model catalog
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True      # the host has no lists; the VM checks the real store

CASES = {
    # new: programs by their kind (programs.find resolves each name on the VM)
    "open the file manager": ("open_app", {"command": "file manager"}),
    "open the image viewer": ("open_app", {"command": "image viewer"}),
    "open the text editor": ("open_app", {"command": "text editor"}),
    "open the notes app": ("open_app", {"command": "notes"}),
    "notes app": ("open_app", {"command": "notes"}),
    "open word": ("open_app", {"command": "word processor"}),
    "open excel": ("open_app", {"command": "spreadsheet"}),
    "I'd like to open the file manager": ("open_app", {"command": "file manager"}),
    # new: a file by its path
    "open /etc/hosts": ("open_file", {"path": "/etc/hosts"}),
    "open ~/notes.txt": ("open_file", {"path": "~/notes.txt"}),
    "open /home/owner/report.pdf": ("open_file", {"path": "/home/owner/report.pdf"}),
    # new: uninstall by one name
    "uninstall foo": ("remove_software", {"name": "foo"}),
    "remove the foo app": ("remove_software", {"name": "foo"}),
    "uninstall vlc": ("remove_software", {"name": "vlc"}),
    "remove the vlc app": ("remove_software", {"name": "vlc"}),
    # new: apt / apk install of one name
    "apt install vlc": ("install_app", {"packages": "vlc"}),
    "apt-get install git": ("install_app", {"packages": "git"}),
    "apk add curl": ("install_app", {"packages": "curl"}),
    # new: a path with spaces (quoted or not), several packages, and the owner's typos that must stay with the model
    "open ~/My Notes.txt": ("open_file", {"path": "~/My Notes.txt"}),
    "open '/tmp/a b.pdf'": ("open_file", {"path": "/tmp/a b.pdf"}),
    'open "/tmp/a b.pdf"': ("open_file", {"path": "/tmp/a b.pdf"}),
    "open ~/a/../b": None,
    "open /tmp/x; rm -rf /": None,
    "apt install htop vim": ("install_app", {"packages": "htop vim"}),
    "apt install htop vim git": ("install_app", {"packages": "htop vim git"}),
    "apt install -y htop": None,
    "apt install htop && reboot": None,
    "apk add curl; rm -rf /": None,
    "apk add a b c d e f g h i j k": None,
    # unchanged: routed before
    "open calculator": ("open_app", {"command": "calculator"}),
    "install vlc": ("install_app", {"packages": "vlc"}),
    "open firefox": ("browse", {}),
    "open my documents": ("show_files", {"path": "~/Documents"}),
    "open my last file": ("last_saved", {"open": True}),
    "open a new tab": None,
    # unchanged: no route before, none now
    "open the door": None,
    "remove the background": None,
    "uninstall the update": None,
    "uninstall": None,
    "remove duplicates": ("find_duplicates", {"folder": "~", "delete": True}),
    "remove this photo": ("which_file", {"request": "remove this photo"}),
    "remove the file notes.txt": ("delete_file", {"path": "~/notes.txt"}),
}

fails = 0
for text, want in CASES.items():
    got = intent.match(text)
    if got is not None and want is not None and got[0] == want[0] and got[1] == want[1]:
        print(f"ok {text!r} -> {got}")
    elif got == want:
        print(f"ok {text!r} -> {got}")
    else:
        fails += 1
        print(f"FAIL {text!r}: got {got}, want {want}")
if fails:
    print(f"{fails} failed")
    sys.exit(1)
print("all good")
