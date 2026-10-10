#!/usr/bin/env python3
"""Tests for tools/triage.py. Stdlib only."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import triage  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("ok %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILURES.append(name)


def rec(run_dir, rid, verdict, error="", reason="", step_failed=None):
    r = {"id": rid, "instruction": "do " + rid, "verdict": verdict, "reason": reason,
         "observed": "", "seconds": 1.0, "steps": {"s1": "ok"}, "step_failed": step_failed,
         "error": error}
    with open(os.path.join(run_dir, "%s-%s.json" % (rid, verdict)), "w") as f:
        json.dump(r, f)
    return r


def main():
    tmp = tempfile.mkdtemp(prefix="triage-test-")
    try:
        run1 = os.path.join(tmp, "run1")
        run2 = os.path.join(tmp, "run2")
        os.makedirs(run1)
        os.makedirs(run2)

        # Same task, error differs only in PID/number and path -> one cluster.
        a = rec(run1, "t1", "FAIL", error="Crash: pid 1234 at /tmp/a/b.log", step_failed="s1")
        b = rec(run2, "t1", "FAIL", error="Crash: pid 5678 at /var/x/c.log", step_failed="s1")
        cl = triage.cluster([a, b])
        check("same-cluster-pid-path", len(cl) == 1, "clusters=%d" % len(cl))
        only = list(cl.values())[0]
        check("same-cluster-runs", only["runs"] == 2 and only["task_ids"] == {"t1"}, str(only["runs"]))
        check("normalized-signature", "<path>" in only["signature"] and "<n>" in only["signature"],
              only["signature"])

        # Different task -> another cluster.
        c = rec(run1, "t2", "FAIL", error="Crash: pid 1 at /tmp/a/b.log", step_failed="s1")
        cl2 = triage.cluster([a, b, c])
        check("different-task-new-cluster", len(cl2) == 2, "clusters=%d" % len(cl2))

        # Flaky: t3 FAILs in run1 and PASSes in run2 -> label flaky, score x0.3.
        f1 = rec(run1, "t3", "FAIL", reason="expected green")
        p3 = rec(run2, "t3", "PASS")
        cl3 = triage.cluster([f1, p3])
        ranked3 = triage.rank(cl3, [f1, p3])
        check("flaky-label", len(ranked3) == 1 and ranked3[0]["label"] == "flaky",
              str(ranked3))
        check("flaky-score", abs(ranked3[0]["score"] - 0.3) < 1e-9, str(ranked3[0]["score"]))

        # Ranking follows the formula: t4 x3 real (3.0), t5 x1 real (1.0), t6 x2 flaky (0.6).
        recs = []
        for _ in range(3):
            recs.append(rec(run1, "t4", "FAIL", error="boom at step", step_failed="s2"))
        recs.append(rec(run1, "t5", "FAIL", error="other fault", step_failed="s3"))
        for _ in range(2):
            recs.append(rec(run1, "t6", "FAIL", error="flappy fault", step_failed="s4"))
        recs.append(rec(run2, "t6", "PASS"))
        ranked = triage.rank(triage.cluster(recs), recs)
        order = [(e["task_ids"].copy().pop(), e["label"], round(e["score"], 6)) for e in ranked]
        check("rank-order", order == [("t4", "real", 3.0), ("t5", "real", 1.0), ("t6", "flaky", 0.6)],
              str(order))
        check("score-formula", triage.score({"runs": 2}, severity=2.0, real=False) == 1.2)

        # Bundle writes cluster.json, step-trace.json and rerun.txt.
        outdir = os.path.join(tmp, "out")
        d = triage.bundle(ranked[0], outdir, suite="suite.json")
        with open(os.path.join(d, "cluster.json")) as f:
            cj = json.load(f)
        check("bundle-cluster-json", cj["label"] == "real" and cj["runs"] == 3
              and cj["task_ids"] == ["t4"] and "signature" in cj, str(cj))
        check("bundle-step-trace", os.path.exists(os.path.join(d, "step-trace.json")))
        with open(os.path.join(d, "rerun.txt")) as f:
            rerun = f.read().strip()
        check("bundle-rerun", rerun == "python3 tools/realrun.py suite.json --ids t4", rerun)

        # --queue: append one open line + one draft line per new cluster, deduped by hash.
        runq = os.path.join(tmp, "runq")
        os.makedirs(runq)
        rec(runq, "q1", "FAIL", error="Crash: pid 9 at /a/b.log", step_failed="s1")
        rec(runq, "q2", "FAIL", reason="expected green", step_failed=None)
        queue = os.path.join(tmp, "queue.md")
        original = b"- [open] fake one\n- [done] fake two\n- [open] fake three\n"
        with open(queue, "wb") as f:
            f.write(original)
        cli = os.path.join(HERE, "triage.py")
        qout = os.path.join(tmp, "qout")

        def run_cli():
            return subprocess.run([sys.executable, cli, runq, "--suite", "suite.json",
                                   "--out", qout, "--queue", queue],
                                  capture_output=True, text=True)

        r1 = run_cli()
        check("queue-cli-exit", r1.returncode == 0, r1.stderr)
        with open(queue, "rb") as f:
            data1 = f.read()
        check("queue-original-intact", data1.startswith(original), repr(data1[:200]))
        added = data1[len(original):].decode("utf-8")
        alines = added.splitlines()
        cl_lines = [l for l in alines if l.startswith("- [open] (reliability) realrun cluster ")]
        draft_lines = [l for l in alines if l.startswith("  - draft FIX spec: ")]
        header_ok = bool(re.search(r"^## Triage \d{4}-\d{2}-\d{2} \d{2}:\d{2} \(2 clusters\)$",
                                   added, re.M))
        check("queue-appended-block", added.startswith("\n## Triage ") and len(cl_lines) == 2
              and len(draft_lines) == 2 and header_ok, added)

        r2 = run_cli()
        check("queue-rerun-exit", r2.returncode == 0, r2.stderr)
        with open(queue, "rb") as f:
            data2 = f.read()
        check("queue-dedupe-nothing-new", data2 == data1, repr(data2[len(data1):]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print("FAILED: %s" % ", ".join(FAILURES))
        sys.exit(1)
    print("all good")


if __name__ == "__main__":
    main()
