#!/usr/bin/env python3
"""The shipped Firefox policy blocks autoplay and does not offer a new-tab site grid.

Search stays. Sponsored tiles, Pocket and telemetry stay off. An asked-for video still
goes through media.find's ytsearch. No browser is launched.
Run: python3 tools/test-firefox-policy.py
"""
import json
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


path = os.path.join(_ROOT, "usr/lib/firefox/distribution/policies.json")
pol = json.load(open(path, encoding="utf-8"))["policies"]
home = pol["FirefoxHome"]
prefs = pol["Preferences"]
auto = prefs["media.autoplay.default"]
check(auto["Value"] == 1, f"media.autoplay.default is 1 (block audio and video), got {auto['Value']}")
check(home["TopSites"] is False, "FirefoxHome.TopSites is off")
check(home["Search"] is True, "FirefoxHome.Search stays on")
check(home["SponsoredTopSites"] is False and home["SponsoredPocket"] is False, "sponsored tiles and sponsored Pocket stay off")
check(home["Pocket"] is False and pol["DisablePocket"] is True, "Pocket stays off")
check(pol["DisableTelemetry"] is True and pol["DisableFirefoxStudies"] is True, "telemetry and studies stay off")
check(prefs["browser.newtabpage.activity-stream.showSponsored"]["Value"] is False, "sponsored new-tab stories stay off")
check(prefs["browser.newtabpage.activity-stream.showSponsoredTopSites"]["Value"] is False, "sponsored top sites pref stays off")
check(prefs["browser.newtabpage.activity-stream.feeds.topsites"]["Value"] is False, "the top-sites feed stays off")
check(prefs["toolkit.legacyUserProfileCustomizations.stylesheets"]["Value"] is True,
      "userChrome is allowed to load, so a restyle can reach Firefox")

media = open(os.path.join(_ROOT, "usr/lib/llmos/llmos/media.py"), encoding="utf-8").read()
tools = open(os.path.join(_ROOT, "usr/lib/llmos/llmos/tools.py"), encoding="utf-8").read()
check('f"ytsearch' in media and "def find(" in media, "media.find still searches with ytsearch")
check("def play_media(" in tools, "play_media is still the tool an asked-for video uses")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
