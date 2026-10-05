"""The graphical programs installed on this computer (from their .desktop files), found by what people call them.

"open the browser", "a text editor", "file manager", "open firefox": the request names a kind of program or a
program; this finds the installed one that fits, so nobody has to know that the web browser is called Epiphany.
"""
import os
import re
import shlex

DIRS = ["/usr/share/applications", "/usr/local/share/applications", "/var/lib/flatpak/exports/share/applications"]
# what people say -> desktop categories / program names that answer it (first installed one wins)
KINDS = {
    "browser": (("web browser", "browser", "internet", "web", "firefox", "chrome", "chromium", "safari", "edge", "google"),
                ("org.gnome.Epiphany", "epiphany", "firefox", "firefox-esr", "chromium"), "WebBrowser"),
    "files": (("file manager", "files app", "file browser", "explorer", "finder", "thunar", "nautilus", "folders"),
              ("thunar", "org.gnome.Nautilus", "pcmanfm"), "FileManager"),
    "spreadsheet": (("spreadsheet", "spreadsheets", "excel", "calc", "gnumeric"), ("gnumeric", "org.gnumeric.gnumeric", "libreoffice-calc"), "Spreadsheet"),
    "wordprocessor": (("word processor", "word document", "word doc", "writer", "write a document", "document editor", "abiword"),
                      ("abiword", "com.abisource.abiword", "libreoffice-writer"), "WordProcessor"),
    "editor": (("text editor", "editor", "notepad++", "gedit", "notepad"), ("org.gnome.TextEditor", "mousepad", "org.xfce.mousepad", "gedit"), "TextEditor"),
    "terminal": (("terminal", "console", "command line", "shell", "cmd", "powershell"), ("foot", "xfce4-terminal"), "TerminalEmulator"),
    "images": (("image viewer", "photo viewer", "photos", "pictures", "picture viewer", "gallery"), ("org.gnome.Loupe", "imv", "ristretto", "eog"), "Viewer"),
    "documents": (("pdf viewer", "pdf reader", "document viewer", "pdf"), ("org.gnome.Papers", "org.gnome.Evince", "evince", "zathura"), ""),
    "presentation": (("presentation", "slides", "slideshow", "powerpoint", "impress"), ("libreoffice-impress",), ""),
    "office": (("office", "libreoffice", "office suite"), ("libreoffice-startcenter", "libreoffice-writer"), ""),
    "music": (("music player", "media player", "video player", "player", "vlc"), ("mpv", "vlc"), "AudioVideo"),
}


def _parse(path):
    d, in_entry = {}, False
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for ln in f:
                ln = ln.strip()
                if ln.startswith("["):
                    in_entry = ln == "[Desktop Entry]"
                    continue
                if in_entry and "=" in ln:
                    k, _, v = ln.partition("=")
                    d.setdefault(k.strip(), v.strip())
    except OSError:
        return None
    if d.get("Type") != "Application" or d.get("NoDisplay", "").lower() == "true" or d.get("Hidden", "").lower() == "true" or not d.get("Exec"):
        return None
    return {"id": os.path.basename(path)[:-8], "name": d.get("Name", ""), "generic": d.get("GenericName", ""),
            "exec": re.sub(r"\s*%[fFuUdDnNickvm]", "", d["Exec"]).strip(), "icon": d.get("Icon", ""),
            "categories": [c for c in d.get("Categories", "").split(";") if c], "keywords": d.get("Keywords", ""),
            "terminal": d.get("Terminal", "").lower() == "true"}


def installed():
    out, seen = [], set()
    for base in DIRS:
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for n in names:
            if n.endswith(".desktop") and n not in seen:
                seen.add(n)
                p = _parse(os.path.join(base, n))
                if p:
                    out.append(p)
    return sorted(out, key=lambda p: p["name"].lower())


def find(words):
    """The installed program the words mean, or None."""
    w = " " + re.sub(r"[^a-z0-9+ ]+", " ", str(words).lower()) + " "
    w = re.sub(r"\b(the|a|an|my|app|application|program|please|open|launch|start|run)\b", " ", w)
    progs = installed()
    by_id = {p["id"].lower(): p for p in progs}
    for kind, (says, prefer, cat) in KINDS.items():
        if any(f" {s} " in " " + " ".join(w.split()) + " " for s in says):
            for pid in prefer:
                if pid.lower() in by_id:
                    return by_id[pid.lower()]
            for p in progs:
                if cat and cat in p["categories"]:
                    return p
    t = " ".join(w.split())
    if not t:
        return None
    for p in progs:
        if t in (p["name"].lower(), p["id"].lower(), p["exec"].split()[0].lower(), os.path.basename(p["exec"].split()[0]).lower()):
            return p
    for p in progs:      # a whole word of the program's own name ("open mousepad", "ristretto")
        if t in p["name"].lower().split() or t == p["generic"].lower():
            return p
    return None


LABELS = {"browser": "the web browser", "files": "Files", "editor": "the text editor", "terminal": "the terminal",
          "images": "the image viewer", "documents": "the document viewer", "office": "the office program", "music": "the media player"}
EXTRA = {"abiword": "the word processor (AbiWord)", "gnumeric": "the spreadsheet (Gnumeric)", "org.gnumeric.gnumeric": "the spreadsheet (Gnumeric)",
         "com.abisource.abiword": "the word processor (AbiWord)", "xarchiver": "the archive manager",
         "pavucontrol": "the sound mixer", "org.xfce.mousepad": "the text editor", "mousepad": "the text editor", "foot": "the terminal",
         "thunar": "Files", "org.xfce.ristretto": "the image viewer", "ristretto": "the image viewer", "firefox": "Firefox"}


HIDE = re.compile(r"^(?:about xfce|bulk rename|envy24|foot (?:client|server)|thunar preferences|xfce|mousepad preferences|"
                  r"avahi|bluetooth adapters|bluetooth manager|print settings|qt\d? |cups|htop|vim|nano|ristretto preferences|"
                  r"xdg-desktop-portal|gnome|java|lstopo|hardware locality|hdajackretask|hdspconf|hdspmixer|envy24|rme|echomixer|"
                  r"qasmixer|alsa|foot server|mpv media player$|open url|desktop file|network connections)", re.I)
SHORT = {"firefox": "Firefox", "thunar": "Files", "org.xfce.mousepad": "Text editor", "mousepad": "Text editor", "foot": "Terminal",
         "org.xfce.ristretto": "Image viewer", "ristretto": "Image viewer", "abiword": "AbiWord (documents)",
         "gnumeric": "Gnumeric (spreadsheets)", "org.gnumeric.gnumeric": "Gnumeric (spreadsheets)", "xarchiver": "Archive manager", "pavucontrol": "Sound mixer", "mpv": "Video player"}


def everyday():
    """The programs worth showing a person: [(button label, program)], no settings helpers or duplicates."""
    out, seen = [], set()
    for p in installed():
        if not p["name"].strip() or HIDE.match(p["name"]) or p.get("terminal") or "Settings" in p["categories"] and p["id"].lower() != "pavucontrol":
            continue
        lab = SHORT.get(p["id"].lower()) or p["name"]
        if lab.lower() in seen:
            continue
        seen.add(lab.lower())
        out.append((lab, p))
    return sorted(out, key=lambda x: x[0].lower())


def label(p):
    """What to call a program to a person: 'the terminal', not 'Foot'."""
    pid = p["id"].lower()
    if pid in EXTRA:
        return EXTRA[pid]
    for kind, (says, prefer, cat) in KINDS.items():
        if pid in [x.lower() for x in prefer]:
            return LABELS.get(kind, p["name"])
    return p["name"]


def refresh():
    """(Programs are read fresh each time; kept so callers can say so after installing one.)"""
    return len(installed())


def argv(p, arg=None):
    a = shlex.split(p["exec"])
    if arg:
        a.append(arg)
    return a
