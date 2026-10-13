#!/usr/bin/env python3
"""Tests for system.find_timezone: accented and ß place names resolve; ASCII queries keep their old answers.

Runs the real find_timezone against the real zone list (ZONEINFO = /usr/share/zoneinfo, walked at call time).
Read-only: it does not touch the system zone.
Run: python3 tools/test-find-timezone.py"""
import os
import sys

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
from llmos import system  # noqa: E402

fails = []


def check(label, got, want):
    if got == want:
        print("ok %s -> %r" % (label, got))
    else:
        print("FAIL %s: got %r want %r" % (label, got, want))
        fails.append(label)


# ASCII queries: answers unchanged from before the NFKD change.
ascii_cases = [
    ("tokyo", "Asia/Tokyo"),
    ("new york", "America/New_York"),
    ("london", "Europe/London"),
    ("los angeles", "America/Los_Angeles"),
    ("paris", "Europe/Paris"),
    ("sydney", "Australia/Sydney"),
    ("berlin", "Europe/Berlin"),
    ("utc", None),
    ("America/New_York", "America/New_York"),
    ("est", "America/Creston"),
]
for q, want in ascii_cases:
    check("ascii %r" % q, system.find_timezone(q), want)

# Accented and ß names now resolve.
accent_cases = [
    ("zürich", "Europe/Zurich"),
    ("Zürich", "Europe/Zurich"),
    ("são paulo", "America/Sao_Paulo"),
    ("méxico", "America/Mexico_City"),
    ("straße", None),
]
for q, want in accent_cases:
    check("accent %r" % q, system.find_timezone(q), want)

# Normalisation keys (no zone or alias exists for Kraków, so it is checked by key only).
key_cases = [("kraków", "krakow"), ("Kraków", "krakow"), ("são paulo", "saopaulo"), ("straße", "strasse"), ("zürich", "zurich")]
for q, want in key_cases:
    check("key %r" % q, system._zone_key(q), want)

# Adversarial inputs: no crash; the empty and emoji cases return None as before.
check("empty", system.find_timezone(""), None)
check("emoji only", system.find_timezone("\U0001F600\U0001F30D"), None)
check("cjk 東京", system.find_timezone("東京"), None)
try:
    r = system.find_timezone("x" * 5000)
    check("5000 chars no crash", r, None)
except Exception as e:
    check("5000 chars no crash (raised %s)" % type(e).__name__, "raised", "returned")

if fails:
    print("FAILED: %d" % len(fails))
    sys.exit(1)
print("all good")
