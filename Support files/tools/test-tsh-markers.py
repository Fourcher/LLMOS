#!/usr/bin/env python3
"""tsh output cutting: runs tools/tsh against a fake vmctl that prints canned
console logs (a console-wrapped echo of the typed command, then the BEGIN/DONE
markers). No VM is touched."""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TSH = os.path.join(HERE, "tsh")

FAKE = r'''
import os, re, sys
d = os.environ["FAKE_DIR"]
mode = os.environ["FAKE_MODE"]
text = sys.argv[4]
n = re.search(r'BEGIN_""(\d+)', text).group(1)
calls_path = os.path.join(d, "calls")
calls = int(open(calls_path).read()) if os.path.exists(calls_path) else 0
calls += 1
open(calls_path, "w").write(str(calls))
open(os.path.join(d, "texts"), "a").write(text + "\n")
# the console wraps the typed echo at 64 columns
wrapped = ["llmos:/# " + text[:55]] + [text[i:i + 64] for i in range(55, len(text), 64)]
out = "\n".join(wrapped) + "\n"
if mode == "dark":
    out += "BEGIN_%s\ndark\nDONE_%s\n" % (n, n)
elif mode == "empty":
    out += "BEGIN_%s\nDONE_%s\n" % (n, n)
elif mode == "retry":
    if calls == 1:
        out += "BEGIN_%s\n/bin/sh: !llmos: not found\nDONE_%s\n" % (n, n)
    else:
        out += "BEGIN_%s\nok\nDONE_%s\n" % (n, n)
sys.stdout.write(out + "\n[vmctl: matched after 0.1s]\n")
'''


def run_tsh(mode, cmd):
    tmp = tempfile.mkdtemp(prefix="tsh-test-")
    try:
        fake = os.path.join(tmp, "vmctl.py")
        with open(fake, "w") as f:
            f.write(FAKE)
        env = dict(os.environ, VMCTL=fake, FAKE_DIR=tmp, FAKE_MODE=mode)
        r = subprocess.run(["bash", TSH, cmd], env=env, capture_output=True, text=True, timeout=60)
        texts = []
        tp = os.path.join(tmp, "texts")
        if os.path.exists(tp):
            texts = open(tp).read().splitlines()
        return r.returncode, r.stdout, r.stderr, texts
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


TRAILER = "[vmctl: matched after 0.1s]\n"
failures = []


def check(name, cond, detail=""):
    if cond:
        print("ok", name)
    else:
        print("FAIL", name, detail)
        failures.append(name)


CMD = "echo dark light; python3 -c \"print('dark')\""

# 1. wrapped echo of the typed command must not leak into the output
rc, out, err, texts = run_tsh("dark", CMD)
check("wrapped echo cut: only 'dark' + trailer", out == "dark\n" + TRAILER and rc == 0,
      repr(out) + " rc=%s err=%s" % (rc, err))
check("wrapped echo really spans several lines", len(texts) == 1 and len(texts[0]) > 64, repr(texts))

# 2. '!llmos: not found' -> one re-send without '!', its output is printed
rc, out, err, texts = run_tsh("retry", CMD)
check("'!' not-found retried once: prints 'ok' + trailer", out == "ok\n" + TRAILER and rc == 0,
      repr(out) + " rc=%s err=%s" % (rc, err))
check("retry sent exactly twice, second without '!'",
      len(texts) == 2 and texts[1].startswith("echo BEGIN_"), repr(texts))

# 3. empty output -> empty output, trailer only
rc, out, err, texts = run_tsh("empty", "true")
check("empty output stays empty", out == TRAILER and rc == 0, repr(out) + " err=" + err)

if failures:
    print("FAILED:", ", ".join(failures))
    sys.exit(1)
print("all good")
