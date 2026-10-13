#!/usr/bin/env python3
"""Host-side test of install_to_disk's owner-facing failure text: the installer call is patched to raise each
known failure, and the show() calls are captured. No disk is touched. Run: python3 tools/test-install-errors.py"""
import os
import subprocess
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))
from llmos import tools, installer  # noqa: E402

FORBIDDEN = ("boom", "Errno", "/dev/", "Traceback")
TITLE_CANNOT = "Can't install on this disk"
TITLE_FAILED = "The install didn't finish"


class Ctx:
    """Captures what the owner would see; the installer call is replaced, so no ctx.status is needed."""
    def __init__(self):
        self.shown = []
        self.status = lambda s: None

    def show_ui(self, spec):
        self.shown.append(spec)


def bodies(spec):
    out = []
    for blk in spec.get("blocks", []):
        if blk.get("type") == "text":
            out.append(blk.get("text", ""))
    return out


def run_case(label, patch_name, exc, args, expect_title, failures):
    real = getattr(installer, patch_name)

    def boom(*_a, **_k):
        raise exc
    setattr(installer, patch_name, boom)
    ctx = Ctx()
    try:
        ret = tools.install_to_disk(args, ctx)
    except Exception as e:  # a non-installer exception is not caught by the tool: that is reported, not hidden
        ret = None
        caught = e
    else:
        caught = None
    finally:
        setattr(installer, patch_name, real)
    if caught is not None:
        if expect_title is None:
            print(f"ok {label}: not caught by the tool (propagates as before)")
            return
        failures.append(f"{label}: unexpected exception {caught!r}")
        return
    if len(ctx.shown) != 1:
        failures.append(f"{label}: expected one show(), got {len(ctx.shown)}")
        return
    spec = ctx.shown[0]
    if spec.get("title") != expect_title:
        failures.append(f"{label}: title {spec.get('title')!r} != {expect_title!r}")
    texts = bodies(spec)
    joined = " | ".join(texts) + " | " + str(ret)
    for bad in FORBIDDEN:
        if bad in " | ".join(texts):
            failures.append(f"{label}: body contains {bad!r}: {texts!r}")
    if not texts or not all(t.strip() for t in texts):
        failures.append(f"{label}: empty body")
    if "Reply: " not in str(ret) or not str(ret).split("Reply: ", 1)[1].strip():
        failures.append(f"{label}: model return has no 'Reply: <sentence>': {str(ret)!r}")
    print(f"ok {label}: {spec.get('title')!r} -> {texts[0]!r}")


def main():
    failures = []
    I = installer.InstallError
    plan_cases = [
        ("no such disk", I("no such disk: /dev/sdz")),
        ("no other disk", I("no other disk found to install onto (the running system's own disk is never a target)")),
        ("no GPT", I("/dev/sda has no GPT partition table; installing next to another system needs GPT (say 'erase the whole disk and install')")),
        ("no free space", I("no free space on /dev/sda; shrink the other system's partition first (macOS: Disk Utility)")),
        ("too small", I("the free space on /dev/sda is 3.2 GB; at least 12 GB is needed")),
        ("OSError", OSError(2, "No such file or directory", "/dev/sda1")),
    ]
    for label, exc in plan_cases:
        run_case(f"plan {label}", "plan", exc, {"mode": "alongside"},
                 TITLE_CANNOT, failures)
    # generic Exception is not an installer failure: the tool does not catch it, so it is not shown as a body
    run_case("plan generic (not caught)", "plan", Exception("boom: /dev/sda1 busy"), {"mode": "whole"},
             None, failures)

    run_cases = [
        ("run InstallError", I("sfdisk failed: boom: /dev/sda1 busy")),
        ("run OSError", OSError(16, "Device or resource busy", "/dev/sda1")),
        ("run timeout", subprocess.TimeoutExpired("mkfs.ext4", 3600)),
    ]
    for label, exc in run_cases:
        run_case(f"{label}", "run", exc, {"token": "abc123"}, TITLE_FAILED, failures)

    # the owner-facing text of the known reasons is a plain sentence, not the raw installer text
    text = tools._install_reason(I("no free space on /dev/sda; shrink"), installer.MIN_ROOT_GB)
    if "/dev/" in text or "free space" not in text:
        failures.append(f"reason sentence unexpected: {text!r}")

    if failures:
        for f in failures:
            print("FAIL", f)
        sys.exit(1)
    print("all good")


if __name__ == "__main__":
    main()
