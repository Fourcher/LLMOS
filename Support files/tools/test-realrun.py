#!/usr/bin/env python3
"""Tests for tools/realrun.py with fake clock, user and VM runner. Stdlib only."""
import json
import os
import shlex
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import realrun  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print("ok %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILS.append(name)


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.log = []

    def __call__(self):
        self.t += 1.0
        self.log.append(self.t)
        return self.t


class FakeUser:
    def __init__(self):
        self.pressed = []
        self.shots = []
        self.typed = []

    def type_into(self, sel, text, secret=False):
        self.typed.append((sel, text))
        return True

    def press(self, key):
        self.pressed.append(key)

    def shot(self, path):
        self.shots.append(path)

    def rect(self, sel):
        return {"ok": True, "text": "rect-text"}


def make_vm(before="", after="Canberra", wait_out="ok"):
    """Fake VM with a desk whose reply is `before` until the wait step runs,
    then `after` (None = the task leaves no new reply). wait_out is what
    `llmos desk-ctl wait` prints."""
    st = {"reply": before, "busy": False}

    def vm(cmd):
        if cmd.startswith("llmos desk-ctl testreset"):
            return "ok"
        if cmd.startswith("llmos desk-ctl wait"):
            if after is not None:
                st["reply"] = after
            return wait_out
        if cmd == "llmos desk-state":
            return json.dumps({"screen": "desk", "busy": st["busy"], "reply": st["reply"],
                               "queued": 0, "dialogs": [], "windows": [], "apps": []})
        if "ls " in cmd:
            return "/root/Desktop/Test"
        return "ok"
    return vm


def reply_task(tid="reply-1"):
    return {"id": tid, "instruction": "what is the capital of australia",
            "evaluator": {"func": "include_exclude", "expected": {"include": ["canberra"]},
                          "result": {"type": "reply"}}}


def state_task(tid="state-1"):
    return {"id": tid, "instruction": "make a folder called Test on the desktop",
            "evaluator": {"func": "include_exclude", "expected": {"include": ["Test"]},
                          "result": {"type": "vm_command_line", "command": "ls /root/Desktop"}}}


def pid_files():
    found = set()
    run_dir = os.path.join(os.path.dirname(HERE), "run")
    if os.path.isdir(run_dir):
        for dp, _, fns in os.walk(run_dir):
            if "target.pid" in fns:
                found.add(os.path.join(dp, "target.pid"))
    return found


def test_no_args_no_boot():
    import subprocess
    script = os.path.join(HERE, "realrun.py")
    basic = os.path.join(HERE, "tasks", "basic.json")
    tmp = tempfile.mkdtemp(prefix="realrun-dry-")
    try:
        with open(basic, encoding="utf-8") as fh:
            data = json.load(fh)
        data["tasks"] = data["tasks"][:2]
        suite = os.path.join(tmp, "two tasks.json")
        with open(suite, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        before = pid_files()
        p = subprocess.run([sys.executable, script, suite], capture_output=True, text=True, timeout=60,
                           cwd=os.path.dirname(HERE))
        check("realrun dry exits 0", p.returncode == 0, "rc=%s err=%s" % (p.returncode, p.stderr))
        check("realrun dry prints --run", "--run" in p.stdout, p.stdout)
        check("realrun dry counts the suite", "dry: would run 2 tasks from" in p.stdout, p.stdout)
        check("realrun dry creates no target.pid", not (pid_files() - before), str(pid_files() - before))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ids_forms():
    import subprocess
    script = os.path.join(HERE, "realrun.py")
    basic = os.path.join(HERE, "tasks", "basic.json")
    # parse_ids: every spelling of the same two ids
    for label, argv in [("space", ["S12", "S13"]), ("comma", ["S12,S13"]), ("comma-space", ["S12,", "S13"]),
                        ("comma-spaces", ["S12, S13"])]:
        got = realrun.parse_ids(argv)
        check("parse_ids %s -> S12,S13" % label, got == ["S12", "S13"], repr(got))
    check("parse_ids empty comma is empty", realrun.parse_ids([","]) == [], repr(realrun.parse_ids([",", " "])))
    print("ok parse_ids forms")

    def dry(ids_argv):
        return subprocess.run([sys.executable, script, basic, "--ids"] + ids_argv, capture_output=True,
                              text=True, timeout=60, cwd=os.path.dirname(HERE))

    for label, argv in [("space", ["S12", "S13"]), ("comma", ["S12,S13"]), ("comma-space", ["S12,", "S13"]),
                        ("comma-spaces", ["S12, S13"])]:
        p = dry(argv)
        check("dry --ids %s selects 2" % label,
              p.returncode == 0 and "dry: would run 2 tasks" in p.stdout and p.stderr == "",
              "rc=%s out=%r err=%r" % (p.returncode, p.stdout, p.stderr))
    print("ok dry --ids forms select 2")

    p = dry(["S12,S13,NOPE"])
    check("unknown mixed runs known one", p.returncode == 0 and "dry: would run 2 tasks" in p.stdout
          and "unknown ids: NOPE" in p.stderr, "rc=%s out=%r err=%r" % (p.returncode, p.stdout, p.stderr))
    print("ok unknown id mixed with known")

    p = dry(["NOPE"])
    check("no match exits 2", p.returncode == 2 and "no task matches --ids: NOPE" in p.stderr
          and "dry:" not in p.stdout, "rc=%s out=%r err=%r" % (p.returncode, p.stdout, p.stderr))
    print("ok no-match exits 2")


def main():
    test_no_args_no_boot()
    test_ids_forms()
    outroot = tempfile.mkdtemp(prefix="realrun-test-")
    try:
        # 1. reply task PASSes
        rec = realrun.run_task(reply_task(), FakeUser(), make_vm(), clock=FakeClock(), outdir=outroot)
        check("reply task PASS", rec["verdict"] == "PASS" and rec["step_failed"] is None,
              json.dumps(rec)[:300])

        # 2. state task PASSes
        rec = realrun.run_task(state_task(), FakeUser(), make_vm(), clock=FakeClock(), outdir=outroot)
        check("state task PASS", rec["verdict"] == "PASS", json.dumps(rec)[:300])

        # 3. seconds equals the fake-clock difference between the first and last clock reads
        clock = FakeClock()
        rec = realrun.run_task(reply_task("reply-clock"), FakeUser(), make_vm(), clock=clock, outdir=outroot)
        expected = clock.log[-1] - clock.log[0]
        check("seconds equals fake-clock difference", rec["seconds"] == expected,
              "seconds=%r expected=%r" % (rec["seconds"], expected))
        check("record json written", os.path.exists(os.path.join(outroot, "reply-clock.json")))

        # 4. exception in setup -> FAIL with step_failed "setup"
        fresh = make_vm()

        def boom_vm(cmd):
            if cmd == "bad-setup":
                raise RuntimeError("boom")
            return fresh(cmd)
        task = reply_task("setup-boom")
        task["setup"] = ["bad-setup", "never-run"]
        rec = realrun.run_task(task, FakeUser(), boom_vm, clock=FakeClock(), outdir=outroot)
        check("setup exception -> FAIL", rec["verdict"] == "FAIL", json.dumps(rec)[:300])
        check("step_failed is setup", rec["step_failed"] == "setup", repr(rec["step_failed"]))
        check("error recorded", rec["error"] is not None and "boom" in rec["error"], repr(rec["error"]))

        # 5. suite summary counts
        suite_dir = tempfile.mkdtemp(prefix="realrun-suite-")
        suite_path = os.path.join(suite_dir, "suite.json")
        with open(suite_path, "w", encoding="utf-8") as f:
            json.dump({"tasks": [reply_task("s-pass"), state_task("s-pass2"),
                                 {"id": "s-fail", "instruction": "x",
                                  "evaluator": {"func": "include_exclude",
                                                "expected": {"include": ["nope"]},
                                                "result": {"type": "reply"}}}]}, f)
        summary = realrun.run_suite(suite_path, FakeUser(), make_vm(), outdir=outroot)
        check("summary counts", (summary["total"], summary["pass"], summary["fail"]) == (3, 2, 1),
              json.dumps({k: summary[k] for k in ("total", "pass", "fail")}))
        check("summary.json written", os.path.exists(os.path.join(outroot, "summary.json")))
        only = realrun.run_suite(suite_path, FakeUser(), make_vm(), ids=["s-pass"], outdir=outroot)
        check("ids filter", only["total"] == 1 and only["pass"] == 1, json.dumps(only)[:200])
        shutil.rmtree(suite_dir, ignore_errors=True)

        # 6. no fixed sleeps in realrun.py
        with open(os.path.join(HERE, "realrun.py"), encoding="utf-8") as f:
            src = f.read()
        poll_at = src.index("def _poll(")
        poll_end = src.index("def _slow(")
        check("sleep( only inside _poll", src.count("sleep(") == 1 and
              src.count("sleep(", poll_at, poll_end) == 1,
              "total=%d in_poll=%d" % (src.count("sleep("), src.count("sleep(", poll_at, poll_end)))

        # 7a. wait reports the desk still busy -> FAIL at step "wait", evaluate skipped
        rec = realrun.run_task(reply_task("busy-1"), FakeUser(),
                               make_vm(wait_out=json.dumps({"busy": True, "reply": "", "screen": "desk"})),
                               clock=FakeClock(), outdir=outroot)
        check("busy after wait -> FAIL", rec["verdict"] == "FAIL", json.dumps(rec)[:300])
        check("busy step_failed is wait", rec["step_failed"] == "wait", repr(rec["step_failed"]))
        check("busy reason names timeout", rec["reason"] == "still busy after 120s", repr(rec["reason"]))
        check("busy skips grade step", "grade" not in rec["steps"], repr(rec["steps"]))

        # 7b. same reply before and after -> stale, grader sees no output -> FAIL
        rec = realrun.run_task(reply_task("stale-1"), FakeUser(),
                               make_vm(before="Canberra", after=None), clock=FakeClock(), outdir=outroot)
        check("stale reply -> FAIL", rec["verdict"] == "FAIL", json.dumps(rec)[:300])
        check("stale_reply true", rec["stale_reply"] is True, repr(rec.get("stale_reply")))

        # 7c. normal case PASSes and stale_reply is false
        rec = realrun.run_task(reply_task("normal-1"), FakeUser(), make_vm(), clock=FakeClock(), outdir=outroot)
        check("normal case PASS with stale_reply false",
              rec["verdict"] == "PASS" and rec["stale_reply"] is False, json.dumps(rec)[:300])

        # 8. page and say paths: same record keys, say issues exactly one llmos say, no type_into
        page_user = FakeUser()
        page_rec = realrun.run_task(reply_task("path-page"), page_user, make_vm(),
                                    clock=FakeClock(), outdir=outroot, path="page")
        check("page path PASS", page_rec["verdict"] == "PASS", json.dumps(page_rec)[:300])
        check("page record path", page_rec["path"] == "page", repr(page_rec.get("path")))
        check("page path types into the page", len(page_user.typed) == 1 and page_user.pressed == ["ret"],
              "typed=%r pressed=%r" % (page_user.typed, page_user.pressed))

        say_user = FakeUser()
        say_cmds = []
        say_vm_inner = make_vm()

        def say_vm(cmd):
            say_cmds.append(cmd)
            return say_vm_inner(cmd)
        say_task_ = dict(reply_task("path-say"), instruction="what's the time")
        say_rec = realrun.run_task(say_task_, say_user, say_vm, clock=FakeClock(), outdir=outroot,
                                   path="say")
        check("say path PASS", say_rec["verdict"] == "PASS", json.dumps(say_rec)[:300])
        check("say record path", say_rec["path"] == "say", repr(say_rec.get("path")))
        check("same record keys on both paths", set(page_rec.keys()) == set(say_rec.keys()),
              "page-only=%r say-only=%r" % (set(page_rec) - set(say_rec), set(say_rec) - set(page_rec)))
        expected_say = "llmos say " + shlex.quote("what's the time")
        say_calls = [c for c in say_cmds if c.startswith("llmos say")]
        check("say path issues exactly one llmos say", say_calls == [expected_say],
              repr(say_calls))
        check("say path never calls type_into", say_user.typed == [], repr(say_user.typed))
        check("say path typed_ok true", say_rec["typed_ok"] is True, repr(say_rec["typed_ok"]))

        say_suite_dir = tempfile.mkdtemp(prefix="realrun-say-")
        say_suite = os.path.join(say_suite_dir, "suite.json")
        with open(say_suite, "w", encoding="utf-8") as f:
            json.dump({"tasks": [dict(reply_task("say-s1"), instruction="what's the time")]}, f)
        say_summary = realrun.run_suite(say_suite, FakeUser(), make_vm(), outdir=outroot,
                                        run_path="say")
        check("summary path say", say_summary.get("path") == "say", repr(say_summary.get("path")))
        page_summary = realrun.run_suite(say_suite, FakeUser(), make_vm(), outdir=outroot)
        check("summary path defaults to page", page_summary.get("path") == "page",
              repr(page_summary.get("path")))
        shutil.rmtree(say_suite_dir, ignore_errors=True)
        print("ok path say summary %s pass=%s" % (say_summary["path"], say_summary["pass"]))

        # 8b. shot path: relative outdir with a space is made absolute and created; repeat subfolders exist
        class ShotUser(FakeUser):
            def __init__(self):
                super().__init__()
                self.seen = []

            def shot(self, path):
                self.seen.append((path, os.path.isdir(os.path.dirname(path))))
                self.shots.append(path)

        shot_suite = os.path.join(outroot, "shot-suite.json")
        with open(shot_suite, "w", encoding="utf-8") as f:
            json.dump({"tasks": [reply_task("shot-abs")]}, f)
        shot_user = ShotUser()
        shot_cur = {"vm": make_vm()}
        cwd_before = os.getcwd()
        os.chdir(outroot)
        try:
            shot_summary = realrun.run_suite(
                shot_suite, shot_user, lambda c: shot_cur["vm"](c),
                outdir=os.path.join("rel dir", "out dir"), repeat=2,
                fresh=lambda: shot_cur.update(vm=make_vm()))
        finally:
            os.chdir(cwd_before)
        check("shot path is absolute", len(shot_user.seen) == 2 and
              all(os.path.isabs(p) for p, _ in shot_user.seen), repr(shot_user.seen))
        check("shot folder exists before the shot (repeat subfolders)",
              len(shot_user.seen) == 2 and all(ok for _, ok in shot_user.seen), repr(shot_user.seen))
        check("repeat shots land in r1 and r2",
              [os.path.basename(os.path.dirname(p)) for p, _ in shot_user.seen] == ["r1", "r2"],
              repr(shot_user.seen))
        check("shot run verdicts unaffected", shot_summary["pass"] == 1 and shot_summary["repeat"] == 2,
              json.dumps(shot_summary)[:200])

        # 8c. a shot that raises: verdict still comes from evaluate, shot_error recorded, shot still timed
        class BadShotUser(FakeUser):
            def shot(self, path):
                raise RuntimeError("QMP screendump failed")

        bad = realrun.run_task(reply_task("shot-err"), BadShotUser(), make_vm(),
                               clock=FakeClock(), outdir=outroot)
        check("shot raises -> evaluate verdict PASS", bad["verdict"] == "PASS" and bad["step_failed"] is None,
              json.dumps(bad)[:300])
        check("shot raises -> shot_error recorded",
              bad["shot_error"] is not None and "QMP screendump failed" in bad["shot_error"],
              repr(bad.get("shot_error")))
        check("shot raises -> shot step still timed", "shot" in bad["steps"] and "grade" in bad["steps"],
              repr(bad["steps"]))
        ok_rec = realrun.run_task(reply_task("shot-none"), FakeUser(), make_vm(),
                                  clock=FakeClock(), outdir=outroot)
        check("no shot error -> shot_error is None", ok_rec["shot_error"] is None, repr(ok_rec["shot_error"]))
        print("ok shot error: verdict %s from evaluate, shot_error set" % bad["verdict"])

        # 9. --repeat: scripted outcomes per repeat (True = reply right, False = reply wrong)
        def scripted(outcomes):
            cur = {"vm": make_vm(after="Canberra" if outcomes[0] else "Wrong")}
            calls = []

            def run_in_vm(cmd):
                return cur["vm"](cmd)

            def fresh():
                calls.append(1)
                i = len(calls)
                cur["vm"] = make_vm(after="Canberra" if outcomes[i] else "Wrong")
            return run_in_vm, fresh, calls

        def one_task_suite(tid):
            p = os.path.join(outroot, "suite-%s.json" % tid)
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"tasks": [reply_task(tid)]}, f)
            return p

        rep_dir = os.path.join(outroot, "rep-flaky")
        run_in_vm, fresh, calls = scripted([True, False, True])
        s = realrun.run_suite(one_task_suite("rep-flaky"), FakeUser(), run_in_vm,
                              outdir=rep_dir, repeat=3, fresh=fresh)
        row = s["tasks"][0]
        check("flaky 2 of 3 -> rate 0.67", row["rate"] == 0.67 and row["passes"] == 2 and row["runs"] == 3,
              json.dumps(row))
        check("flaky label", row["label"] == "flaky", repr(row["label"]))
        check("summary repeat field", s["repeat"] == 3, repr(s.get("repeat")))
        check("fresh called repeat-1 times (flaky)", len(calls) == 2, repr(len(calls)))
        check("repeat writes r{r}/<id>.json",
              all(os.path.exists(os.path.join(rep_dir, "r%d" % r, "rep-flaky.json")) for r in (1, 2, 3)))

        run_in_vm, fresh, calls = scripted([True, True, True])
        s = realrun.run_suite(one_task_suite("rep-pass"), FakeUser(), run_in_vm,
                              outdir=os.path.join(outroot, "rep-pass"), repeat=3, fresh=fresh)
        row = s["tasks"][0]
        check("3 of 3 -> pass", row["label"] == "pass" and row["rate"] == 1.0, json.dumps(row))
        check("fresh called repeat-1 times (pass)", len(calls) == 2, repr(len(calls)))

        run_in_vm, fresh, calls = scripted([False, False, False])
        s = realrun.run_suite(one_task_suite("rep-fail"), FakeUser(), run_in_vm,
                              outdir=os.path.join(outroot, "rep-fail"), repeat=3, fresh=fresh)
        row = s["tasks"][0]
        check("0 of 3 -> fail", row["label"] == "fail" and row["rate"] == 0.0 and row["passes"] == 0,
              json.dumps(row))
        check("fresh called repeat-1 times (fail)", len(calls) == 2, repr(len(calls)))

        # repeat=1: flat layout, no fresh call, no repeat dirs
        one_dir = os.path.join(outroot, "rep-one")
        run_in_vm, fresh, calls = scripted([True])
        s = realrun.run_suite(one_task_suite("rep-one"), FakeUser(), run_in_vm, outdir=one_dir,
                              fresh=fresh)
        check("repeat=1 writes {outdir}/<id>.json",
              os.path.exists(os.path.join(one_dir, "rep-one.json"))
              and not os.path.exists(os.path.join(one_dir, "r1")))
        check("repeat=1 never calls fresh", calls == [] and s["repeat"] == 1 and s["tasks"][0]["label"] == "pass",
              repr((calls, s.get("repeat"))))
        print("ok repeat=1 summary label=%s" % s["tasks"][0]["label"])

        # 9b. vm_json on the shapes tools/tsh prints (tsh keeps the echoed command, the prompt and the
        # "[vmctl: ...]" trailer; grep drops only blank, DONE_, "!" and bare-prompt lines)
        desk_json = json.dumps({"screen": "wizard", "busy": False, "reply": "", "windows": []})
        echo_line = '!llmos desk-state; echo DONE_""12345'
        check("vm_json: pure JSON unchanged", realrun.vm_json(desk_json) == json.loads(desk_json))
        check("vm_json: echo line before the JSON",
              realrun.vm_json(echo_line + "\n" + desk_json + "\n\n[vmctl: matched after 1.2s]\n")
              == json.loads(desk_json))
        check("vm_json: JSON line then prompt/marker line",
              realrun.vm_json(desk_json + "\nllmos:/# \n[vmctl: matched after 0.8s]\n") == json.loads(desk_json))
        check("vm_json: timeout only -> None",
              realrun.vm_json("[vmctl: TIMEOUT after 30.4s]\n") is None)
        nested = {"screen": "desk", "reply": "use {x} and } here", "busy": False}
        check("vm_json: nested braces inside a string value",
              realrun.vm_json(echo_line + "\n" + json.dumps(nested) + "\n[vmctl: matched after 2.0s]\n")
              == nested)
        check("vm_json: last JSON line wins",
              realrun.vm_json('{"a": 1}\n' + desk_json + "\n") == json.loads(desk_json))
        check("vm_json: non-JSON text -> None", realrun.vm_json("Traceback: nope") is None)
        check("vm_json: None input -> None", realrun.vm_json(None) is None)
        check("vm_json: wait output with echo and trailer",
              realrun.vm_json(echo_line + "\n{\"busy\": true}\n\n[vmctl: matched after 9.0s]\n") == {"busy": True})
        # the wrapped reply path: desk-state with echo/trailer lines is read as the reply
        vm_wrapped = make_vm(after="Canberra")

        def wrapped(cmd):
            out = vm_wrapped(cmd)
            if cmd == "llmos desk-state":
                return echo_line + "\n" + out + "\n[vmctl: matched after 1.0s]\n"
            return out
        rec = realrun.run_task(reply_task("wrapped-1"), FakeUser(), wrapped, clock=FakeClock(), outdir=outroot)
        check("run_task reads desk-state through tsh-shaped output", rec["verdict"] == "PASS", json.dumps(rec)[:300])
        print("ok vm_json shapes: echo, prompt, timeout, nested braces")

        # 9c. vm_text: the vmctl trailer is removed from graded text; TIMEOUT gives None
        check("vm_text: trailer only matched -> empty string",
              realrun.vm_text("[vmctl: matched after 1.0s]\n") == "", repr(realrun.vm_text("[vmctl: matched after 1.0s]\n")))
        check("vm_text: trailer only TIMEOUT -> None",
              realrun.vm_text("[vmctl: TIMEOUT after 30.4s]\n") is None)
        check("vm_text: multi-line output keeps its lines",
              realrun.vm_text("a.txt\nb.txt\n\n[vmctl: matched after 2.2s]\n") == "a.txt\nb.txt",
              repr(realrun.vm_text("a.txt\nb.txt\n\n[vmctl: matched after 2.2s]\n")))
        check("vm_text: trailer glued mid-line is removed, rest of line kept",
              realrun.vm_text("see [vmctl: matched after 1.0s] in text\n[vmctl: matched after 1.0s]\n")
              == "see  in text",
              repr(realrun.vm_text("see [vmctl: matched after 1.0s] in text\n[vmctl: matched after 1.0s]\n")))
        check("vm_text: TIMEOUT trailer with output -> None",
              realrun.vm_text("partial\n[vmctl: TIMEOUT after 30.4s]\n") is None)
        check("vm_text: non-string -> None", realrun.vm_text(None) is None)
        check("vm_text: no trailer strips trailing whitespace",
              realrun.vm_text("Canberra  \n\n") == "Canberra", repr(realrun.vm_text("Canberra  \n\n")))
        print("ok vm_text trailer removal, TIMEOUT -> None, multi-line kept")

        # 9c2. vm_text drops the echoed command line (prompt + text); keeps mid-line "#" and bare-prompt-free output
        echo_cmd = "llmos:/# cd /usr/lib/llmos && python3 -c \"print('dark' if x else 'light')\""
        check("vm_text: echoed command line dropped, output kept",
              realrun.vm_text(echo_cmd + "\ndark\n[vmctl: matched after 1.0s]\n") == "dark",
              repr(realrun.vm_text(echo_cmd + "\ndark\n[vmctl: matched after 1.0s]\n")))
        check("vm_text: mid-line # kept",
              realrun.vm_text("issue #5 llmos:/# here\n") == "issue #5 llmos:/# here",
              repr(realrun.vm_text("issue #5 llmos:/# here\n")))
        check("vm_text: bare prompt line dropped",
              realrun.vm_text("llmos:/#\nok\n") == "ok", repr(realrun.vm_text("llmos:/#\nok\n")))
        check("vm_text: multi-line output kept after echo",
              realrun.vm_text("llmos:/# ls\na.txt\nb.txt\n[vmctl: matched after 1.0s]\n") == "a.txt\nb.txt",
              repr(realrun.vm_text("llmos:/# ls\na.txt\nb.txt\n[vmctl: matched after 1.0s]\n")))
        print("ok vm_text drops echoed command line, keeps mid-line # and multi-line output")

        # 9c3. tsh types at the console prompt "› " and prefixes "!": the echo is "› !cmd"
        tsh_echo = "› !cat /etc/llmos/settings.json; echo"
        check("vm_text: tsh echo \"› !cmd\" dropped",
              realrun.vm_text(tsh_echo + "\n{}\n[vmctl: matched after 1.0s]\n") == "{}",
              repr(realrun.vm_text(tsh_echo + "\n{}\n[vmctl: matched after 1.0s]\n")))
        check("vm_text: reply line with mid-line › kept",
              realrun.vm_text("the arrow › is used\n") == "the arrow › is used",
              repr(realrun.vm_text("the arrow › is used\n")))
        check("vm_text: llmos:/# echo still dropped",
              realrun.vm_text("llmos:/# echo hi\nhi\n") == "hi", repr(realrun.vm_text("llmos:/# echo hi\nhi\n")))
        print("ok vm_text drops tsh \"› !cmd\" echo, keeps mid-line ›, still drops llmos:/# echo")

        def echo_cmd_vm(output):
            def vm(cmd):
                if cmd == "fake-state-cmd":
                    return output
                return make_vm()(cmd)
            return vm

        s12_task = {"id": "S12-like", "instruction": "is the theme dark",
                    "evaluator": {"func": "include_exclude", "expected": {"include": ["dark"], "exclude": ["light"]},
                                  "result": {"type": "vm_command_line", "command": "fake-state-cmd"}}}
        s12_rec = realrun.run_task(s12_task, FakeUser(),
                                   echo_cmd_vm(echo_cmd + "\ndark\n[vmctl: matched after 1.0s]\n"),
                                   clock=FakeClock(), outdir=outroot)
        check("S12-like echo+dark -> PASS", s12_rec["verdict"] == "PASS" and s12_rec["observed"] == "dark",
              json.dumps(s12_rec)[:300])
        print("ok S12-like observed=%r verdict=%s" % (s12_rec["observed"], s12_rec["verdict"]))

        s19_task = {"id": "S19-like", "instruction": "make a folder called Test",
                    "evaluator": {"func": "include_exclude", "expected": {"include": ["/root/Desktop/Test"]},
                                  "result": {"type": "vm_command_line", "command": "fake-state-cmd"}}}
        s19_rec = realrun.run_task(s19_task, FakeUser(),
                                   echo_cmd_vm("llmos:/# ls -d /root/Desktop/Test; echo DONE_\"\"1\n"
                                               "[vmctl: matched after 1.0s]\n"),
                                   clock=FakeClock(), outdir=outroot)
        check("S19-like echo-only (folder missing) -> FAIL",
              s19_rec["verdict"] == "FAIL" and s19_rec["observed"] == "", json.dumps(s19_rec)[:300])
        print("ok S19-like observed=%r verdict=%s" % (s19_rec["observed"], s19_rec["verdict"]))

        # 9d. vm_command_line getter: the matched trailer is not part of the observed text
        trailer_vm = make_vm()

        def trailer_cmd(cmd):
            if cmd == "ls /root/Desktop":
                return "/root/Desktop/Test\n[vmctl: matched after 1.0s]\n"
            return trailer_vm(cmd)
        trailer_rec = realrun.run_task(state_task("trailer-1"), FakeUser(), trailer_cmd,
                                       clock=FakeClock(), outdir=outroot)
        check("vm_command_line observed has no trailer",
              trailer_rec["observed"] == "/root/Desktop/Test" and trailer_rec["verdict"] == "PASS",
              json.dumps(trailer_rec)[:300])
        print("ok run_task vm_command_line observed=%r verdict=%s" % (trailer_rec["observed"], trailer_rec["verdict"]))

        # 9e. stuck-turn drain: a fake desk that stays busy after the wait; cancel ends it after `left` polls
        def make_drain_vm(left=2, cancel_raises=False, drop_queued=False, never_idle=False, busy_waits=1):
            base = make_vm()
            st = {"busy": False, "cancelled": False, "left": left, "busy_waits": busy_waits,
                  "reply": "", "never_idle": never_idle, "cmds": [], "events": []}

            def vm(cmd):
                st["cmds"].append(cmd)
                if cmd == "llmos desk-ctl testreset":
                    st["events"].append("testreset")
                    st["reply"] = ""  # a reset clears the reply; a busy desk stays busy
                    return "ok"
                if cmd == "llmos desk-ctl cancel":
                    st["cancelled"] = True
                    if cancel_raises:
                        raise RuntimeError("cancel refused")
                    return "ok"
                if cmd.startswith("llmos desk-ctl wait"):
                    if st["busy_waits"] > 0:
                        st["busy_waits"] -= 1
                        st["busy"] = True
                    if not st["busy"]:
                        st["reply"] = "Canberra"
                    return json.dumps({"busy": st["busy"], "reply": st["reply"], "screen": "desk"})
                if cmd == "llmos desk-state":
                    if st["cancelled"] and st["busy"] and not st["never_idle"]:
                        if st["left"] > 0:
                            st["left"] -= 1
                        else:
                            st["busy"] = False
                    d = {"screen": "desk", "busy": st["busy"], "reply": st["reply"],
                         "dialogs": [], "windows": [], "apps": []}
                    if not drop_queued:
                        d["queued"] = 0
                    return json.dumps(d)
                return base(cmd)
            return vm, st

        def no_sleep(_s):
            pass

        vm, st = make_drain_vm(left=2)
        busy_rec = realrun.run_task(reply_task("drain-busy"), FakeUser(), vm, clock=FakeClock(),
                                    outdir=outroot, sleep=no_sleep)
        cancels = [c for c in st["cmds"] if c == "llmos desk-ctl cancel"]
        check("busy after wait -> cancel sent once", len(cancels) == 1, repr(st["cmds"]))
        check("busy drain: verdict still FAIL with the same reason",
              busy_rec["verdict"] == "FAIL" and busy_rec["reason"] == "still busy after 120s", json.dumps(busy_rec)[:300])
        check("busy drain: cancelled true, not stuck, drain time recorded",
              busy_rec["cancelled"] is True and busy_rec["stuck"] is False
              and isinstance(busy_rec["drain_seconds"], float) and busy_rec["drain_seconds"] > 0,
              json.dumps({k: busy_rec[k] for k in ("cancelled", "stuck", "drain_seconds")}))
        check("busy drain: idle on poll 3 (2 busy polls after cancel)", st["left"] == 0 and st["busy"] is False,
              repr((st["left"], st["busy"])))
        nxt = realrun.run_task(reply_task("drain-next"), FakeUser(), vm, clock=FakeClock(), outdir=outroot,
                               sleep=no_sleep)
        check("next task after drain runs normally PASS", nxt["verdict"] == "PASS" and nxt["cancelled"] is False
              and nxt["stuck"] is False and nxt["stale_reply"] is False, json.dumps(nxt)[:300])
        print("ok drain: busy -> cancel -> idle on poll 3 -> cancelled true, next task PASS")

        # missing queued key counts as 0: idle detection still works
        vm, st = make_drain_vm(left=2, drop_queued=True)
        dq = realrun.run_task(reply_task("drain-noq"), FakeUser(), vm, clock=FakeClock(), outdir=outroot,
                              sleep=no_sleep)
        check("desk-state without queued -> drain idle, not stuck", dq["cancelled"] is True and dq["stuck"] is False,
              json.dumps({k: dq[k] for k in ("cancelled", "stuck")}))

        # cancel command fails -> still polls to idle
        vm, st = make_drain_vm(left=2, cancel_raises=True)
        cr = realrun.run_task(reply_task("drain-cerr"), FakeUser(), vm, clock=FakeClock(), outdir=outroot,
                              sleep=no_sleep)
        check("cancel raises -> still polls, idle, not stuck",
              cr["cancelled"] is True and cr["stuck"] is False and "drain" in cr["steps"],
              json.dumps({k: cr[k] for k in ("cancelled", "stuck")}))

        # never idle -> stuck true; the suite calls fresh() before the next task
        events = []
        vm, st = make_drain_vm(never_idle=True)
        real_vm = vm

        def logged_vm(cmd):
            if cmd == "llmos desk-ctl testreset":
                events.append("testreset")
            return real_vm(cmd)
        stuck_suite_dir = tempfile.mkdtemp(prefix="realrun-stuck-")
        stuck_suite = os.path.join(stuck_suite_dir, "suite.json")
        with open(stuck_suite, "w", encoding="utf-8") as f:
            json.dump({"tasks": [reply_task("stuck-1"), reply_task("stuck-2")]}, f)

        def fresh_fake():
            events.append("fresh")
            st.update(busy=False, cancelled=False, never_idle=False)
        realrun.run_suite(stuck_suite, FakeUser(), logged_vm, outdir=os.path.join(outroot, "stuck"),
                          fresh=fresh_fake, sleep=no_sleep, clock=FakeClock())
        stuck_rec = json.load(open(os.path.join(outroot, "stuck", "stuck-1.json"), encoding="utf-8"))
        check("never idle -> stuck true", stuck_rec["stuck"] is True and stuck_rec["cancelled"] is True,
              json.dumps({k: stuck_rec[k] for k in ("cancelled", "stuck")}))
        check("never idle -> fresh() before the next task",
              events == ["testreset", "fresh", "testreset"], repr(events))
        next_rec = json.load(open(os.path.join(outroot, "stuck", "stuck-2.json"), encoding="utf-8"))
        check("task after fresh runs normally PASS", next_rec["verdict"] == "PASS" and next_rec["stuck"] is False,
              json.dumps(next_rec)[:300])
        shutil.rmtree(stuck_suite_dir, ignore_errors=True)
        print("ok stuck: never idle -> stuck true, fresh before next task, next PASS")

        # never idle with no fresh available: stuck is recorded, the suite still continues
        vm, st = make_drain_vm(never_idle=True)
        nf_suite_dir = tempfile.mkdtemp(prefix="realrun-nofresh-")
        nf_suite = os.path.join(nf_suite_dir, "suite.json")
        with open(nf_suite, "w", encoding="utf-8") as f:
            json.dump({"tasks": [reply_task("nf-1"), reply_task("nf-2")]}, f)
        nf_summary = realrun.run_suite(nf_suite, FakeUser(), vm, outdir=os.path.join(outroot, "nofresh"),
                                       sleep=no_sleep, clock=FakeClock())
        check("never idle without fresh -> suite continues to 2 tasks", nf_summary["total"] == 2,
              json.dumps(nf_summary)[:200])
        shutil.rmtree(nf_suite_dir, ignore_errors=True)

        # normal task: no cancel, no drain step, cancelled false, stuck false
        normal_cmds = []
        normal_vm = make_vm()

        def recording_vm(cmd):
            normal_cmds.append(cmd)
            return normal_vm(cmd)
        nr = realrun.run_task(reply_task("normal-drain"), FakeUser(), recording_vm, clock=FakeClock(),
                              outdir=outroot, sleep=no_sleep)
        check("normal task sends no cancel",
              "llmos desk-ctl cancel" not in normal_cmds and "drain" not in nr["steps"], repr(normal_cmds))
        check("normal task fields false/None", nr["cancelled"] is False and nr["stuck"] is False
              and nr["drain_seconds"] is None, json.dumps({k: nr[k] for k in ("cancelled", "stuck", "drain_seconds")}))
        print("ok drain: normal task sends no cancel")

        # 9f. a cancelled task (drained idle, not stuck) -> the next task starts on one fresh overlay
        cf_dir = tempfile.mkdtemp(prefix="realrun-cancel-")
        cf_suite = os.path.join(cf_dir, "suite.json")
        with open(cf_suite, "w", encoding="utf-8") as f:
            json.dump({"tasks": [reply_task("cf-1"), reply_task("cf-2")]}, f)
        vm, st = make_drain_vm(left=2, busy_waits=1)  # task 1 finds the desk busy; task 2 finds it idle

        def cf_fresh():
            cf_calls.append("fresh")
            st.update(busy=False, cancelled=False)
        cf_calls = []
        cf_out = os.path.join(outroot, "cancel-next")
        realrun.run_suite(cf_suite, FakeUser(), vm, outdir=cf_out, fresh=cf_fresh, sleep=no_sleep,
                          clock=FakeClock())
        cf1 = json.load(open(os.path.join(cf_out, "cf-1.json"), encoding="utf-8"))
        cf2 = json.load(open(os.path.join(cf_out, "cf-2.json"), encoding="utf-8"))
        check("cancelled task (drained idle) -> fresh() called once before task 2", cf_calls == ["fresh"],
              repr(cf_calls))
        check("cancelled task 1: cancelled true, stuck false, fresh_before None",
              cf1["cancelled"] is True and cf1["stuck"] is False and cf1["fresh_before"] is None,
              json.dumps({k: cf1[k] for k in ("cancelled", "stuck", "fresh_before")}))
        check("task 2 after cancel: fresh_before names the reason and task 2 PASSes",
              cf2["fresh_before"] == "previous task cancelled" and cf2["verdict"] == "PASS",
              json.dumps({k: cf2[k] for k in ("fresh_before", "verdict")}))
        shutil.rmtree(cf_dir, ignore_errors=True)
        print("ok cancel: cancelled task -> fresh once before next task, fresh_before recorded")

        # no cancel anywhere -> fresh() never called, fresh_before null
        nc_dir = tempfile.mkdtemp(prefix="realrun-nocancel-")
        nc_suite = os.path.join(nc_dir, "suite.json")
        with open(nc_suite, "w", encoding="utf-8") as f:
            json.dump({"tasks": [reply_task("nc-1"), reply_task("nc-2"), reply_task("nc-3")]}, f)
        nc_calls = []
        nc_out = os.path.join(outroot, "no-cancel")
        nc_vm, _nc_st = make_drain_vm(busy_waits=0)  # its testreset clears the reply, so no task sees a stale one
        nc_sum = realrun.run_suite(nc_suite, FakeUser(), nc_vm, outdir=nc_out,
                                   fresh=lambda: nc_calls.append("fresh"), sleep=no_sleep, clock=FakeClock())
        check("no cancels -> fresh() never called, all PASS, fresh_before null",
              nc_calls == [] and nc_sum["pass"] == 3 and all(
                  json.load(open(os.path.join(nc_out, "nc-%d.json" % i), encoding="utf-8"))["fresh_before"] is None
                  for i in (1, 2, 3)), repr(nc_calls))
        shutil.rmtree(nc_dir, ignore_errors=True)

        # last task cancelled -> no trailing fresh() (the next task never runs, so no reboot is made for it)
        lc_dir = tempfile.mkdtemp(prefix="realrun-lastcancel-")
        lc_suite = os.path.join(lc_dir, "suite.json")
        with open(lc_suite, "w", encoding="utf-8") as f:
            json.dump({"tasks": [reply_task("lc-1")]}, f)
        vm, st = make_drain_vm(left=2, busy_waits=1)
        lc_calls = []
        lc_out = os.path.join(outroot, "last-cancel")
        realrun.run_suite(lc_suite, FakeUser(), vm, outdir=lc_out,
                          fresh=lambda: lc_calls.append("fresh"), sleep=no_sleep, clock=FakeClock())
        lc1 = json.load(open(os.path.join(lc_out, "lc-1.json"), encoding="utf-8"))
        check("last task cancelled -> no trailing fresh(), record cancelled",
              lc_calls == [] and lc1["cancelled"] is True, repr((lc_calls, lc1["cancelled"])))
        shutil.rmtree(lc_dir, ignore_errors=True)
        print("ok cancel: last task cancelled -> no trailing fresh()")

        # 10. fresh_overlay: readiness, onboarding, desk-ready polls with a fake clock (sleep advances it)
        class FakeTime:
            def __init__(self):
                self.t = 0.0

            def clock(self):
                return self.t

            def sleep(self, s):
                self.t += s

        def scripted_vm(answers):
            calls = []

            def vm(cmd):
                calls.append(cmd)
                if cmd == "echo up":
                    out = answers["up"].pop(0)
                    if isinstance(out, Exception):
                        raise out
                    return out
                if cmd == realrun.ONBOARD_CMD:
                    return ""
                if cmd == "llmos desk-state":
                    return answers["desk"].pop(0)
                raise AssertionError("unexpected command %r" % cmd)
            return vm, calls

        onboard_literal = 'cd /usr/lib/llmos && python3 -c "from llmos import config; config.settings.set(\\"onboarded\\", True)"'
        check("onboard command quoted as calc-smoke", realrun.ONBOARD_CMD == onboard_literal, repr(realrun.ONBOARD_CMD))

        wizard = json.dumps({"screen": "wizard", "busy": False, "reply": ""})
        desk = json.dumps({"screen": "desk", "busy": False, "reply": ""})
        ft = FakeTime()
        vm, calls = scripted_vm({"up": [RuntimeError("no answer"), OSError("refused"), "up\n"],
                                 "desk": [wizard, desk]})
        realrun.fresh_overlay(vm, boot=lambda: None, clock=ft.clock, sleep=ft.sleep)
        onboard_calls = [c for c in calls if c == realrun.ONBOARD_CMD]
        check("fresh: VM up after two failures, onboarded once, desk after wizard",
              len(onboard_calls) == 1 and calls.count("echo up") == 3 and
              calls.count("llmos desk-state") == 2,
              repr(calls))
        print("ok fresh succeeds: onboard issued %d time, polls up=%d desk=%d" %
              (len(onboard_calls), calls.count("echo up"), calls.count("llmos desk-state")))

        # desk-state that is not JSON keeps polling
        ft = FakeTime()
        vm, calls = scripted_vm({"up": ["up"], "desk": ["Traceback: nope", desk]})
        realrun.fresh_overlay(vm, boot=lambda: None, clock=ft.clock, sleep=ft.sleep)
        check("fresh: non-JSON desk-state keeps polling", calls.count("llmos desk-state") == 2,
              repr(calls))

        # VM never answers -> RuntimeError
        ft = FakeTime()
        vm, calls = scripted_vm({"up": [RuntimeError("never")] * 10000, "desk": []})
        try:
            realrun.fresh_overlay(vm, boot=lambda: None, clock=ft.clock, sleep=ft.sleep)
            err = None
        except RuntimeError as e:
            err = str(e)
        check("fresh: VM never up -> RuntimeError", err == "fresh: VM not ready", repr(err))
        check("fresh: never-up does not onboard", realrun.ONBOARD_CMD not in calls, repr(calls[-3:]))

        # desk never leaves the wizard -> RuntimeError
        ft = FakeTime()
        vm, calls = scripted_vm({"up": ["up"], "desk": [wizard] * 10000})
        try:
            realrun.fresh_overlay(vm, boot=lambda: None, clock=ft.clock, sleep=ft.sleep)
            err = None
        except RuntimeError as e:
            err = str(e)
        check("fresh: desk never ready -> RuntimeError", err == "fresh: desk not ready", repr(err))
        print("ok fresh timeouts raise RuntimeError")

        # desk-ready requires screen == "desk": lock keeps polling, missing screen keeps polling
        lock = json.dumps({"screen": "lock", "busy": False, "reply": ""})
        ft = FakeTime()
        vm, calls = scripted_vm({"up": ["up"], "desk": [lock, lock, desk]})
        realrun.fresh_overlay(vm, boot=lambda: None, clock=ft.clock, sleep=ft.sleep)
        check("fresh: lock then desk succeeds after 3 desk-state polls",
              calls.count("llmos desk-state") == 3, repr(calls))
        print("ok fresh lock-then-desk polls=%d" % calls.count("llmos desk-state"))

        ft = FakeTime()
        vm, calls = scripted_vm({"up": ["up"], "desk": [lock] * 10000})
        try:
            realrun.fresh_overlay(vm, boot=lambda: None, clock=ft.clock, sleep=ft.sleep)
            err = None
        except RuntimeError as e:
            err = str(e)
        check("fresh: lock forever -> RuntimeError", err == "fresh: desk not ready", repr(err))
        print("ok fresh lock-only raises RuntimeError")

        check("desk-ready: missing screen key is not ready",
              realrun._desk_ready(json.dumps({"busy": False, "reply": ""})) is False)
        # 7c. the desk reports "done": the wait asks for the requests finished after the count it read
        def vm_done(extra, waits):
            st = {"reply": ""}

            def vm(cmd):
                if cmd.startswith("llmos desk-ctl testreset"):
                    return "ok"
                if cmd.startswith("llmos desk-ctl wait"):
                    waits.append(cmd)
                    st["reply"] = "Canberra"
                    return "ok"
                if cmd == "llmos desk-state":
                    d = {"screen": "desk", "busy": False, "reply": st["reply"], "queued": 0,
                         "dialogs": [], "windows": [], "apps": []}
                    d.update(extra)
                    return json.dumps(d)
                if "ls " in cmd:
                    return "/root/Desktop/Test"
                return "ok"
            return vm

        waits = []
        realrun.run_task(reply_task("done-1"), FakeUser(), vm_done({"done": 7}, waits),
                         clock=FakeClock(), outdir=outroot)
        check("desk with done=7 -> wait 'after 7'", waits == ["llmos desk-ctl wait 120 after 7"], repr(waits))
        if waits == ["llmos desk-ctl wait 120 after 7"]:
            print("ok desk with done=7 waits 'after 7'")
        waits = []
        realrun.run_task(reply_task("done-2"), FakeUser(), vm_done({}, waits),
                         clock=FakeClock(), outdir=outroot)
        check("older desk without done -> old wait command", waits == ["llmos desk-ctl wait 120"], repr(waits))
        if waits == ["llmos desk-ctl wait 120"]:
            print("ok older desk without done uses the old wait command")

        # 11. approve tasks: a desk that asks (desk-state "dialogs") and blocks until "dialog yes".
        # wait slices advance the turn unless an ask is open; "dialog yes" clears the open ask; cancel stops it.
        def make_approve_vm(ask_at=(), done_at=1):
            st = {"slices": 0, "progress": 0, "dialogs": [], "done_at": done_at, "stopped": False,
                  "reply": "", "cmds": []}

            def vm(cmd):
                st["cmds"].append(cmd)
                if cmd == "llmos desk-ctl testreset":
                    st.update(slices=0, progress=0, dialogs=[], stopped=False, reply="")
                    return "ok"
                if cmd == "llmos desk-ctl cancel":
                    st.update(stopped=True, dialogs=[])
                    return "ok"
                if cmd == "llmos desk-ctl dialog yes":
                    st["dialogs"] = []
                    return "ok"
                if cmd.startswith("llmos desk-ctl wait"):
                    st["slices"] += 1
                    if st["slices"] in ask_at and not st["stopped"]:
                        st["dialogs"].append({"id": "d%d" % st["slices"], "title": "Empty the trash?", "text": ""})
                    if not st["dialogs"] and not st["stopped"]:
                        st["progress"] += 1
                    done = (st["progress"] >= st["done_at"] and not st["dialogs"]) or st["stopped"]
                    if done and not st["stopped"]:
                        st["reply"] = "Canberra"
                    return json.dumps({"busy": not done, "reply": st["reply"], "screen": "desk"})
                if cmd == "llmos desk-state":
                    busy = not st["stopped"] and (st["progress"] < st["done_at"] or bool(st["dialogs"]))
                    return json.dumps({"screen": "desk", "busy": busy, "reply": st["reply"], "queued": 0,
                                       "dialogs": list(st["dialogs"]), "windows": [], "apps": []})
                if "ls " in cmd:
                    return "/root/Desktop/Test"
                return "ok"
            return vm, st

        def yes_count(cmds):
            return len([c for c in cmds if c == "llmos desk-ctl dialog yes"])

        # 11a. approve + one ask -> one "dialog yes", PASS, approved 1
        vm, st = make_approve_vm(ask_at=(1,), done_at=2)
        rec = realrun.run_task(dict(reply_task("ap-one"), approve=True), FakeUser(), vm,
                               clock=FakeClock(), outdir=outroot, sleep=no_sleep)
        check("approve + one dialog -> one dialog yes sent", yes_count(st["cmds"]) == 1, repr(st["cmds"]))
        check("approve + one dialog -> PASS, approved 1", rec["verdict"] == "PASS" and rec["approved"] == 1,
              json.dumps({k: rec[k] for k in ("verdict", "approved", "reason")}))

        # 11b. approve + no ask -> finishes normally, approved 0
        vm, st = make_approve_vm(ask_at=(), done_at=1)
        rec = realrun.run_task(dict(reply_task("ap-none"), approve=True), FakeUser(), vm,
                               clock=FakeClock(), outdir=outroot, sleep=no_sleep)
        check("approve + no dialog -> PASS, approved 0, no dialog yes",
              rec["verdict"] == "PASS" and rec["approved"] == 0 and yes_count(st["cmds"]) == 0,
              json.dumps({k: rec[k] for k in ("verdict", "approved")}))

        # 11c. approve + two asks -> answered twice
        vm, st = make_approve_vm(ask_at=(1, 3), done_at=3)
        rec = realrun.run_task(dict(reply_task("ap-two"), approve=True), FakeUser(), vm,
                               clock=FakeClock(), outdir=outroot, sleep=no_sleep)
        check("approve + two dialogs -> two dialog yes, PASS",
              yes_count(st["cmds"]) == 2 and rec["approved"] == 2 and rec["verdict"] == "PASS",
              json.dumps({k: rec[k] for k in ("verdict", "approved")}) + repr(yes_count(st["cmds"])))

        # 11d. non-approve task with an ask -> no dialog yes sent (unchanged: the wait is one call, the task fails
        # and is cancelled)
        vm, st = make_approve_vm(ask_at=(1,), done_at=2)
        rec = realrun.run_task(reply_task("noap-dialog"), FakeUser(), vm,
                               clock=FakeClock(), outdir=outroot, sleep=no_sleep)
        check("non-approve task with a dialog -> no dialog yes sent", yes_count(st["cmds"]) == 0 and
              rec["approved"] == 0, repr(st["cmds"]))

        # 11e. approve task that never finishes within timeout_s -> FAIL, cancelled, next task gets a reboot
        vm, st = make_approve_vm(ask_at=(), done_at=10 ** 6)
        ap_dir = tempfile.mkdtemp(prefix="realrun-approve-")
        ap_suite = os.path.join(ap_dir, "suite.json")
        with open(ap_suite, "w", encoding="utf-8") as f:
            json.dump({"tasks": [dict(reply_task("ap-timeout"), approve=True, timeout_s=3),
                                 reply_task("ap-after")]}, f)
        ap_calls = []

        def ap_fresh():
            ap_calls.append("fresh")
            st.update(done_at=1, stopped=False, dialogs=[], progress=0)
        ap_sum = realrun.run_suite(ap_suite, FakeUser(), vm, outdir=os.path.join(outroot, "approve-timeout"),
                                   fresh=ap_fresh, sleep=no_sleep, clock=FakeClock())
        ap1 = json.load(open(os.path.join(outroot, "approve-timeout", "ap-timeout.json"), encoding="utf-8"))
        ap2 = json.load(open(os.path.join(outroot, "approve-timeout", "ap-after.json"), encoding="utf-8"))
        check("approve timeout -> FAIL, cancelled, reason kept",
              ap1["verdict"] == "FAIL" and ap1["cancelled"] is True and ap1["reason"] == "still busy after 3s",
              json.dumps({k: ap1[k] for k in ("verdict", "cancelled", "reason")}))
        check("approve timeout -> next task gets fresh before it and PASSes",
              ap_calls == ["fresh"] and ap2["fresh_before"] == "previous task cancelled" and ap2["verdict"] == "PASS",
              repr((ap_calls, ap2["fresh_before"], ap2["verdict"])))
        shutil.rmtree(ap_dir, ignore_errors=True)

        # 11f. a task whose type step raises -> the next task starts on a fresh overlay ("previous task error")
        class TypeFailUser(FakeUser):
            def __init__(self):
                super().__init__()
                self.fails = 1

            def type_into(self, sel, text, secret=False):
                if self.fails > 0:
                    self.fails -= 1
                    raise RuntimeError("typing failed")
                return super().type_into(sel, text, secret)

        tf_dir = tempfile.mkdtemp(prefix="realrun-typefail-")
        tf_suite = os.path.join(tf_dir, "suite.json")
        with open(tf_suite, "w", encoding="utf-8") as f:
            json.dump({"tasks": [reply_task("tf-1"), reply_task("tf-2")]}, f)
        tf_calls = []
        tf_out = os.path.join(outroot, "type-fail")
        realrun.run_suite(tf_suite, TypeFailUser(), make_vm(), outdir=tf_out,
                          fresh=lambda: tf_calls.append("fresh"), sleep=no_sleep, clock=FakeClock())
        tf1 = json.load(open(os.path.join(tf_out, "tf-1.json"), encoding="utf-8"))
        tf2 = json.load(open(os.path.join(tf_out, "tf-2.json"), encoding="utf-8"))
        check("type step raises -> step_failed type, FAIL", tf1["step_failed"] == "type" and tf1["verdict"] == "FAIL",
              json.dumps({k: tf1[k] for k in ("step_failed", "verdict")}))
        check("step_failed type -> next task gets fresh(), fresh_before names it, PASS",
              tf_calls == ["fresh"] and tf2["fresh_before"] == "previous task error: type" and tf2["verdict"] == "PASS",
              repr((tf_calls, tf2["fresh_before"], tf2["verdict"])))
        shutil.rmtree(tf_dir, ignore_errors=True)
        # 11g. approve task whose typed line reaches the desk only after 7 s: for the first 7 s done stays at
        # done0 and busy is false. The slices must keep waiting (no early "finished" with an empty reply); the
        # turn then runs, done increments and the reply comes back.
        class LateDesk:
            def __init__(self):
                self.t = 0.0
                self.done = 0
                self.reply = ""
                self.cmds = []

            def clock(self):
                return self.t

            def vm(self, cmd):
                self.cmds.append(cmd)
                if cmd == "llmos desk-state":
                    return json.dumps({"screen": "desk", "busy": False, "reply": self.reply, "queued": 0,
                                       "done": self.done, "dialogs": [], "windows": [], "apps": []})
                if cmd.startswith("llmos desk-ctl wait"):
                    self.t += int(cmd.split()[3])
                    if self.t >= 7 and self.done == 0:
                        self.done, self.reply = 1, "Canberra"
                    return json.dumps({"busy": False, "reply": self.reply, "screen": "desk", "done": self.done})
                return "ok"

        late = LateDesk()
        rec = realrun.run_task(dict(reply_task("ap-late"), approve=True), FakeUser(), late.vm,
                               clock=late.clock, outdir=outroot, sleep=no_sleep)
        late_waits = [c for c in late.cmds if c.startswith("llmos desk-ctl wait")]
        check("approve, line reaches desk after 7 s -> keeps waiting, PASS with the reply",
              rec["verdict"] == "PASS" and len(late_waits) == 2 and late.done == 1,
              json.dumps({k: rec[k] for k in ("verdict", "reason")}) + repr(late_waits))

        print("ok approve: one/none/two asks, timeout reboots; type error reboots next task; late line keeps waiting")
    finally:
        shutil.rmtree(outroot, ignore_errors=True)

    if FAILS:
        print("FAILED: %s" % ", ".join(FAILS))
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
