#!/usr/bin/env python3
"""Host-side test of the scientific calculator ready-made app (usr/share/llmos/apps/calculator-scientific.html):
its header parses and 'scientific calculator' finds it while 'a calculator' still finds the plain calculator;
the file uses no eval or Function constructor; the expression parser gives the right answers (run under node
when node is installed).
Run: python3 tools/test-sci-calc.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
home = tempfile.mkdtemp(prefix="llmos-test-")
os.environ.update(LLMOS_HOME=home, LLMOS_ETC=os.path.join(home, "etc"), LLMOS_SHARE=os.path.join(_ROOT, "usr/share/llmos"))
from llmos import apps  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails += 1


APP = os.path.join(apps.SHARE, "calculator-scientific.html")
with open(APP, encoding="utf-8") as f:
    text = f.read()

# (1) header and matching
meta = apps._meta(text[:4000])
check(meta.get("id") == "calculator-scientific", "header id is calculator-scientific")
check(meta.get("title") == "Scientific calculator", "header title is Scientific calculator")
check(meta.get("size") == "m", "header size is m")
check("scientific-calculator" in meta.get("words", ""), "header words include 'scientific-calculator' (matches the 'scientific calculator' phrase)")
check(any(t["id"] == "calculator-scientific" for t in apps.templates()), "template is listed by apps.templates()")
t = apps.match_template("scientific calculator")
check(t is not None and t["id"] == "calculator-scientific", "match_template('scientific calculator') -> calculator-scientific")
t = apps.match_template("a calculator")
check(t is not None and t["id"] == "calculator", "match_template('a calculator') -> calculator")

# (2) no eval or Function constructor
check("eval(" not in text, "file contains no 'eval('")
check("Function(" not in text, "file contains no 'Function('")

# (3) parser under node
node = shutil.which("node")
if not node:
    print("skip js (no node)")
else:
    start, end = "// PARSER BEGIN", "// PARSER END"
    if start not in text or end not in text:
        check(False, "parser markers present")
    else:
        parser = text[text.index(start):text.index(end) + len(end)]
        cases = [
            ("2+3*4", True, "14"), ("2^3^2", True, "512"), ("-2^2", True, "-4"),
            ("sqrt(16)", True, "4"), ("sin(30)", True, "0.5"), ("log(1000)", True, "3"),
            ("ln(e)", True, "1"), ("2*pi", True, "6.28318530718"), ("(1+2)*3", True, "9"),
            ("1/0", True, "Infinity"), ("(1+2", True, "ERR"), ("foo", True, "ERR"),
            ("sqrt(-1)", True, "NaN"), ("2pi", True, "6.28318530718"), ("2(3)", True, "6"),
            ("sqrt 9", True, "3"), ("2×3÷4", True, "1.5"), ("√16", True, "4"),
            ("sin(pi/2)", False, "1"), ("1+", True, "ERR"), ("2 3", True, "6"),
        ]
        script = parser + "\nconst cases=" + json.dumps([[e, d] for e, d, _ in cases]) + ";\n" \
            "console.log(JSON.stringify(cases.map(([e,d])=>{try{return sciFormat(sciCalc(e,d))}catch(x){return 'ERR'}})));\n"
        r = subprocess.run([node], input=script, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            check(False, "node runs the parser: " + r.stderr.strip()[:300])
        else:
            got = json.loads(r.stdout.strip().splitlines()[-1])
            for (expr, d, want), g in zip(cases, got):
                check(g == want, f"{expr!r} ({'deg' if d else 'rad'}) = {want}" + ("" if g == want else f" (got {g!r})"))

print("all good" if not fails else f"{fails} failure(s)")
sys.exit(1 if fails else 0)
