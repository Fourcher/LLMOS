#!/usr/bin/env python3
"""End-to-end test of the real agent loop against a live llama-server, on the
Mac, before baking the image. Uses a headless ctx and a temp HOME/ETC so it
touches nothing real. Runs the actual agent.py -> llm.py -> tools.py path."""
import json
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..", "src", "rootfs", "usr", "lib", "llmos")
sys.path.insert(0, os.path.abspath(ROOT))

tmp = tempfile.mkdtemp(prefix="llmos-smoke-")
os.environ.update(LLMOS_HOME=os.path.join(tmp, "home"), LLMOS_ETC=os.path.join(tmp, "etc"),
                  LLMOS_LIB=os.path.join(tmp, "lib"), LLMOS_RUN=os.path.join(tmp, "run"),
                  LLMOS_SHARE=os.path.abspath(os.path.join(ROOT, "..", "..", "share", "llmos")),
                  LLMOS_LLAMA_URL=os.environ.get("LLMOS_LLAMA_URL", "http://127.0.0.1:8080"))
os.makedirs(os.environ["LLMOS_HOME"], exist_ok=True)

from llmos import agent, config, tools  # noqa: E402

config.settings.set("autonomy", "hands-off")
config.settings.set("internet", "yes")
config.settings.set("onboarded", True)


class Ctx:
    headless = False  # allow interactive-flagged tools to still be captured
    def __init__(self): self.after_turn=None; self.calls=[]; self.buf=""
    def new_stream(self): return None
    def on_text(self, s, t): self.buf += t
    def end_stream(self, s): pass
    def status(self, t): pass
    def begin_tool(self, tool, args, risk): self.calls.append((tool.name, args)); print(f"    · {tool.name} {json.dumps(args, ensure_ascii=False)[:90]}")
    def end_tool(self, tool, result): pass
    def progress(self,*a): pass
    def background(self, fn): pass
    def confirm_network(self, n, a): return True
    def confirm_action(self, t, a, r): return True
    def interactive(self, cmd): return 0
    def redraw(self): pass
    def show_panel(self, p): self.calls.append(("__panel__", p))
    def display(self, t): pass


CASES = [
    ("what can you do?", None),
    ("make everything purple", "set_appearance"),
    ("no sharp corners, round everything", "set_appearance"),
    ("put the settings in Chinese but keep everything else English", "set_appearance"),
    ("how much disk space is free?", "run_command"),
    ("what's 4823 times 971?", "calculate"),
    ("remember that I prefer metric units", "remember"),
    ("every weekday at 8am give me a summary of my day", "schedule_task"),
    ("turn the brightness up to 70", "set_brightness"),
    ("switch to hands-on mode", "change_setting"),
    ("write a file /tmp/hello.txt that says hi", "write_file"),
    ("show me the settings screen", "show_panel"),
]

def main():
    from llmos import llm
    if not llm.wait_ready(120):
        print("model server not reachable at", config.LLAMA_URL); sys.exit(1)
    passed = 0
    for prompt, expect in CASES:
        ctx = Ctx()
        hist = []
        print(f"\n>>> {prompt}")
        final = agent.run(ctx, prompt, hist)
        names = [c[0] for c in ctx.calls]
        ok = (expect is None and not names) or (expect in names)
        passed += ok
        print(f"    reply: {final[:120]!r}")
        print(f"    [{'PASS' if ok else 'FAIL'}] tools={names} (wanted {expect})")
    print(f"\n{passed}/{len(CASES)} cases passed")
    # verify side effects really happened
    from llmos import store
    print("memory:", [f['fact'] for f in store.facts()])
    print("tasks:", [t['desc'] for t in store.tasks()])
    print("appearance:", config.settings.get("appearance"))
    print("autonomy:", config.settings.get("autonomy"))
    print("hello.txt:", open("/tmp/hello.txt").read().strip() if os.path.exists("/tmp/hello.txt") else "(missing)")

if __name__ == "__main__":
    main()
