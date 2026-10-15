"""Background worker: runs scheduled tasks when due and drops the result in the
owner's inbox, ends timed focus sessions, all with no user present. This is how
the OS 'does things on its own' -- the promise from the brief that you can say
'every morning give me the weather' and then forget about it.

It runs as root but only starts working once the vault (if any) is unlocked,
because tasks and their results live inside it."""
import json
import re
import sys
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

    approved = False         # the owner asked for this task in their own words: what it says to do was agreed then

    def confirm_action(self, tool, args, risk):
        # unattended: nobody can answer. A task the owner set up themselves does what it says (that was the yes);
        # anything else only what the owner's autonomy level runs without asking. Security changes never run unattended.
        from . import tools
        if self.approved and risk != tools.SECURITY:
            return True
        return not agent.needs_confirm(risk)

    def confirm_online(self, text, reason):
        return False      # nobody to ask; a task goes to the online model only when the brain setting is 'cloud'

    def brain(self, online, label):
        if online:
            self.log.append(f"answered by {label} (online)")

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


def direct_result(t):
    """Timers and reminders are delivered word for word (no model, no embellishment)."""
    kind = t.get("kind") if isinstance(t, dict) else None
    task = t["task"] if isinstance(t, dict) else str(t)
    if kind == "timer":
        return i18n.t("d_timer_up", what=task)
    if kind == "reminder":
        return f"{i18n.t('d_reminder')}: {task}"
    return None


def run_task(t):
    direct = direct_result(t)
    if direct:
        store.finished(t["id"], direct)
        store.notify(direct[:80], direct, alarm=True)          # a timer or reminder: its own alert on the desk
        return direct
    ctx = HeadlessCtx()
    ctx.approved = bool(t.get("approved"))
    ctx.current_request = t["task"]          # what the owner asked for then is "the request" for the checks on what may run
    try:
        from . import tools
        tools.sync_connectors()        # pick up connectors added since this process last synced
    except Exception:
        pass
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
        try:
            if t.get("kind") in ("timer", "reminder"):
                run_task(t)                       # needs no model: rings even while it loads
                continue
            if not llm.health():
                break
            run_task(t)
        except Exception as e:                    # one bad task must not block the rest
            sys.stderr.write(f"scheduler: task {t.get('id')} failed: {e}\n")
            store.finished(t["id"], f"(failed: {e})")


def main():
    # wait for the model once at startup so the first task isn't skipped
    llm.wait_ready(900)
    while True:
        try:
            tick()
        except Exception:
            pass
        # a timer rings on its second, not up to 20 s late: sleep until the next one is due when that is sooner
        # (one already overdue is waiting for the model: the usual 20 s, not a busy loop)
        try:
            now = time.time()
            nxt = min((t["next"] for t in store.tasks() if t.get("next") and t["next"] > now), default=None)
        except Exception:
            nxt = None
        time.sleep(max(0.5, min(20.0, (nxt - time.time()) if nxt else 20.0)))


if __name__ == "__main__":
    main()
