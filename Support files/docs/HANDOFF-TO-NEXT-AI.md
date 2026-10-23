# LLM OS — Handoff for the next developer (AI or human)

Everything needed to pick up this project and keep going. Written to be self-contained. Where a verbatim original
is not in hand, that is said plainly rather than invented.

---

## 0. The mandate (reconstructed, not verbatim)

The literal first prompt isn't preserved in the current working context (the session was compacted). This is a
faithful reconstruction from the whole build history; if the owner has the original text, it belongs at the top of
this section word-for-word.

**Build LLM OS: an operating system whose entire interface is an on-device AI assistant.** You talk to the computer
in plain language and it runs the machine for you. It runs on the device (local model), works offline, keeps
everything private (no telemetry, no account, nothing phones home), and treats the **owner as the highest
authority**. It should be genuinely capable, not a toy, and over time able to improve and extend itself.

## 1. The owner's corrections and principles — the "alterations" to the mandate, most load-bearing first

These are the course-corrections the owner gave repeatedly. Treat them as binding.

1. **Safety = Asimov's three laws, and nothing more.** The First Law means *physical harm to a human being* — NOT
   property, computers, money, feelings, or taste. The only hard stops for the on-device assistant: don't help cause
   physical harm to a person, and never produce sexual content involving anyone under 18. Everything else is allowed.
2. **The owner is the highest authority.** Opt-in full trust asks nothing. Never nag, never refuse the owner on
   ordinary, non-dangerous tasks. Protections are disclosed, opt-out defaults — not gates.
3. **Uncensored by design.** The on-device model must not moralize or second-guess the owner. Refusals seen early
   were a small model buckling under a tool-heavy prompt, not the rules — fixed with uncensored models + auto-escalation.
4. **Capable over quick when it matters.** Tiered models: do quick things fast, hand hard/refused ones to a stronger
   or uncensored model automatically.
5. **Do everything yourself; verify end to end.** "It answered" is not a pass — verify on the real screen. Resolve
   every issue found before reporting; never leave things "still open."
6. **Minimal friction for the person.** Plain words, discrete controls, numbers with context, nothing hard to type,
   never assume anything about the target computer.
7. **Integrate the owner's shared links if free and helpful** — build it in, don't just assess.
8. **The laptop is the real target**, not a VM. Test on the physical machine. (Dev was repeatedly confused between
   the Mac's in-app browser / a VM and the real laptop — always act on the laptop.)
9. **This machine is a development machine** — its security rules can be relaxed (e.g., the API key persists, full
   trust is on).

## 2. What LLM OS is — the pillars

1. **The assistant is the whole interface.** Plain language runs the machine; no app/desktop maze.
2. **On-device and private.** Local model, offline-capable, no telemetry, no account.
3. **Owner-sovereign and uncensored.** Does what the owner asks; protections few, disclosed, opt-out; Asimov-only line.
4. **Capable when it counts.** Escalates across models; can borrow a bigger model over the owner's own network or use
   a free online one.
5. **Self-extending.** Makes its own email to read verification codes, passes notes to other people's AIs (MPR),
   borrows a bigger brain, and works on its own code behind a test gate.

## 3. Architecture & where things live

- Alpine Linux (musl), labwc + a GTK4/WebKitGTK "desk", a local `llama-server`, OTA updates signed with Ed25519.
- Code: `Support files/src/rootfs/usr/lib/llmos/llmos/*.py` (the OS). Key modules:
  - `desk.py` (the UI/controller), `agent.py` (the turn loop, tool execution, **refusal auto-escalation**),
    `tools.py` (the tool registry), `intent.py` (fast-path phrase → tool), `llm.py` (local + online model calls,
    `CLOUD_PROVIDERS`), `config.py` (settings, vault, `cloud()` account), `models.py` (catalog, install, GPU offload),
    `web.py` (search + Wikipedia fallback), `mail.py` (owner IMAP/SMTP), `devmail.py` (the computer's own mailbox),
    `mcp.py` (connectors incl. MPR), `scheduler.py`, `store.py`, `system.py`, `devaccess.py`/`devlink.py` (remote dev).
- Dev tools: `Support files/tools/` — `ota.py` (publish), `devssh.py` / `devlink.py` (drive the laptop),
  `run-host-tests.sh` (**needs bash**, runs `tools/test-*.py`), `brain.py` (lend a Mac model), `selfdev.py` (self-patching).
- Docs: `Support files/docs/PROJECT-CONTEXT.md` (shorter context), `OTA.md`, this file.

## 4. Current state — built and working (as of ~v1.8.9.77, 2026-10-23)

- **Models / refusals.** On-device default is an uncensored model (Dolphin 3.0 8B; Huihui Ornith 1.5 9B for more
  reasoning; Ministral 3 14B downloaded as the strongest local coder). A timid refusal or authorization hedge
  **auto-escalates** (agent.py): re-run on a more capable model — online if set up, else a stronger uncensored local
  one; chains (local → online → stronger local), never twice. Genuinely harmful asks (violence to a person, CSAM)
  keep the refusal.
- **Home brain** (`tools/brain.py`): a Mac lends its GPU model to the laptop over the owner's own network ("home"
  provider); used while on, the laptop's own model the instant it isn't. (The 9B needs ~65% free Mac RAM.)
- **Online models**: presets for OpenRouter (free; auto-picks the strongest free tool-calling model — currently
  NVIDIA Nemotron 3 Ultra 550B) and Abliteration (paid, uncensored). Sign-in opens the key page; the owner presses
  Copy and the desk auto-ingests the `sk-or-v1-…` key (no typing). **A free *uncensored* coder does not exist online**
  — confirmed across OpenRouter and Chutes — so the setup is a strong free coder + escalation to the uncensored local
  models. The key persists (no vault) → survives restart.
- **MPR** (Meat Proxy Remover): the assistant can pass notes to another person's AI. Off by default; the wake is
  notify-only (never runs the model on an incoming note). KEY safety finding: a headless/scheduled agent task only
  blocks *destructive* commands, not benign writes/reads — so never run the full agent unattended on untrusted input.
- **Web search** falls back to Wikipedia's API when the engines bot-block the laptop.
- **Device email** (`devmail.py`): the computer makes itself a real mailbox (mail.tm) and reads verification codes /
  confirm links, so the owner doesn't copy 2FA codes by hand. (Shared free domains are on disposable blocklists, so
  screened sign-ups reject them — use the owner's real IMAP account for those.)
- **Self-patching loop** (`tools/selfdev.py`, test-gated, NEVER auto-ships): the model proposes SEARCH/REPLACE edits →
  applied to the real files ONLY while the full suite runs, then restored → staged only when the suite ACTUALLY ran
  (a real "N run" summary via bash) and added no failures beyond a clean-tree baseline. `--show` / `--apply` / OTA are
  separate human steps. Deployed on the laptop at `/root/llmos-dev`; uses the laptop's online coder.

## 5. The real walls — hardware/physics, not policy (don't burn effort here)

- **A home laptop cannot be a mail server.** Port 25 blocked both ways (verified on Mac and laptop), no domain/public
  IP/rDNS. Use a mailbox API or the owner's IMAP.
- **Disposable email is blocklisted**, so screened sign-ups (OpenRouter via Clerk, etc.) reject it.
- **Automated third-party logins and CAPTCHAs are a capability wall, not a willingness one.** Filling a Gmail/GitHub
  login and clearing Google's "verify it's you" needs browser automation + bot-evasion that is not built, and the
  providers block automated logins regardless of model. The reliable path: the **owner** does the one login + Copy;
  the device reads codes and does the rest. (This is independent of which AI drives — an uncensored model does not
  change what Google blocks.)
- **The 8–14B local models can't reliably edit code** (measured: Huihui 9B ~3 min/turn, small coders fabricate and
  leak tool-call syntax). Route real code edits to a capable model (home brain or online).
- **Running the full OS test suite ON the laptop is too heavy** — it froze the 16 GB machine during a self-dev run.
  A self-dev loop is naturally a dev-machine job that ships results to the laptop via OTA; if it must run on the
  laptop, give it a *lighter* gate (only tests touching the changed modules + a core subset), not the full 212.
- **The agent's tools are real.** They delete files and touch the network. Test risky prompts only inside a VM, never
  the one real install.

## 6. How to work on it

- Everything under the project folder; never touch personal Mac folders. Host tests only via `tools/run-host-tests.sh`
  (with bash). **Gate every OTA publish on the suite**: redirect its output to a file and chain the publish with `&&`
  (a pipe to `tail` once hid a failure and shipped 4 broken suites).
- The spare x86 laptop (the only real install, 192.168.86.134) is reachable: `tools/devssh.py 'CMD'` and
  `tools/devlink.py` (screenshots/clicks). **Never restart its network services remotely.** Its IP/name can move;
  clients rediscover by key. One VM at a time on the 16 GB Mac.
- Ship with `tools/ota.py publish --version X --restart desk,... --note "…"`; then check `run/ota/reports.jsonl`.

## 7. Open / next

- Bring the laptop back online (it froze during a full-suite self-dev run) and confirm it's healthy — the installed
  OS was not modified (self-dev ran in a separate `/root/llmos-dev` checkout).
- Give `selfdev.py` a lighter gate so it can run on the laptop without exhausting it.
- Decide where self-dev lives long-term: dev machine → OTA to laptop (recommended) vs. on the laptop (slow).
- Optional model follow-ups the owner raised: benchmark a local coder vs the online one; a durable (non-disposable)
  device email via a domain the owner owns.

## 8. One thing to pass along honestly

Most of this project is built and works. The friction in the last stretch was not the OS's capability — it was tasks
that are capability-limited for *any* assistant (third-party logins, CAPTCHAs, autonomous account creation on screened
services) and best done by the owner in seconds, plus the single real-machine prudence of not auto-shipping unreviewed
self-modifications. The OS itself is uncensored and owner-sovereign exactly as specified.
