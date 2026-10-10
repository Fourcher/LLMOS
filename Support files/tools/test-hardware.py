#!/usr/bin/env python3
"""Host-side unit test for hardware.plugged_in: what is plugged in, read from a fake /sys and /proc tree.
Also checks the desk regex that answers "what's plugged into my computer".
Run: python3 tools/test-hardware.py  (no VM needed). Exit status 0 = pass."""
import os
import re
import sys
import tempfile

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))

from llmos import hardware


def put(root, rel, text=""):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


fake = tempfile.mkdtemp()
put(fake, "sys/bus/usb/devices/1-1/product", "USB Keyboard\n")
put(fake, "sys/bus/usb/devices/1-1/manufacturer", "Logitech\n")
os.makedirs(os.path.join(fake, "sys/bus/usb/devices/1-1:1.0"))
put(fake, "sys/bus/usb/devices/usb1/product", "xHCI Host Controller\n")
put(fake, "sys/bus/usb/devices/1-2/product", "Hub\n")
put(fake, "dev/video0", "")
put(fake, "sys/block/sda/removable", "1\n")
put(fake, "sys/block/sda/device/model", "SanDisk\n")
put(fake, "proc/asound/cards",
    " 0 [Generic        ]: HDA-Intel - HD-Audio Generic\n"
    "                      HD-Audio Generic at 0xf7e10000 irq 32\n")

got = hardware.plugged_in(fake)
want = ["USB Keyboard (Logitech)", "a camera", "a removable drive (SanDisk)", "sound: HDA-Intel"]
assert got == want, f"plugged_in mismatch: {got!r}"
print("ok plugged_in:", got)

empty = tempfile.mkdtemp()
sent = hardware.plugged_in_sentence(empty)
assert sent == "Nothing extra is plugged in.", sent
print("ok empty sentence:", sent)

# The same regex as desk.py shortcut(), applied to the lowercased, stripped line.
DESK = (r"what(?:'s| is| are| devices are)? (?:plugged|connected) (?:in|into|to) (?:my |the |this )?(?:computer|pc|laptop|machine)"
        r"|what(?:'s| is) plugged in|(?:list|show)(?: me)? (?:my |the )?(?:usb |connected |plugged[- ]in )?devices")


def desk_match(text):
    low = text.lower().strip()
    return re.fullmatch(DESK, low.rstrip("?.! ")) is not None


for s in ["what's plugged into my computer", "what is connected to my pc", "what's plugged in", "show my usb devices"]:
    assert desk_match(s), s
    print("ok desk matches:", s)
assert not desk_match("what's plugged into the wall socket")
print("ok desk does not match: what's plugged into the wall socket")
print("all good")
