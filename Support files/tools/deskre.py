"""Read a regex literal straight out of desk.py's source, so tests check the real pattern (desk.py needs GTK to import)."""
import os
import re

DESK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
_LIT = re.compile(r'r"((?:[^"\\\n]|\\.)*)"')


def pattern_containing(needle):
    """The r"..." literal holding `needle`, joined with the literals right before/after it that are separated only by
    whitespace (Python's implicit concatenation of r"a" r"b" across lines)."""
    src = open(DESK, encoding="utf-8").read()
    i = src.find(needle)
    if i < 0:
        raise AssertionError(f"{needle!r} not found in desk.py")
    lits = list(_LIT.finditer(src))
    k = next(n for n, m in enumerate(lits) if m.start() <= i < m.end())
    a = b = k
    while a > 0 and not src[lits[a - 1].end():lits[a].start()].strip():
        a -= 1
    while b + 1 < len(lits) and not src[lits[b].end():lits[b + 1].start()].strip():
        b += 1
    return "".join(m.group(1) for m in lits[a:b + 1])
