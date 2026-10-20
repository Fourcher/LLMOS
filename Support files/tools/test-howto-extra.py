#!/usr/bin/env python3
"""Host-side test of the answers-at-once phrases for accounts, dual boot and the update shortcut (desk.py _HOWTO
and _system_shortcut). desk.py needs GTK, so the table and the update pattern are read from its source with ast and
compiled. Matching is the desk's own: the first _HOWTO entry whose pattern fullmatches the normalised text wins.
Run: python3 tools/test-howto-extra.py"""
import ast
import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs/usr/lib/llmos/llmos/desk.py")
tree = ast.parse(open(SRC, encoding="utf-8").read())
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        fails += 1


# the _HOWTO table: a list of (pattern, reply) tuples of plain string constants
howto = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_HOWTO" for t in node.targets):
        howto = [(re.compile(rx), text) for rx, text in ast.literal_eval(node.value)]
assert howto, "_HOWTO not found in desk.py"

ACCOUNT = next(t for rx, t in howto if t.startswith("LLM OS has one account"))
DUAL = next(t for rx, t in howto if t.startswith("Yes: say"))


def answer(q):
    """The desk's _howto: first entry whose pattern fullmatches the normalised text."""
    for rx, text in howto:
        if rx.fullmatch(q):
            return text
    return None


# the update shortcut: the one string constant that holds the install-updates / update-system pattern
# (the install-updates words are desk._UPD_INSTALL now, one pattern for every everyday phrasing)
_src = open(SRC, encoding="utf-8").read() if "SRC" in globals() else ast.unparse(tree)
_ns = {}
exec("import re\n" + _src[_src.index("_UPD_AUTO = "):_src.index("_TIME_Q = re.compile(")], _ns)
UPDATE = _ns["_UPD_INSTALL"]
assert UPDATE, "update pattern not found in desk.py"

print("account phrases (new)")
for q in ("second user", "second account", "second login", "second profile", "another user", "another account",
          "another login", "my wife needs her own login", "kid needs his own account", "kid needs his own user",
          "my son needs a login", "my daughter needs an account", "my partner needs a login",
          "can two people use this computer"):
    check(answer(q) == ACCOUNT, f"account: {q!r}")

print("dual-boot phrases (new)")
for q in ("install alongside windows", "install next to windows", "keep windows and install llm os",
          "keep windows and install this", "install without erasing windows", "install llm os without deleting windows",
          "install this without removing windows"):
    check(answer(q) == DUAL, f"dual boot: {q!r}")

print("update phrases (new and old)")
for q in ("upgrade everything", "upgrade the system", "upgrade my apps", "upgrade all my programs", "upgrade the computer now",
          "update the system", "update everything", "update my apps", "install updates"):
    check(bool(UPDATE.fullmatch(q)), f"update: {q!r}")

print("old phrases still answered by the same entry")
for q in ("add a user", "make an account for my son", "create a login", "can my wife have her own account", "switch users",
          "guest mode", "can i dual boot", "can i dual-boot with windows", "dual boot with windows",
          "can i keep windows", "can i install it next to windows"):
    got = answer(q)
    if q in ("add a user", "make an account for my son", "create a login", "can my wife have her own account",
             "switch users", "guest mode"):
        check(got == ACCOUNT, f"old account: {q!r}")
    else:
        check(got == DUAL, f"old dual boot: {q!r}")
check(bool(UPDATE.fullmatch("update the system now")), "old update: 'update the system now'")

print("adversarial inputs (must not match)")
for q in ("my wife needs her own coffee", "install windows", "remove windows", "second hand laptop prices", "another user said hi"):
    got = answer(q)
    check(got not in (ACCOUNT, DUAL), f"not account or dual boot: {q!r}")
for q in ("update my resume", "upgrade my plan"):
    check(not UPDATE.fullmatch(q), f"not update shortcut: {q!r}")

print("ok" if not fails else f"{fails} failed")
print("all good" if not fails else "FAILED")
sys.exit(1 if fails else 0)
