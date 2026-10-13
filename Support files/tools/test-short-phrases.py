#!/usr/bin/env python3
"""Host-side test of short task phrasings that must reach an existing action without the model.

Desk side (llmos/desk.py needs GTK, so its regexes are read from the source with ast, as the other desk tests do):
  "turn wifi off" -> the Wi-Fi regex with v=off; "airplane mode" -> the airplane regex with v=on;
  "open a new tab" / "close this tab" -> the browser-key table (_WIN, key route); "close the browser" -> _WIN closew;
  "bookmark this" -> the browser-key route's bm group; "bigger window" -> _WIN maximize.
Intent side (llmos/intent.py, imported): "font bigger" and "scale 150%" -> set_appearance scale; "show all apps" -> the
app list; "less blue light at night" -> night light on; "too dark, go back" -> undo.
Adversarial phrases must not reach those routes. "private window" has no existing action (no key in wm.KEYS): not tested.
Run: python3 tools/test-short-phrases.py  (no VM needed)."""
import ast
import os
import re
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
SRC = os.path.join(_ROOT, "usr/lib/llmos/llmos/desk.py")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))   # the model catalog
from llmos import intent  # noqa: E402
intent._note_exists = lambda ref: True      # the host has no lists; the VM checks the real store

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
    """The desk's own normalisation: low = text.lower().strip(); l2 = low.rstrip("?.!")."""
    low = intent.plain(text).lower().strip()
    return low, low.rstrip("?.!")


def desk_regex(must_contain):
    """The one re.fullmatch / re.compile pattern in desk.py whose text contains must_contain."""
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("fullmatch", "compile")
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "re" and node.args
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                and must_contain in node.args[0].value):
            found.append(re.compile(node.args[0].value))
    assert len(found) == 1, f"expected one desk pattern with {must_contain!r}, found {len(found)}"
    return found[0]


WIFI = desk_regex("wi-?fi (?P<v>on|off)")
AIRPLANE = desk_regex("(?:airplane|aeroplane|flight|plane) mode")
BROWSER = desk_regex("(?P<bm>bookmark")
WIN = desk_regex("(?P<key>(?:go )?back")


def wifi_v(low):
    m = WIFI.fullmatch(low.rstrip(".!"))
    return (m.group("v") or m.group("v2") or ("on" if m.group("v3") == "enable" else "off")) if m else None


def airplane_v(low):
    m = AIRPLANE.fullmatch(low.rstrip(".!"))
    if not m:
        return None
    return m.group("v") or ("off" if (m.group("v2") or "").endswith(("off", "disable")) or low.startswith(("turn off", "switch off")) else "on")


def win_action(text):
    """What _window_shortcut takes from a phrase: ('key', name) | ('closew', name) | ('maxw', name) | None."""
    _, l2 = norm(text)
    m = WIN.fullmatch(l2)
    if not m:
        return None
    g = m.groupdict()
    if g["key"]:
        k = g["key"].replace("go ", "").replace(" the page", "").replace("open ", "").replace("a new", "new").replace("this ", "").replace("the ", "")
        return ("key", {"previous page": "back", "next page": "forward", "refresh": "reload"}.get(k, k))
    if g.get("closew"):
        return ("closew", g["closew"])
    if m.group(0).startswith(("maximi", "make", "bigger", "full")):
        return ("maxw", m.group(0))
    return None


def bookmark_group(text):
    _, l2 = norm(text)
    m = BROWSER.fullmatch(l2)
    return m.lastgroup if m else None


def intent_route(text):
    return intent.match(text)


print("desk: wifi and airplane")
check(wifi_v(norm("turn wifi off")[0]) == "off", f"wifi: 'turn wifi off' -> v={wifi_v(norm('turn wifi off')[0])!r} (want off)")
check(airplane_v(norm("airplane mode")[0]) == "on", f"airplane: 'airplane mode' -> v={airplane_v(norm('airplane mode')[0])!r} (want on)")

print("desk: browser keys and windows")
check(win_action("open a new tab") == ("key", "new tab"), f"browser: 'open a new tab' -> {win_action('open a new tab')}")
check(win_action("close this tab") == ("key", "close tab"), f"browser: 'close this tab' -> {win_action('close this tab')}")
check(win_action("close the browser") == ("closew", "browser"), f"browser: 'close the browser' -> {win_action('close the browser')}")
check(bookmark_group("bookmark this") == "bm", f"browser: 'bookmark this' -> {bookmark_group('bookmark this')}")
check(win_action("bigger window") is not None and win_action("bigger window")[0] == "maxw", f"window: 'bigger window' -> {win_action('bigger window')}")

print("intent: text size, scale, apps, night light, undo")
check(intent_route("font bigger") == ("set_appearance", {"scale": "bigger"}), f"font: 'font bigger' -> {intent_route('font bigger')}")
check(intent_route("scale 150%") == ("set_appearance", {"scale": "150"}), f"scale: 'scale 150%' -> {intent_route('scale 150%')}")
check(intent_route("show all apps") == ("manage_apps", {"action": "list"}), f"apps: 'show all apps' -> {intent_route('show all apps')}")
check(intent_route("less blue light at night") == ("change_setting", {"setting": "night_light", "value": "on"}),
      f"night light: 'less blue light at night' -> {intent_route('less blue light at night')}")
check(intent_route("too dark, go back") == ("undo", {}), f"undo: 'too dark, go back' -> {intent_route('too dark, go back')}")

print("adversarial (must not reach those routes)")
check(wifi_v(norm("turn wifi off in an hour")[0]) is None and intent_route("turn wifi off in an hour") is not None
      and intent_route("turn wifi off in an hour")[0] == "schedule_task", "timed: 'turn wifi off in an hour' is a scheduled task, not the switch")
check(airplane_v(norm("airplane mode is annoying")[0]) is None and intent_route("airplane mode is annoying") is None,
      "airplane: 'airplane mode is annoying' matches no airplane route")
check(intent_route("font bigger than this?") is None, "font: 'font bigger than this?' matches no size route (left as it was)")
check(win_action("close this tab and open gmail") is None, "chain: 'close this tab and open gmail' matches no single window key")
r = intent_route("scale the image 150%")
check(not (r and r[0] == "set_appearance" and r[1].get("scale") == "150"), f"scale: 'scale the image 150%' -> {r} (not the display scale)")

print("all good" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
