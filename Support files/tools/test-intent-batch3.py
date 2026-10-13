#!/usr/bin/env python3
"""Host-side table test of batch 3 of the instant intent routes (llmos/intent.py).
Each row: phrase, the result at 79a7311 (before), the expected result now (after).
Run: python3 tools/test-intent-batch3.py  (no VM, no network)."""
import os
import sys
import urllib.parse

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True

OSM = "https://www.openstreetmap.org/search?query="
CLAUDE = ("online_model", {"action": "sign in", "provider": "claude"})
CHATGPT = ("online_model", {"action": "sign in", "provider": "chatgpt"})

# (phrase, before at 79a7311, expected now)
ROWS = [
    # 1. share over / on the network -> share_folder with no folder
    ("share over the network", None, ("share_folder", {})),
    ("share on the network", None, ("share_folder", {})),
    # 2. mail setup by provider: not done (the mail-setup route gives None for "add my outlook mail" too)
    ("add my outlook account", None, None),
    ("set up my gmail account", None, None),
    ("connect my yahoo account", None, None),
    ("add my icloud account", None, None),
    ("add my outlook mail", None, None),
    # 3. use my <provider> account -> the sign-in result
    ("use my claude account", None, CLAUDE),
    ("use my chatgpt account", None, CHATGPT),
    ("sign in with my claude account", CLAUDE, CLAUDE),
    ("sign in to claude", CLAUDE, CLAUDE),
    ("use chatgpt", ("browse", {"site": "chatgpt"}), ("browse", {"site": "chatgpt"})),
    # 4. map of <place> -> OpenStreetMap search
    ("map of paris", None, ("browse", {"site": OSM + urllib.parse.quote("paris")})),
    ("show me a map of tokyo", None, ("browse", {"site": OSM + urllib.parse.quote("tokyo")})),
    ("map of london please", None, ("browse", {"site": OSM + urllib.parse.quote("london")})),
    ("map of the world", None, ("browse", {"site": OSM + urllib.parse.quote("the world")})),
    # 5. do I have new email (any optional)
    ("do I have new email", None, ("mail_inbox", {})),
    ("do i have new mail", None, ("mail_inbox", {})),
    ("any new email?", ("mail_inbox", {}), ("mail_inbox", {})),
    ("do i have any new email", ("mail_inbox", {}), ("mail_inbox", {})),
    ("do I have new messages on whatsapp", None, None),
    # 6. youtube music -> music.youtube.com
    ("youtube music", None, ("browse", {"site": "https://music.youtube.com"})),
    ("open youtube music", None, ("browse", {"site": "https://music.youtube.com"})),
    ("youtube music video for despacito", None, None),
    # 7. sign out / log out: not done (the lock is a desk shortcut with no intent route); must not match
    ("sign out", None, None),
    ("log out", None, None),
    ("sign me out", None, None),
    ("log me out", None, None),
    ("log out of facebook", None, None),
    ("sign out of gmail", None, None),
    ("share my screen", None, None),
]


def main():
    bad = 0
    print(f"{'phrase':36} {'before (79a7311)':44} {'after':44} ok?")
    for phrase, before, want in ROWS:
        got = intent.match(phrase)
        ok = got == want
        bad += 0 if ok else 1
        print(f"{phrase:36} {str(before):44.44} {str(got):44.44} {'ok' if ok else 'FAIL'}")
        if ok:
            print(f"ok {phrase}")
        else:
            print(f"FAIL {phrase!r}: got {got!r}, want {want!r}")
    if bad:
        print(f"{bad} FAIL")
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
