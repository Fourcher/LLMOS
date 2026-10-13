#!/usr/bin/env python3
"""Host-side test of two answer-at-once phrasings in llmos/desk.py, read from the source with ast (desk.py needs GTK):
"open my browser bookmarks" / "bookmarks" open the browser's bookmarks (the bms2 alternative of the browser-key route),
and "change homepage" / "set my home page to bbc.com" get the Firefox homepage answer (the _HOWTO homepage entry).
Matching is the desk's own: l2 = low.rstrip("?.!") with low = text.lower().strip(); the first _HOWTO entry whose pattern
fullmatches l2 wins. Adversarial phrases must not match.
Run: python3 tools/test-bookmarks-howto.py"""
import ast
import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
tree = ast.parse(open(SRC, encoding="utf-8").read())
fails = 0


def check(cond, msg):
    global fails
    if cond:
        print("ok " + msg)
    else:
        fails += 1
        print("FAIL " + msg)


def norm(text):
    low = text.lower().strip()
    return low, low.rstrip("?.!")


# the browser-key route: the re.fullmatch call whose pattern holds the bms2 group
BROWSER = None
for node in ast.walk(tree):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "fullmatch"
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "re" and node.args
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
            and "(?P<bms2>" in node.args[0].value):
        BROWSER = re.compile(node.args[0].value)
assert BROWSER, "browser-key route with bms2 not found in desk.py"

# the _HOWTO table: plain (pattern, reply) tuples
HOWTO = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_HOWTO" for t in node.targets):
        HOWTO = [(re.compile(rx), text) for rx, text in ast.literal_eval(node.value)]
assert HOWTO, "_HOWTO not found in desk.py"
HOMEPAGE = next(text for rx, text in HOWTO if text.startswith("In Firefox: open the menu"))


def howto(text):
    """The desk's _howto: first entry whose pattern fullmatches the normalised text."""
    _, l2 = norm(text)
    for rx, reply in HOWTO:
        if rx.fullmatch(l2):
            return reply
    return None


def bookmarks_group(text):
    """The group that the browser-key route would take for this text, or None."""
    _, l2 = norm(text)
    m = BROWSER.fullmatch(l2)
    if not m:
        return None
    return "bms" if m.group("bms") else "bms2" if m.group("bms2") else m.lastgroup


print("bookmarks phrases (new)")
for phrase in ("open my browser bookmarks", "show my browser bookmarks", "open firefox bookmarks", "show me the firefox favourites",
               "open my firefox favorites", "bookmarks", "my bookmarks", "Bookmarks?"):
    check(bookmarks_group(phrase) in ("bms", "bms2"), f"bookmarks: {phrase!r} -> {bookmarks_group(phrase)}")

print("bookmarks phrases (old, still answered by the same group)")
for phrase, group in (("open my bookmarks", "bms"), ("show me the bookmarks", "bms"), ("bookmark this page", "bm"),
                      ("zoom in", "zin")):
    check(bookmarks_group(phrase) == group, f"old: {phrase!r} -> {bookmarks_group(phrase)} (want {group})")

print("bookmarks adversarial (must not match the bookmarks route)")
for phrase in ("delete my bookmarks", "remove my bookmarks", "bookmark this page", "home page of bbc", "go to my home folder",
               "set my home address", "my firefox bookmarks are gone"):
    got = bookmarks_group(phrase)
    if phrase == "bookmark this page":
        check(got == "bm", f"adversarial: {phrase!r} stays on the existing bm route")
    else:
        check(got is None, f"adversarial: {phrase!r} -> {got}")

print("homepage phrases (new)")
for phrase in ("change homepage", "change my home page", "change my homepage", "change the start page", "set my homepage",
               "set my home page to bbc.com", "make my start page to google", "set the start page to news.com",
               "how do i change my home page", "how do i set home page", "how do i change homepage"):
    check(howto(phrase) == HOMEPAGE, f"homepage: {phrase!r}")

print("homepage phrases (old, still answered by the same entry)")
for phrase in ("pick my homepage", "how do i change my homepage", "set the browser's homepage", "change firefox's start page"):
    check(howto(phrase) == HOMEPAGE, f"old homepage: {phrase!r}")

print("homepage adversarial (must not get the homepage answer)")
for phrase in ("set my home address", "home page of bbc", "go to my home folder", "delete my bookmarks", "bookmark this page"):
    got = howto(phrase)
    check(got != HOMEPAGE, f"adversarial: {phrase!r} -> {'no answer' if got is None else got[:40]!r}")

if fails:
    print(f"{fails} FAIL")
    sys.exit(1)
print("all good")
