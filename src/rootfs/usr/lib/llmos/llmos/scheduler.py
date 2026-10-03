"""Background worker: runs scheduled tasks when due and drops the result in the
owner's inbox, ends timed focus sessions, all with no user present. This is how
the OS 'does things on its own' -- the promise from the brief that you can say
'every morning give me the weather' and then forget about it.

It runs as root but only starts working once the vault (if any) is unlocked,
because tasks and their results live inside it."""
import json
import re
import time

from . import agent, config, llm, store, system, vault, i18n


class HeadlessCtx:
    """A ctx with no screen: tool output is captured, nothing is drawn, and
    anything that would need the owner is treated as declined (a background
    task must never block waiting for someone)."""
    headless = True

    def __init__(self):
        self.after_turn = None
        self.log = []

    def new_stream(self):
        return None

    def on_text(self, stream, text):
        pass

    def end_stream(self, stream):
        pass

    def status(self, text):
        self.log.append(text)

    def begin_tool(self, tool, args, risk):
        self.log.append(f"{tool.name} {json.dumps(args, ensure_ascii=False)[:120]}")

    def end_tool(self, tool, result):
        pass

    def progress(self, phase, done, total):
        pass

    def background(self, fn):
        try:
            fn()
        except Exception:
            pass

    def confirm_network(self, name, args):
        return config.settings.get("internet") == "yes"

    def confirm_action(self, tool, args, risk):
        # unattended: only auto-run what hands-off would; never destructive
        from . import tools
        return risk not in (tools.DESTRUCTIVE, tools.SECURITY)

    def interactive(self, cmd):
        return 127

    def redraw(self):
        pass

    def show_panel(self, panel):
        pass

    def show_box(self, title, rows):
        self.log.append(title + ": " + " / ".join(rows))

    def show_ui(self, spec):
        from . import uispec
        norm = uispec.normalize(spec)
        if norm:
            self.log.append(norm["title"] + ": " + " / ".join(uispec.to_rows(norm)))

    def display(self, text):
        pass

    def display(self, text):
        pass


_REMIND = re.compile(r"^\s*remind me(?:\s*[:,]\s*|\s+(?:to|that|about)\s+)(?P<what>.+?)\s*$", re.I | re.S)
_TIMER = re.compile(r"^\s*tell me that my (?P<what>.+?) timer is done\b", re.I)


def direct_result(task):
    """A reminder or a timer is delivered word for word (no model, no embellishment)."""
    m = _TIMER.match(task)
    if m:
        return i18n.t("d_timer_up", what=m.group("what"))
    m = _REMIND.match(task)
    if m:
        what = m.group("what").strip().rstrip(".")
        return f"{i18n.t('d_reminder')}: {what}"
    return None


def run_task(t):
    direct = direct_result(t["task"])
    if direct:
        store.finished(t["id"], direct)
        store.notify(direct[:80], direct)
        return direct
    ctx = HeadlessCtx()
    instruction = (f"This is a scheduled task running in the background with no one watching. "
                   f"Task: {t['task']}\n\nComplete it now and give a short result the owner can read later. "
                   f"Use web_search for anything current or numeric rather than inventing it; if the task "
                   f"needs an action that can't run unattended, say what you couldn't do.")
    try:
        result = agent.run(ctx, instruction, [])
    except llm.ModelDown as e:
        result = f"(couldn't run: the model was unavailable: {e})"
    except Exception as e:
        result = f"(couldn't run: {e})"
    store.finished(t["id"], result)
    store.notify(f"Scheduled: {t['task'][:60]}", result or "(no result)")
    return result


def tick():
    system.apply_timezone_env()  # the owner may have changed the zone since we started
    if config.settings.get("vault") and not vault.unlocked():
        return  # tasks live in the vault; wait until it's open
    if system.focus_tick():
        store.notify("Focus mode ended", "Social media and feeds are reachable again.")
    for t in store.due():
        if not llm.health():
            break
        run_task(t)


def main():
    # wait for the model once at startup so the first task isn't skipped
    llm.wait_ready(900)
    while True:
        try:
            tick()
        except Exception:
            pass
        time.sleep(20)


if __name__ == "__main__":
    main()
