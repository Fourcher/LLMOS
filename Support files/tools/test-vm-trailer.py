#!/usr/bin/env python3
"""Tests for the vmctl trailer filters: vmjson.vm_text (Python) and tsh emit (shell, run via sh on a
fixture RAW; no VM is touched). Stdlib only."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from vmjson import vm_text  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print("ok %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILS.append(name)


# 1. vm_text on the real polluted sample (a trailer cut in two, plus a shell complaint about it)
POLLUTED = "d after 0.0s]/PiApps Documents …\n/bin/sh: [vmctl:: not found\n0"
got = vm_text(POLLUTED)
check("vm_text polluted sample -> clean text",
      got == "/PiApps Documents …\n0" and "after" not in got and "[vmctl" not in got, repr(got))

# 2. clean sample unchanged
CLEAN = "a.txt\nb.txt\n\n  indented\n"
check("vm_text clean sample unchanged (rstrip only)", vm_text(CLEAN) == "a.txt\nb.txt\n\n  indented",
      repr(vm_text(CLEAN)))
check("vm_text clean sample: interior blank line kept byte-identical",
      vm_text("x\n\ny\n") == "x\n\ny", repr(vm_text("x\n\ny\n")))

# 3. a legitimate line containing the word vmctl survives
check("vm_text 'ls vmctl.py' output kept", vm_text("vmctl.py\n") == "vmctl.py", repr(vm_text("vmctl.py\n")))
check("vm_text vmctl word in a path kept",
      vm_text("tools/vmctl.py\n[vmctl: matched after 0.4s]\n") == "tools/vmctl.py",
      repr(vm_text("tools/vmctl.py\n[vmctl: matched after 0.4s]\n")))

# 4. trailer glued mid-line, alone, and the shell complaint alone
check("vm_text trailer glued at line end removed",
      vm_text("PiApps Documents [vmctl: matched after 0.0s]\n") == "PiApps Documents",
      repr(vm_text("PiApps Documents [vmctl: matched after 0.0s]\n")))
check("vm_text trailer alone -> empty", vm_text("[vmctl: matched after 0.0s]\n") == "",
      repr(vm_text("[vmctl: matched after 0.0s]\n")))
check("vm_text shell complaint alone -> empty", vm_text("/bin/sh: [vmctl:: not found\n") == "",
      repr(vm_text("/bin/sh: [vmctl:: not found\n")))

# 5. empty output -> empty; non-string -> None; TIMEOUT anywhere -> None
check("vm_text empty output -> empty", vm_text("") == "", repr(vm_text("")))
check("vm_text non-string -> None", vm_text(None) is None)
check("vm_text TIMEOUT glued mid-line -> None",
      vm_text("partial [vmctl: TIMEOUT after 30.4s]\n") is None)

# 6. tsh emit: run its emit() via sh on a fixture RAW (function extracted from the file, not executed)
TSH = os.path.join(HERE, "tsh")
with open(TSH, encoding="utf-8") as f:
    tsh_src = f.read()
m = re.search(r"^emit\(\) \{\n.*?^\}\n", tsh_src, re.S | re.M)
check("tsh emit() found in file", m is not None)


def run_emit(raw, run_n):
    env = dict(os.environ, RAW=raw, RUN_N=run_n)
    script = m.group(0) + "\nemit\n"
    r = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout, r.stderr


if m:
    raw = ("BEGIN_123\n"
           "PiApps Documents [vmctl: matched after 0.0s]\n"
           "vmctl.py\n"
           "/bin/sh: [vmctl:: not found\n"
           "DONE_123\n"
           "[vmctl: matched after 0.2s]\n")
    rc, out, err = run_emit(raw, "123")
    check("tsh emit: glued and shell-complaint lines dropped, vmctl.py kept, trailer last",
          rc == 0 and out == "vmctl.py\n[vmctl: matched after 0.2s]\n", repr((rc, out, err)))

    raw2 = "BEGIN_5\nDONE_5\n"
    rc, out, err = run_emit(raw2, "5")
    check("tsh emit: empty output -> empty", rc == 0 and out == "", repr((rc, out, err)))

    raw3 = "BEGIN_7\nhello\nDONE_7\n"
    rc, out, err = run_emit(raw3, "7")
    check("tsh emit: normal output unchanged, no trailer", rc == 0 and out == "hello\n", repr((rc, out, err)))

# static check: the body filter uses fixed-string "[vmctl:"
check("tsh body filter uses grep -F \"[vmctl:\"", 'grep -av -F "[vmctl:"' in tsh_src)

# 7. syntax of tsh
r = subprocess.run(["sh", "-n", TSH], capture_output=True, text=True)
check("sh -n tsh", r.returncode == 0, r.stderr)

if FAILS:
    print("FAILED: %s" % ", ".join(FAILS))
    sys.exit(1)
print("all good")
