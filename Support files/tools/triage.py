#!/usr/bin/env python3
"""Cluster failing realrun records by signature, rank them, and bundle evidence.

CLI: triage.py <run_dir> [<run_dir>...] --suite PATH --out run/triage
Stdlib only.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys


def normalize(s):
    s = str(s or "").lower()
    s = re.sub(r"/\S+", "<path>", s)
    s = re.sub(r"0x[0-9a-f]+", "<hex>", s)
    s = re.sub(r"\d+", "<n>", s)
    return " ".join(s.split())


def _kind(rec):
    return "exception" if rec.get("error") else "assertion"


def signature(rec):
    return "|".join([
        str(rec["id"]),
        rec.get("step_failed") or "evaluate",
        _kind(rec),
        normalize(rec.get("expected") or rec.get("reason") or ""),
        normalize(rec.get("error") or rec.get("reason") or ""),
    ])


def _hash(sig):
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()[:12]


def cluster(records):
    out = {}
    for rec in records:
        if rec.get("verdict") != "FAIL":
            continue
        sig = signature(rec)
        h = _hash(sig)
        c = out.setdefault(h, {"signature": sig, "task_ids": set(), "runs": 0, "examples": []})
        c["task_ids"].add(str(rec["id"]))
        c["runs"] += 1
        if len(c["examples"]) < 2:
            c["examples"].append(rec)
    return out


def score(cl, severity=1.0, real=True):
    return severity * cl["runs"] * (1 if real else 0.3)


def rank(clusters, records):
    passed = {str(r["id"]) for r in records if r.get("verdict") == "PASS"}
    ranked = []
    for h, cl in clusters.items():
        flaky = bool(cl["task_ids"] & passed)
        label = "flaky" if flaky else "real"
        entry = dict(cl, hash=h, label=label)
        entry["score"] = score(cl, real=not flaky)
        ranked.append(entry)
    ranked.sort(key=lambda e: e["score"], reverse=True)
    return ranked


def bundle(cl, outdir, suite="suite"):
    h = cl.get("hash") or _hash(cl["signature"])
    d = os.path.join(outdir, h)
    os.makedirs(d, exist_ok=True)
    ids = sorted(cl["task_ids"])
    with open(os.path.join(d, "cluster.json"), "w") as f:
        json.dump({
            "signature": cl["signature"],
            "task_ids": ids,
            "runs": cl["runs"],
            "label": cl.get("label", "real"),
        }, f, indent=2)
    examples = cl.get("examples", [])
    trace = [{"id": r.get("id"), "step_failed": r.get("step_failed"),
              "steps": r.get("steps", {})} for r in examples]
    with open(os.path.join(d, "step-trace.json"), "w") as f:
        json.dump(trace, f, indent=2)
    for r in examples:
        src = os.path.join(r.get("_dir", "run/realrun"), "%s.png" % r["id"])
        if os.path.exists(src):
            shutil.copy(src, os.path.join(d, os.path.basename(src)))
    with open(os.path.join(d, "rerun.txt"), "w") as f:
        f.write("python3 tools/realrun.py %s --ids %s\n" % (suite, ",".join(ids)))
    return d


def load_records(run_dirs):
    recs = []
    for d in run_dirs:
        for p in sorted(glob.glob(os.path.join(d, "*.json"))):
            with open(p) as f:
                rec = json.load(f)
            if isinstance(rec, dict) and "id" in rec and "verdict" in rec:
                rec["_dir"] = d
                recs.append(rec)
    return recs


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rank and bundle failing realrun records.")
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--suite", required=True)
    ap.add_argument("--out", default="run/triage")
    a = ap.parse_args(argv)
    records = load_records(a.run_dirs)
    ranked = rank(cluster(records), records)
    if not ranked:
        print("no FAIL records")
        return 0
    print("%4s %7s %-6s %4s %-30s %s" % ("rank", "score", "label", "runs", "task_ids", "signature"))
    for i, e in enumerate(ranked, 1):
        bundle(e, a.out, suite=a.suite)
        print("%4d %7.2f %-6s %4d %-30s %s" % (
            i, e["score"], e["label"], e["runs"], ",".join(sorted(e["task_ids"])),
            e["signature"][:80]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
