#!/usr/bin/env python3
"""Compare hand verdicts from docs/research/basic-sweep.md with realrun records.

usage: compare-verdicts.py <dir> [--sweep docs/research/basic-sweep.md]

<dir> holds realrun records <dir>/S01.json ... with fields
id, verdict, reason, observed, step_failed, error, shot_error.
Prints a table and counts, and writes <dir>/compare.tsv.
Stdlib only. Runs nothing.
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # "Support files"
DEFAULT_SWEEP = "docs/research/basic-sweep.md"

# Hand verdicts decided in the "## Results — 2026-10-09" prose (decision option b).
HAND_OVERRIDES = {
    "S40": "PASS",  # real bug, FIXED (a5b2257)
    "S48": "PASS",  # real bug, FIXED (ff47fbf)
    "S04": "PASS",  # re-tested, not a bug (wording tidy is cosmetic)
    "S32": "PASS",  # re-tested, not a bug (start-up race)
    "S35": "PASS",  # re-tested, not a bug (start-up race)
    "S36": "PASS",  # re-tested, not a bug (start-up race)
    "S28": "PASS",  # notes only
    "S37": "PASS",  # notes only
    "S39": "PASS",  # notes only
}

# S-id token: S01, S 01, S01-S03 / S01 to S03 / S01–S03 (second end must carry S).
ID_RE = re.compile(r"\bS\s?(\d{1,3})(?:\s*(?:-|–|—|to)\s*S\s?(\d{1,3}))?\b")
BROKEN_RE = re.compile(r"\b(still broken|broken|open|fails?|failing|not fixed)\b", re.I)
REC_RE = re.compile(r"^S(\d+)\.json$")
REASON_WIDTH = 60


def parse_ids(text):
    """Return the S-ids in text as 'S%02d' strings, expanding ranges."""
    out = []
    for m in ID_RE.finditer(text):
        a = int(m.group(1))
        if m.group(2) is not None:
            b = int(m.group(2))
            lo, hi = sorted((a, b))
            out.extend(range(lo, hi + 1))
        else:
            out.append(a)
    return ["S%02d" % n for n in out]


def parse_sweep(path):
    """Return {id: 'PASS'|'FAIL'} from the Results prose, with HAND_OVERRIDES applied last."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r"^## Results\b", l)), None)
    if start is None:
        raise SystemExit("no '## Results' section in " + path)
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^## [^#]", lines[i])), len(lines))
    res = lines[start:end]

    # 1. Pass list: the paragraph that starts at "Pass (" and runs to the next blank line.
    pass_ids = set()
    for idx, l in enumerate(res):
        if "Pass (" in l:
            block = [l[l.index("Pass (") :]]
            for nxt in res[idx + 1 :]:
                if not nxt.strip():
                    break
                block.append(nxt)
            pass_ids.update(parse_ids("\n".join(block)))
            break
    if not pass_ids:
        raise SystemExit("no 'Pass (' list in Results section of " + path)

    # 2. Issues table and Follow-up: ids whose text says still broken / open / fails.
    broken_ids = set()
    mode = None
    for l in res:
        if "Issues found" in l:
            mode = "issues"
            continue
        if re.match(r"^###\s+Follow-up", l):
            mode = "follow"
            continue
        if mode and BROKEN_RE.search(l):
            broken_ids.update(parse_ids(l))

    verdicts = {}
    for sid in broken_ids:
        verdicts[sid] = "FAIL"
    for sid in pass_ids:
        verdicts[sid] = "PASS"
    for sid, v in HAND_OVERRIDES.items():
        verdicts[sid] = v
    return verdicts


def load_records(rdir):
    """Return {id: record dict} for every S##.json in rdir."""
    recs = {}
    for path in glob.glob(os.path.join(rdir, "S*.json")):
        m = REC_RE.match(os.path.basename(path))
        if not m:
            continue
        sid = "S%02d" % int(m.group(1))
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError) as e:
            rec = {"verdict": "BAD", "reason": "unreadable record: %s" % e, "step_failed": ""}
        recs[sid] = rec
    return recs


def _clean(s, width=None):
    s = " ".join(str(s if s is not None else "").split())
    return s[:width] if width else s


def compare(sweep, rdir):
    """Return (rows, counts). rows: dicts with id, hand, real, agree, reason, step."""
    hand = parse_sweep(sweep)
    recs = load_records(rdir)
    universe = sorted(set(hand) | set(recs), key=lambda s: int(s[1:]))
    counts = {"agree": 0, "pass_fail": 0, "fail_pass": 0, "other": 0, "unknown": 0, "missing": 0}
    rows = []
    for sid in universe:
        h = hand.get(sid, "UNKNOWN")
        rec = recs.get(sid)
        if h == "UNKNOWN":
            counts["unknown"] += 1
        if rec is None:
            counts["missing"] += 1
            rows.append({"id": sid, "hand": h, "real": "MISSING", "agree": "missing",
                         "reason": "", "step": ""})
            continue
        real = _clean(rec.get("verdict")).upper() or "NONE"
        if h == "UNKNOWN":
            agree = "unknown"
        elif h == real:
            agree = "yes"
            counts["agree"] += 1
        else:
            agree = "no"
            if h == "PASS" and real == "FAIL":
                counts["pass_fail"] += 1
            elif h == "FAIL" and real == "PASS":
                counts["fail_pass"] += 1
            else:
                counts["other"] += 1
        rows.append({"id": sid, "hand": h, "real": real, "agree": agree,
                     "reason": _clean(rec.get("reason")), "step": _clean(rec.get("step_failed"))})
    return rows, counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir", help="realrun folder holding S01.json ...")
    ap.add_argument("--sweep", default=DEFAULT_SWEEP, help="basic-sweep.md path")
    args = ap.parse_args(argv)

    sweep = args.sweep
    if not os.path.isfile(sweep) and not os.path.isabs(sweep):
        sweep = os.path.join(ROOT, sweep)
    if not os.path.isfile(sweep):
        print("sweep file not found: " + args.sweep, file=sys.stderr)
        return 2
    if not os.path.isdir(args.dir):
        print("realrun folder not found: " + args.dir, file=sys.stderr)
        return 2

    rows, counts = compare(sweep, args.dir)

    header = "%-5s %-7s %-8s %-8s %-60s %s" % ("id", "hand", "realrun", "agree", "realrun reason", "step_failed")
    print(header)
    print("-" * len(header))
    for r in rows:
        print("%-5s %-7s %-8s %-8s %-60s %s" % (r["id"], r["hand"], r["real"], r["agree"],
                                              r["reason"][:REASON_WIDTH], r["step"]))
    print()
    print("agree: %d" % counts["agree"])
    print("hand PASS / real FAIL: %d" % counts["pass_fail"])
    print("hand FAIL / real PASS: %d" % counts["fail_pass"])
    print("other mismatch: %d" % counts["other"])
    print("unknown (no hand verdict): %d" % counts["unknown"])
    print("missing (no realrun record): %d" % counts["missing"])

    tsv = os.path.join(args.dir, "compare.tsv")
    with open(tsv, "w", encoding="utf-8") as f:
        f.write("id\thand\trealrun\tagree\treason\tstep_failed\n")
        for r in rows:
            f.write("\t".join([r["id"], r["hand"], r["real"], r["agree"],
                               r["reason"][:REASON_WIDTH], r["step"]]) + "\n")
    print("wrote " + tsv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
