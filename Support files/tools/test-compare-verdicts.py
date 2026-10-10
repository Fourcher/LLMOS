#!/usr/bin/env python3
"""Tests for tools/compare-verdicts.py (stdlib only)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # "Support files"
SCRIPT = os.path.join(HERE, "compare-verdicts.py")
SWEEP = os.path.join(ROOT, "docs", "research", "basic-sweep.md")

spec = importlib.util.spec_from_file_location("compare_verdicts", SCRIPT)
cv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cv)


def check(cond, msg):
    if not cond:
        print("not ok " + msg)
        sys.exit(1)
    print("ok " + msg)


def main():
    # 1. Id parsing: extra words, slashes, ranges, spaces, stray numbers.
    got = cv.parse_ids("S01 hello, S09/S10 volume, S05-S07 x, S12 to S13 y, S20 - 3 things, S 21 ok")
    check(got == ["S01", "S09", "S10", "S05", "S06", "S07", "S12", "S13", "S20", "S21"],
          "parse_ids handles words, slashes, ranges, spaces: %s" % got)

    # 2. Real sweep: every id S01..S50 gets a hand verdict; at least 43 PASS.
    hand = cv.parse_sweep(SWEEP)
    verdicts = [hand.get("S%02d" % n, "UNKNOWN") for n in range(1, 51)]
    missing = ["S%02d" % n for n in range(1, 51) if hand.get("S%02d" % n, "UNKNOWN") == "UNKNOWN"]
    check(not missing, "all 50 ids get a hand verdict (missing: %s)" % missing)
    n_pass = verdicts.count("PASS")
    n_fail = verdicts.count("FAIL")
    print("hand counts on real sweep: PASS=%d FAIL=%d UNKNOWN=%d" % (n_pass, n_fail, verdicts.count("UNKNOWN")))
    check(n_pass >= 43, "at least 43 hand PASS (got %d)" % n_pass)

    # 3. Temp dir with 3 fake records.
    tmp = tempfile.mkdtemp(prefix="cmpverd-")
    try:
        fakes = {
            "S01": {"id": "S01", "verdict": "PASS", "reason": "hello answered"},
            "S02": {"id": "S02", "verdict": "FAIL", "reason": "no reply",
                    "step_failed": "ask", "error": "timeout"},
            "S03": {"id": "S03", "verdict": "PASS", "reason": "time spoken"},
        }
        for sid, rec in fakes.items():
            with open(os.path.join(tmp, sid + ".json"), "w", encoding="utf-8") as f:
                json.dump(rec, f)
        rows, counts = cv.compare(SWEEP, tmp)
        print("fake-dir counts: %s" % counts)
        check(counts["agree"] == 2, "agree count is 2 (got %d)" % counts["agree"])
        check(counts["pass_fail"] == 1, "hand PASS / real FAIL count is 1 (got %d)" % counts["pass_fail"])
        check(counts["fail_pass"] == 0, "hand FAIL / real PASS count is 0 (got %d)" % counts["fail_pass"])
        check(counts["unknown"] == 0, "unknown count is 0 (got %d)" % counts["unknown"])
        check(counts["missing"] == 47, "missing count is 47 (got %d)" % counts["missing"])

        proc = subprocess.run([sys.executable, SCRIPT, tmp, "--sweep", SWEEP],
                              capture_output=True, text=True)
        check(proc.returncode == 0, "CLI exits 0 (rc=%d, stderr=%s)" % (proc.returncode, proc.stderr.strip()))
        tsv = os.path.join(tmp, "compare.tsv")
        check(os.path.isfile(tsv), "compare.tsv written")
        with open(tsv, encoding="utf-8") as f:
            lines = f.read().splitlines()
        check(len(lines) == 51, "compare.tsv has header + 50 rows (got %d lines)" % len(lines))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("all good")


if __name__ == "__main__":
    main()
