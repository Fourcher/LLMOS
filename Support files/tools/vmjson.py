"""Parse the JSON object out of VM command output (tsh output). Stdlib only."""
import json
import re


def vm_json(text):
    """The JSON object (a dict) in VM command output, or None. tsh output carries more than the
    reply (the echoed command, prompt lines, the "[vmctl: ...]" trailer), so: the whole text if it is
    one object; else the last line that is one object; else the span from the first "{" to the last "}".
    Output with no object (e.g. "[vmctl: TIMEOUT after 30.4s]") gives None."""
    if not isinstance(text, str):
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    for line in reversed([ln.strip() for ln in text.splitlines()]):
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        try:
            obj = json.loads(text[first:last + 1])
        except ValueError:
            return None
        if isinstance(obj, dict):
            return obj
    return None


_TRAILER = re.compile(r"^\[vmctl: (matched|TIMEOUT) after [\d.]+s\]$")
# the echoed command typed into the console: a prompt "llmos:<cwd># " followed by text (or a bare prompt)
_ECHO = re.compile(r"^llmos:\S*#(\s|$)")


def vm_text(out):
    """The text of VM command output with the echoed command lines (a line starting "llmos:<cwd># "), the
    "[vmctl: matched after N.Ns]" and "[vmctl: TIMEOUT after N.Ns]" trailer lines removed and trailing
    whitespace stripped. Output with a TIMEOUT trailer gives None (no output); a non-string gives None."""
    if not isinstance(out, str):
        return None
    kept = []
    timed_out = False
    for line in out.splitlines():
        m = _TRAILER.match(line.strip())
        if m:
            if m.group(1) == "TIMEOUT":
                timed_out = True
            continue
        if _ECHO.match(line.strip()):
            continue
        kept.append(line)
    if timed_out:
        return None
    return "\n".join(kept).rstrip()
