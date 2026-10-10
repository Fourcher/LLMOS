#!/usr/bin/env python3
"""Host-side unit test: model sampling is repeatable only in the test VM (fw_cfg opt/llmos/testshell).
With the test marker, chat() sends temperature 0 and seed 42; otherwise the owner's temperature (0.3) and no seed.
Run: python3 tools/test-sampling.py  (no VM needed). Exit status 0 = pass."""
import os
import sys
from unittest.mock import MagicMock, patch

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import llm


def _check(label, got, want):
    if got != want:
        print(f"FAIL {label}: got {got!r}, wanted {want!r}")
        sys.exit(1)
    print(f"ok   {label}: {got!r}")


def _sent_body(testshell):
    """Run chat() with the marker set to testshell and return the request body it would POST."""
    sent = []

    def fake_chat_on(c, body, on_text):
        sent.append(body)
        return {"content": "", "tool_calls": [], "timings": {}}

    with patch.object(llm, "_testshell", return_value=testshell), \
         patch.object(llm, "_conn", return_value=MagicMock()), \
         patch.object(llm, "_chat_on", side_effect=fake_chat_on):
        llm.chat([{"role": "user", "content": "hi"}], think=False)
    _check("one request sent", len(sent), 1)
    return sent[0]


body = _sent_body(True)
_check("test VM: temperature", body.get("temperature"), 0)
_check("test VM: seed", body.get("seed"), 42)

body = _sent_body(False)
_check("owner: temperature", body.get("temperature"), 0.3)
_check("owner: no seed key", "seed" in body, False)

print("all good")
sys.exit(0)
