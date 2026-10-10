#!/usr/bin/env python3
"""'click X' with nothing open names X: 'Nothing is open to click X in.' Empty X keeps the old sentence."""
import ast
import os
import py_compile
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "desk.py")

CASES = [
    ("click File", "Nothing is open to click File in."),
    ("click on File", "Nothing is open to click File in."),
    ("click the File menu", "Nothing is open to click File menu in."),
    ("CLICK OK", "Nothing is open to click OK in."),
    ("click", "Nothing is open to click on."),
    ("click the", "Nothing is open to click on."),
    ("please tap Save button.", "Nothing is open to click Save button in."),
]


def load_helper(tree):
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_nothing_open_reply")
    mod = ast.Module(body=[fn], type_ignores=[])
    ns = {"re": re}
    exec(compile(mod, DESK, "exec"), ns)
    return ns["_nothing_open_reply"]


def calls_helper_in_shortcut(tree):
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Desk"):
        for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "shortcut"):
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "_nothing_open_reply"):
                    return True
    return False


def main():
    failures = []
    with open(DESK, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src, DESK)

    try:
        reply = load_helper(tree)
    except StopIteration:
        print("FAIL _nothing_open_reply not defined in desk.py")
        return 1

    for text, want in CASES:
        got = reply(text)
        if got == want:
            print(f"ok {text!r} -> {got!r}")
        else:
            failures.append(f"{text!r}: got {got!r}, want {want!r}")

    if calls_helper_in_shortcut(tree):
        print("ok Desk.shortcut calls _nothing_open_reply")
    else:
        failures.append("Desk.shortcut does not call _nothing_open_reply")

    try:
        py_compile.compile(DESK, doraise=True)
        print("ok desk.py compiles")
    except py_compile.PyCompileError as exc:
        failures.append(f"desk.py does not compile: {exc}")

    if failures:
        for f in failures:
            print("FAIL", f)
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
