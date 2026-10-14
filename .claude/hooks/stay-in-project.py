#!/usr/bin/env python3
"""PreToolUse hook: tools in this project may not reach the owner's personal folders.

Everything LLM OS needs is under the project folder. Blocks Bash commands and file tools that name the home
folder (other than ~/.claude), other volumes, or personal places (Downloads, Desktop, Music, iCloud Drive ...).
"""
import json, re, sys

PROJECT = "/Volumes/Files/Claude Work Area/LLMOS"
try:
    inp = json.load(sys.stdin)
except Exception:
    sys.exit(0)
tool, args = inp.get("tool_name", ""), inp.get("tool_input") or {}
if tool == "Bash":
    text = args.get("command", "")
elif tool in ("Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit"):
    text = " ".join(str(args.get(k, "")) for k in ("file_path", "path", "notebook_path"))
else:
    sys.exit(0)

# the owner's one standing exception (2026-10-13): a finished release zip may be copied into their Downloads folder
if tool == "Bash" and re.fullmatch(r"cp \"/Volumes/Files/Claude Work Area/LLMOS/packages/LLM OS [0-9.]+\.zip\" "
                                   r"\"?/Users/[^/\s\"']+/Downloads/\"?", text.strip()):
    sys.exit(0)

# a real Mac home path: "/Users/<name>", or "~" / "$HOME" used as a path (at a word start, then "/" or the end of the
# word). A "~" inside code or a regex ("(?:~|/)", "~/Documents" in the OS's own source passed to python) is not a path
# the command opens, so it is not judged here (that blocked ordinary source edits).
home = r"(?:/Users/[^/\s\"']+|(?<![\w(|\\\"'])~(?=/|\s|$)|\$HOME|\$\{HOME\})"
bad = [
    home + r"(?:/(?!\.claude(?:/|\b))[^\s\"']*)?(?=[\s\"';)&]|$)",       # the home folder or anything in it except ~/.claude
    r"/Volumes/(?!Files/Claude Work Area/LLMOS)",                         # other drives / folders on this SSD
    r"Library/(?:Mobile Documents|CloudStorage)|/Users/[^/\s\"']+/(?:Music|Pictures|Movies|Downloads|Desktop|Documents)\b",
    r"\bmdfind\b|\bfind\s+/(?:\s|$)|\bfind\s+/Users\b",
]
# a heredoc's body (python fed on stdin, a file written with cat <<EOF) is data or code, not a path the shell opens
text = re.sub(r"<<-?\s*'?(\w+)'?\n.*?\n\1(?=\n|$)", "", text, flags=re.S)
# paths inside the guest image ("/root/Downloads", "~/Downloads" in OS source or VM commands) are not the Mac's:
# only judge text outside quoted strings that are clearly guest/test data would be guesswork, so judge Mac-side paths only
scan = re.sub(r"/root/[^\s\"']*", "", text)
scan = re.sub(r"(tsh|vmctl\.py|desk-ctl|llmos)\s[^\n]*", "", scan)        # commands sent into the VM
for pat in bad:
    m = re.search(pat, scan)
    if m:
        print(f"Blocked: '{m.group(0)}' is outside the LLM OS project folder. Everything this project needs is under "
              f"{PROJECT}. Use paths there (scratch: Support files/run/). Host tests: Support files/tools/run-host-tests.sh.",
              file=sys.stderr)
        sys.exit(2)
sys.exit(0)
