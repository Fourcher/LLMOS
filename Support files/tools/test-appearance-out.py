#!/usr/bin/env python3
"""A restyle of the desk is written out for GTK, labwc and Firefox from the same tokens.

"make everything purple" with square corners puts that background and border-radius: 0 into
gtk.css and userChrome.css. "no corners" is still the desk's rounded radius, and that radius
is written too. Settings-in-Chinese is unchanged. Nothing is fetched. No WebKit session.
Run: python3 tools/test-appearance-out.py
"""
import os
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ["LLMOS_HOME"] = home
os.environ["LLMOS_ETC"] = os.path.join(home, "etc")
os.environ["LLMOS_SHARE"] = os.path.join(_ROOT, "usr/share/llmos")
os.environ["XDG_CONFIG_HOME"] = os.path.join(home, ".config")
from llmos import desk, i18n, intent, themes, tools  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


class Ctx:
    def redraw(self):
        return None

    def background(self, fn):
        return None

    def reload_apps(self):
        return None


# a profile Firefox already had, plus the one the OS creates
other = os.path.join(home, ".mozilla", "firefox", "other.default")
os.makedirs(other, exist_ok=True)
ini = os.path.join(home, ".mozilla", "firefox", "profiles.ini")
os.makedirs(os.path.dirname(ini), exist_ok=True)
with open(ini, "w", encoding="utf-8") as f:
    f.write("[Profile0]\nName=other\nIsRelative=1\nPath=other.default\nDefault=1\n")
# a compositor config whose corner radius should follow the desk
rc = os.path.join(home, ".config", "labwc", "rc.xml")
os.makedirs(os.path.dirname(rc), exist_ok=True)
with open(rc, "w", encoding="utf-8") as f:
    f.write("<labwc_config><theme><cornerRadius>10</cornerRadius></theme></labwc_config>\n")

ctx = Ctx()
reply = tools.set_appearance({"theme": "purple", "corners": "square"}, ctx)
pay = desk.Desk.theme_payload(None)
css = pay["css"]
bg, radius = css.get("--bg", ""), css.get("--radius", "")
check(reply.startswith("appearance updated"), f"purple and square applied ({reply})")
check(bg.startswith("#") and radius == "0px", f"desk tokens are a colour and square corners ({bg}, {radius})")

paths = themes.appearance_paths(home)
gtk = open(paths["gtk"], encoding="utf-8").read()
gtk4 = open(paths["gtk4"], encoding="utf-8").read()
chrome = open(paths["chrome"], encoding="utf-8").read()
content = open(paths["content"], encoding="utf-8").read()
themerc = open(paths["labwc"], encoding="utf-8").read()
other_chrome = open(os.path.join(other, "chrome", "userChrome.css"), encoding="utf-8").read()


def follows(text, what):
    check(bg in text and "border-radius: 0" in text, f"{what} has the desk background and border-radius: 0")
    check("http://" not in text and "https://" not in text and "@import" not in text, f"{what} fetches nothing")


follows(gtk, "gtk-3.0/gtk.css")
follows(gtk4, "gtk-4.0/gtk.css")
follows(chrome, "userChrome.css")
follows(content, "userContent.css")
follows(other_chrome, "an existing Firefox profile")
check(bg in themerc and "window.button.hover.bg.corner-radius: 0" in themerc, "labwc themerc has the background and square corners")
check("<cornerRadius>0</cornerRadius>" in open(rc, encoding="utf-8").read(), "labwc rc.xml corner radius is 0")
check("toolkit.legacyUserProfileCustomizations.stylesheets" in open(os.path.join(home, ".mozilla", "firefox", "llmos", "user.js"), encoding="utf-8").read(),
      "Firefox is told to load userChrome")

hit = intent.match("no corners")
check(hit == ("set_appearance", {"corners": "rounded"}), f"'no corners' is still the rounded corner ({hit})")
tools.set_appearance(hit[1], ctx)
pay = desk.Desk.theme_payload(None)
rounded = pay["css"].get("--radius", "")
check(rounded not in ("", "0", "0px"), f"the desk's rounded radius is {rounded}")
gtk = open(paths["gtk"], encoding="utf-8").read()
chrome = open(paths["chrome"], encoding="utf-8").read()
content = open(paths["content"], encoding="utf-8").read()
themerc = open(paths["labwc"], encoding="utf-8").read()
for text, what in ((gtk, "gtk.css"), (chrome, "userChrome.css"), (content, "userContent.css")):
    check(rounded in text and bg in text, f"'no corners' writes the desk radius {rounded} into {what}")
check(f"window.button.hover.bg.corner-radius: {int(rounded[:-2])}" in themerc, "labwc radius matches the desk")
check(f"<cornerRadius>{int(rounded[:-2])}</cornerRadius>" in open(rc, encoding="utf-8").read(),
      "labwc rc.xml radius matches the desk")

tools.set_appearance({"language": "English", "settings_language": "Chinese"}, ctx)
check(i18n.t("s_language", area="settings") == "语言" and i18n.t("s_language") == "Language",
      "settings stay in Chinese and the rest stays in English")

print(f"\n{'all good' if not fails else str(fails) + ' failure(s)'}")
sys.exit(1 if fails else 0)
