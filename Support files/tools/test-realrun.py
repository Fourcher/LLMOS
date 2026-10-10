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


def main():
    test_no_args_no_boot()
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
        check("vm_text: line merely containing vmctl is kept",
              realrun.vm_text("see [vmctl: matched after 1.0s] in text\n[vmctl: matched after 1.0s]\n")
              == "see [vmctl: matched after 1.0s] in text",
              repr(realrun.vm_text("see [vmctl: matched after 1.0s] in text\n[vmctl: matched after 1.0s]\n")))
        check("vm_text: TIMEOUT trailer with output -> None",
              realrun.vm_text("partial\n[vmctl: TIMEOUT after 30.4s]\n") is None)
        check("vm_text: non-string -> None", realrun.vm_text(None) is None)
        check("vm_text: no trailer strips trailing whitespace",
              realrun.vm_text("Canberra  \n\n") == "Canberra", repr(realrun.vm_text("Canberra  \n\n")))
        print("ok vm_text trailer removal, TIMEOUT -> None, multi-line kept")

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
    finally:
        shutil.rmtree(outroot, ignore_errors=True)

    if FAILS:
        print("FAILED: %s" % ", ".join(FAILS))
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
