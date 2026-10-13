#!/usr/bin/env python3
"""Host-side test: the models page's Download / Use / Remove buttons act at once (a toast straight away, the model
tool called directly) and are never queued behind a request the model is still thinking about. Before, their words
went to the model like typed text and nothing visible happened for minutes.
Run: python3 tools/test-model-buttons.py  (exit status 0 = pass)"""
import os
import sys

tools_dir = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(tools_dir), "src/rootfs")
sys.path.insert(0, os.path.join(_ROOT, "usr/lib/llmos"))
os.environ.setdefault("LLMOS_SHARE", os.path.join(_ROOT, "usr/share/llmos"))

from llmos import agent, desk  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(("ok " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


class InlineThread:
    def __init__(self, target=None, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


calls = []
agent.execute = lambda ctx, name, args: calls.append((name, dict(args), ctx.current_request)) or f"{args['action']} done"
agent._shortcut_reply = lambda name, args, out: out
desk.threading.Thread = InlineThread

for words, action, mid in (("download the model qwen3-4b", "download", "qwen3-4b"),
                           ("use the model ministral-3-8b", "use", "ministral-3-8b"),
                           ("remove the model gemma-3-1b", "remove", "gemma-3-1b")):
    d = desk.Desk.__new__(desk.Desk)
    d.ctx = desk.DeskCtx(d)
    d.events, d.queued, d.windows, d.panels = [], [], {"panel-models": {}}, []
    d.emit = d.events.append
    d._enqueue = lambda text, done, chat: d.queued.append(text)
    d.open_panel = d.panels.append
    d._instant = lambda text: (_ for _ in ()).throw(AssertionError("went through the general lane"))
    calls.clear()
    ret = d.act(words)
    toasts = [e["text"] for e in d.events if e.get("t") == "toast"]
    check(f"'{words}' is not queued", d.queued == [] and ret is False, f"queued={d.queued}")
    check(f"'{words}' shows feedback at once", bool(toasts) and mid in toasts[0], f"toasts={toasts}")
    check(f"'{words}' calls the model tool directly", calls == [("manage_models", {"action": action, "model": mid}, words)],
          f"calls={calls}")
    check(f"'{words}' reports the result and refreshes the page", [x.lower() for x in toasts[-1:]] == [f"{action} done"] and d.panels == ["models"],
          f"toasts={toasts} panels={d.panels}")

print("all good" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
