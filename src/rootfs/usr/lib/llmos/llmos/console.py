"""The console: the whole user-facing interface. First-run onboarding, the
vault unlock screen, the main talk-to-your-computer loop, the built-in panels,
and the confirmation prompts the autonomy policy raises."""
import os
import select
import signal
import sys
import termios
import threading
import time

from . import agent, config, i18n, llm, media, models, store, system, ui, vault, voice, version_line

try:
    import readline  # noqa: F401  (enables line editing + history in input())
except ImportError:
    readline = None

T = i18n.t


# --------------------------------------------------------------- ctx

class ConsoleCtx:
    """Bridges the agent to this terminal: streaming, tool feedback,
    confirmations, panels."""
    headless = False

    def __init__(self, console):
        self.c = console
        self.after_turn = None
        self._net_ok = set()

    def setup_vault(self):
        """"set up a passphrase" after first boot: the same prompt the console used at onboarding."""
        self.c._setup_vault()

    def new_stream(self):
        return ui.Stream()

    def on_text(self, stream, text):
        stream.feed(text)

    def end_stream(self, stream):
        stream.end()

    def status(self, text):
        ui.status(text)

    def begin_tool(self, tool, args, risk):
        ui.status(self.c.describe_tool(tool, args))

    def end_tool(self, tool, result):
        pass

    def progress(self, phase, done, total):
        self.c.progress(phase, done, total)

    def background(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def confirm_network(self, name, args):
        host = args.get("url", "") or args.get("query", "")
        if name in self._net_ok:
            return True
        ok = self.c.ask_yes_no(f"{T('s_internet')}: {name} → {str(host)[:60]}?")
        if ok:
            self._net_ok.add(name)
        return ok

    def confirm_action(self, tool, args, risk):
        return self.c.ask_yes_no(self.c.describe_tool(tool, args, confirm=True), danger=risk in ("destructive", "security"))

    def confirm_online(self, text, reason):
        """'ask' brain mode: one question before a request leaves this computer."""
        label = llm.cloud_label()
        why = T("d_online_failed") if reason == "failed" else T("d_online_big")
        return self.c.ask_yes_no(f"{why} {T('d_online_title', model=label)} {T('d_online_shares')}")

    def brain(self, online, label):
        pass          # the activity line (agent.run) already says when an answer comes from the online model

    def expect(self, seconds, step):
        if seconds >= 20 and step == 0:
            self.status(agent.about_time(seconds))

    def setup_cloud(self, provider=None):
        return ("From this console, say it in one line, for example: \"set up the online model: provider claude, "
                "model claude-opus-5-5, key sk-ant-…\" or \"… provider openai, url https://…/v1, model NAME, key …\". "
                "The key is checked with one tiny request and kept inside the vault. On the desk a form opens instead.")

    def setup_connector(self):
        return ("From this console, say it in one line, e.g.: \"add a connector named files that runs 'npx -y "
                "@modelcontextprotocol/server-filesystem /root'\" or \"add a connector named api at https://…/mcp\". "
                "On the desk a form opens instead.")

    def edit_conduct(self):
        return ("The conduct section of the assistant's own instructions is the plain-text file "
                "/etc/llmos/conduct.txt. Open it in an editor (say 'open a terminal', then `nano "
                "/etc/llmos/conduct.txt`); whatever it holds replaces the built-in conduct. Delete the file to "
                "return to the default. This is the one part of the system prompt you control. On the desk an "
                "editor opens instead.")

    def interactive(self, cmd):
        return self.c.run_interactive(cmd)

    def redraw(self):
        self.c.redraw()

    def show_panel(self, panel):
        self.c.panel(panel)

    def show_box(self, title, rows):
        ui.box(title, rows)
        ui.blank()

    def show_ui(self, spec):
        """A generated window, drawn as a framed box on this text console."""
        from . import uispec
        norm = uispec.normalize(spec)
        if norm:
            ui.box(norm["title"], uispec.to_rows(norm))
            ui.blank()

    def display(self, text):
        ui.write(ui.theme.base())
        for line in text.splitlines():
            ui.write("  " + line + ui.theme.base() + "\033[K\n")


# --------------------------------------------------------------- console

class Console:
    def __init__(self, headless_login=False):
        self.ctx = ConsoleCtx(self)
        self.history = []
        self.stop_flag = threading.Event()

    # ---- low-level input helpers

    def _raw_line(self, prompt, secret=False):
        """A single line, drawn in the theme. Secret hides typing (passphrase)."""
        ui.write(ui.theme.base())
        if secret:
            return self._read_secret(prompt)
        try:
            return input(prompt)
        except EOFError:
            raise
        return ""

    def _read_secret(self, prompt):
        ui.write(prompt)
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            new = termios.tcgetattr(fd)
            new[3] &= ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSADRAIN, new)
            line = sys.stdin.readline()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        ui.write("\n")
        return line.strip()

    def ask_yes_no(self, question, default=False, danger=False):
        ui.blank()
        ui.line(question, style="err" if danger else "accent")
        suffix = "[y/N]" if not default else "[Y/n]"
        try:
            ans = self._raw_line(ui.theme.base() + "  " + suffix + " ").strip().lower()
        except EOFError:
            return default
        if not ans:
            return default
        return ans[0] in ("y", "o", "s", "j", "d")  # yes/oui/sí/ja/da

    # ---- tool descriptions (transparency)

    def describe_tool(self, tool, args, confirm=False):
        n = tool.name
        if n == "run_command":
            c = args.get("command", "")
            return (f"run: {c}" if not confirm else f"Run this command?\n  {c}")
        if n == "install_app":
            return f"install {args.get('packages','')}"
        if n == "write_file":
            return f"write {args.get('path','')}" if not confirm else f"Write to {args.get('path','')}?"
        if n == "web_search":
            return f"search the web: {args.get('query','')}"
        if n == "read_webpage":
            return f"read {args.get('url','')}"
        if n == "manage_models":
            return f"models: {args.get('action','')} {args.get('model','')}"
        if n == "system_power":
            return f"{args.get('action','')} the computer?" if confirm else f"{args.get('action','')}…"
        if n == "change_setting":
            return f"change {args.get('setting','')} → {args.get('value','')}"
        if n == "set_appearance":
            return "change the look"
        if n == "play_media":
            return f"play: {args.get('query','')}"
        # default: name + short args
        import json
        a = json.dumps(args, ensure_ascii=False)
        a = a if len(a) < 60 else a[:57] + "…"
        return f"{n} {a}" if not confirm else f"Allow {n} {a}?"

    def progress(self, phase, done, total):
        pct = int(done * 100 / total) if total else 0
        bar = "█" * (pct // 4) + "░" * (25 - pct // 4)
        label = {"download": "downloading", "verify": "verifying"}.get(phase, phase)
        # time left, from the average rate since this phase began (no extra measuring)
        now = time.time()
        p = getattr(self, "_prog", None)
        if not p or p[0] != phase or done < p[2]:
            self._prog = p = (phase, now, done)
        left = ""
        if now - p[1] >= 3 and done > p[2] and total > done:
            rate = (done - p[2]) / (now - p[1])
            left = "  " + agent.about_time((total - done) / rate, left=True)
        ui.write(f"\r{ui.theme.base()}  {ui.theme.dim()}{label} {bar} {pct}%  {done//1048576}/{total//1048576} MB{left}{ui.theme.base()}\033[K")
        if done >= total:
            self._prog = None
            ui.write("\n")

    def redraw(self):
        ui.paint()
        self.banner()

    def display_reply_voice(self, text):
        if text and config.settings.get("speak_replies"):
            voice.speak(text)

    # ---- screens

    def banner(self):
        s = config.settings.all()
        ui.line(f"LLM OS", style="accent")
        m = models.active()
        sub = m["name"] if m else T("model_down")
        extras = []
        if models.host_mode():
            extras.append("host GPU")
        if s.get("tor"):
            extras.append("Tor")
        if s.get("vault"):
            extras.append("🔒" if vault.unlocked() else "locked")
        if s.get("focus", {}).get("on"):
            extras.append(T("s_focus"))
        ui.line(f"{sub} · {s['autonomy']}" + (" · " + " · ".join(extras) if extras else ""), style="dim")
        ui.blank()

    def show_unseen(self):
        un = store.unseen()
        if not un:
            return
        rows = []
        for m in un[-6:]:
            rows.append(f"{m['title']}")
            rows.append("  " + ui.strip(m["text"])[:900])
        ui.box(T("while_away"), rows)
        store.mark_seen([m["id"] for m in un])
        ui.blank()

    # ---- onboarding

    def onboard(self):
        ui.paint()
        ui.line("LLM OS", style="accent")
        ui.blank()
        ui.line(T("welcome"))
        ui.blank()
        # language first, so the rest of onboarding is localized
        lang = self._raw_line(ui.theme.base() + "  " + T("ask_language") + " [English] ").strip()
        if lang:
            config.settings.set("language", i18n.display_name(lang))
            if i18n.lang_code(lang) not in i18n.BUILTIN:
                ui.status(T("loading_model"))
                i18n.table_for(lang)
        ui.blank()
        name = self._raw_line(ui.theme.base() + "  " + T("ask_name") + " ").strip()
        if name:
            config.Profile().set("name", name)

        ui.blank()
        cur_tz = system.timezone()
        tz = self._raw_line(ui.theme.base() + "  " + T("ask_timezone") + f" [{cur_tz}] ").strip()
        if tz:
            try:
                system.set_timezone(tz)
            except ValueError as e:
                ui.line(f"{T('error')}: {e}", style="err")

        ui.blank()
        ui.line(T("ask_autonomy"), style="accent")
        ui.line("1. " + T("v_hands-off"))
        ui.line("2. " + T("v_balanced"))
        ui.line("3. " + T("v_hands-on"))
        pick = self._raw_line(ui.theme.base() + "  [1] ").strip() or "1"
        config.settings.set("autonomy", {"1": "hands-off", "2": "balanced", "3": "hands-on"}.get(pick, "hands-off"))

        ui.blank()
        if self.ask_yes_no(T("ask_internet"), default=True):
            config.settings.set("internet", "yes")
            if self.ask_yes_no(T("ask_tor"), default=False):
                ui.status(T("loading_model"))
                system.set_tor(True)
        else:
            config.settings.set("internet", "no")
        system.apply_firewall()

        ui.blank()
        self._setup_vault()

        config.settings.set("onboarded", True)
        store.remember(f"set up LLM OS on {time.strftime('%Y-%m-%d')}")
        ui.blank()
        ui.line(T("onboard_done"), style="accent")
        ui.blank()

    def _setup_vault(self):
        try:
            p1 = self._raw_line(ui.theme.base() + "  " + T("ask_passphrase") + "\n  " + T("passphrase") + ": ", secret=True)
        except EOFError:
            return
        if not p1:
            return
        p2 = self._raw_line(ui.theme.base() + "  " + T("ask_passphrase_again") + ": ", secret=True)
        if p1 != p2:
            ui.line(T("passphrase_mismatch"), style="err")
            return self._setup_vault()
        ui.status(T("creating_vault"))
        try:
            vault.create(p1)
        except vault.VaultError as e:
            ui.line(f"{T('error')}: {e}", style="err")

    def unlock_screen(self):
        ui.paint()
        ui.line("LLM OS", style="accent")
        ui.line(T("locked"), style="dim")
        ui.blank()
        for _ in range(5):
            try:
                p = self._raw_line(ui.theme.base() + "  " + T("passphrase") + ": ", secret=True)
            except EOFError:
                return False
            if not p:
                continue
            ui.status(T("unlocking"))
            if vault.unlock(p):
                return True
            ui.line(T("wrong_passphrase"), style="err")
        return False

    # ---- panels

    def panel(self, which):
        {"settings": self.panel_settings, "models": self.panel_models,
         "tasks": self.panel_tasks, "memory": self.panel_memory,
         "audit": self.panel_audit, "help": self.panel_help}.get(which, self.panel_help)()

    def panel_help(self):
        ui.box("LLM OS", [T("help_1"), "", T("help_2"), T("help_3")])
        ui.blank()

    def panel_settings(self):
        s = config.settings.all()
        L = lambda k: T(k, area="settings")
        V = lambda k: T(k, area="settings")
        rows = [
            f"{L('s_autonomy')}: {V('v_' + s['autonomy'])}",
            f"{L('s_internet')}: {V('v_' + {'yes':'yes','ask':'ask','no':'no'}[s['internet']])}"
            + (f" · {L('s_tor')}: {V('v_on') if s['tor'] else V('v_off')}"),
            f"{L('s_model')}: {(models.active() or {}).get('name', '—')}"
            f" · {L('s_timezone')}: {system.timezone()}",
            f"{L('s_language')}: {s['language']}" + (f" · {L('s_settings_language')}: {s['settings_language']}" if s['settings_language'] else ""),
            f"{L('s_color')}: {s['appearance']['color'] or V('v_default')}"
            f" · {L('s_background')}: {s['appearance']['background'] or V('v_default')}"
            f" · {L('s_corners')}: {V('v_' + s['appearance']['corners']) if s['appearance']['corners'] in ('rounded','square','none') else s['appearance']['corners']}",
            f"{L('s_voice')}: {V('v_on') if s['speak_replies'] else V('v_off')}"
            f" · {L('s_vault')}: {V('v_on') if s['vault'] else V('v_off')}"
            f" · {L('s_focus')}: {V('v_on') if s.get('focus',{}).get('on') else V('v_off')}",
            f"{L('s_version')}: {version_line()}",
        ]
        ui.box(L("settings"), rows)
        ui.line(L("s_change_hint"), style="dim")
        ui.blank()

    def panel_models(self):
        cur = models.active()
        rows = []
        for m in models.catalog():
            mark = "●" if cur and m["id"] == cur["id"] else "○" if m in models.installed() else " "
            tag = T("active") if cur and m["id"] == cur["id"] else T("installed") if m in models.installed() else f"{m['size']/1e9:.1f} GB"
            rows.append(f"{mark} {m['name']} · {m['maker']} · {tag}")
        rows.append("")
        rows.append(f"RAM {models.ram_gb():.1f} GB · " + 'say "use ministral 8b" or "download gemma 12b"')
        ui.box(T("models"), rows)
        ui.blank()

    def panel_tasks(self):
        ts = store.tasks()
        rows = [f"[{t['id']}] {t['desc']} — {t['task']}" for t in ts] or [T("no_tasks")]
        ui.box(T("tasks"), rows)
        ui.blank()

    def panel_memory(self):
        facts = store.facts()
        rows = [f"· {f['fact']}" for f in facts] or [T("no_memory")]
        ui.box(T("memory"), rows)
        ui.blank()

    def panel_audit(self):
        rows = []
        for r in store.audit_tail(15):
            mark = "" if r["allowed"] else "✗ "
            rows.append(f"{r['ts'][11:]} {mark}{r['tool']}: {ui.strip(str(r['result']))[:80]}")
        ui.box(T("audit"), rows or [T("no_audit")])
        ui.blank()

    # ---- interactive passthrough (editors, htop, games)

    def run_interactive(self, cmd):
        ui.reset()
        ui.write("\033[2J\033[H")
        sys.stdout.flush()
        env = dict(os.environ, HOME=config.home(), TERM=os.environ.get("TERM", "xterm-256color"))
        rc = os.system(f"cd {config.home()!r} && {cmd}")
        self.redraw()
        return rc >> 8 if rc >= 256 else rc

    # ---- voice

    def voice_turn(self):
        if not voice.available():
            ui.line(T("no_mic"), style="dim")
            return None
        ui.status(T("listening"))
        wav = voice.listen()
        if wav is None:
            ui.line(T("no_mic"), style="dim")
            return None
        if not wav:
            ui.line(T("stopped"), style="dim")
            return None
        text = voice.transcribe(wav)
        if text:
            ui.line(f"{T('heard')}: {text}", style="dim")
        return text or None

    # ---- shortcuts

    def shortcut(self, line):
        low = line.lower().strip()
        if low in ("settings", "models", "tasks", "memory", "audit", "help", "?"):
            self.panel("help" if low == "?" else low)
            return True
        if low == "clear":
            self.history.clear()
            self.redraw()
            return True
        if low in ("lock",) and config.settings.get("vault"):
            try:
                media.stop()
            except Exception:
                pass
            try:
                vault.lock()
            except Exception as e:
                ui.line(f"{T('lock_failed')} ({e})", style="err")
            if not self.unlock_screen():
                self.shutdown("poweroff")
            self.redraw()
            return True
        if low in ("voice", "listen", "🎤"):
            text = self.voice_turn()
            if text:
                self.turn(text)
            return True
        if low in ("shutdown", "poweroff", "halt"):
            self.shutdown("poweroff")
            return True
        if low in ("reboot", "restart"):
            self.shutdown("reboot")
            return True
        if line.startswith("!"):  # !cmd -> run a shell command directly
            self.ctx.after_turn = None
            self.run_interactive(line[1:].strip() or "sh")
            return True
        return False

    # ---- main turn

    def turn(self, text):
        self.ctx.after_turn = None
        old = signal.signal(signal.SIGINT, self._interrupt)
        try:
            final = agent.run(self.ctx, text, self.history)
            self.display_reply_voice(final)
        except llm.ModelError as e:
            ui.line(f"{T('error')}: {e}", style="err")
        except llm.ModelDown:
            ui.line(T("model_down"), style="err")
        except agent.Cancelled:
            ui.line(T("stopped"), style="dim")
        except Exception as e:
            ui.line(f"{T('error')}: {e}", style="err")
        finally:
            signal.signal(signal.SIGINT, old)
        if self.ctx.after_turn:
            self.shutdown(self.ctx.after_turn)
        ui.blank()

    def _interrupt(self, *_):
        raise agent.Cancelled()

    def shutdown(self, how):
        ui.line(T("shutting_down") if how == "poweroff" else T("restarting"), style="accent")
        if config.settings.get("vault") and vault.unlocked():
            vault.lock()
        os.system("poweroff" if how == "poweroff" else "reboot")
        sys.exit(0)

    # ---- model readiness

    def ensure_model(self):
        if llm.health():
            return True
        ui.status(T("loading_model"))
        spin = "|/-\\"
        i = 0
        start = time.time()
        while not llm.health():
            if time.time() - start > 900:
                return False
            ui.write(f"\r{ui.theme.base()}  {ui.theme.dim()}{T('loading_model')} {spin[i % 4]}{ui.theme.base()}\033[K")
            i += 1
            time.sleep(0.5)
        ui.write("\r\033[K")
        return True

    def warm_up(self):
        """Pre-process the static prompt while the owner reads the banner."""
        threading.Thread(target=agent.warm_up, daemon=True).start()

    # ---- run loop

    def _desk_alive(self):
        """Is the graphical desk running on the screen? Then set-up and
        unlocking happen there, and this text console just waits."""
        try:
            with open(os.path.join(config.RUN, "desk.pid")) as f:
                os.kill(int(f.read().strip()), 0)
            return True
        except (OSError, ValueError):
            return False

    def _wait_for_desk(self, what):
        """Wait for set-up / unlocking to happen on the screen; Enter here
        takes over and does it on this console instead."""
        ui.line(what, style="dim")
        ui.line(T("take_over"), style="dim")
        while self._desk_alive():
            if config.settings.get("onboarded") and (not config.settings.get("vault") or vault.unlocked()):
                return True
            try:
                r, _, _ = select.select([sys.stdin], [], [], 2)
            except (OSError, ValueError):
                time.sleep(2)
                continue
            if r:
                sys.stdin.readline()
                return False
        return False

    def _locked_elsewhere(self):
        """The vault was locked by another session while this console was open: nothing typed here runs until
        the passphrase is given here too."""
        if not (config.settings.get("vault") and not vault.unlocked()):
            return False
        self.history.clear()
        if not self.unlock_screen():
            self.shutdown("poweroff")
        self.redraw()
        return True

    def run(self):
        ui.query_size()
        ui.reload_theme()
        system.apply_timezone_env()
        if self._desk_alive() and (not config.settings.get("onboarded") or
                                   (config.settings.get("vault") and not vault.unlocked())):
            self._wait_for_desk(T("screen_hint"))
        if config.settings.get("vault") and not vault.unlocked():
            if not self.unlock_screen():
                self.shutdown("poweroff")
        if not config.settings.get("onboarded"):
            self.ensure_model()
            self.warm_up()
            self.onboard()
        else:
            self.redraw()
            self.ensure_model()
            self.warm_up()
        while True:
            ui.query_size()
            if self._locked_elsewhere():
                continue
            self.show_unseen()  # results of background tasks, as they arrive
            try:
                line = input(ui.prompt_str())
            except EOFError:
                ui.blank()
                break
            except KeyboardInterrupt:
                ui.write("\n")
                continue
            line = line.strip()
            if self._locked_elsewhere():   # the desk (or the automatic lock) locked while this prompt waited
                continue
            if not line:
                continue
            if self.shortcut(line):
                continue
            self.turn(line)


def main():
    console = Console()
    try:
        console.run()
    finally:
        ui.reset()


if __name__ == "__main__":
    main()
