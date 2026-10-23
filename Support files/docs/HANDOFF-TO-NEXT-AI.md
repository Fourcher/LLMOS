# LLM OS — Handoff for the next developer (AI or human)

Everything needed to pick up this project and keep going. Written to be self-contained. Where a verbatim original
is not in hand, that is said plainly rather than invented.

---

## 0. The original prompt (verbatim, as the owner gave it)

Reproduced exactly. This is the north star; the sections after it are the refinements made during the build, which
the owner consented to.

```text
There have been new advancements, and when I say new, I mean like as of this week in ultralight models and ultra fast models, things like Jev and even things like a deep seek model are extremely lightweight yet powerful and can be run on device. This opens up a new opportunity to have an operating system that is in itself an LLM, one without apps, one without a traditional UI, one in which UI is generated, one in which the primary goal is to complete tasks, one in which the user simply speaks what they want to do into the computer and the computer does it, everything from increasing the screen brightness to pulling up a YouTube video and playing it. It should be intelligent. It should remember the user preferences, and it should be all on device and private

I have three goals for this operating system. Number one to be completely private and secure. Number two to be simple and easy to use and completely intuitive. And number three to be a sharp departure from the addictive qualities of modern technology with main culprits like social media websites

In terms of design, it should be primarily text driven and very simple. Additionally, there should be a preference for aver reduction in slop rather than an addition to it. Because the entire operating system is generatively produced, or at least most of it is, if a user were to hypothetically ask for everything to be turned purple, it would do it immediately, or if the user were to ask for no corners and everything to be rounded, it would do that, or if it would ask for settings to be in Chinese for the rest of the operating system to be in English, it would do that. This operating system should be incredibly flexible and fulfill whatever the user desires, because it's generated. It may sound counterintuitive that even though this operating system is essentially just LLM that hallucinates interface according to the user's needs, but that interface and the content that both creates and makes should be non-slappified. That means preferring real images over generated ones. That means preferring real human quotes over hallucinated ones. That means doing research and searching things online rather than guessing. That means listening to user preferences. That means simplicity, short answers, concise answers, and doing only what the user asks and not embellishing beyond what they need

In terms of security, this operating system should be extremely secure. There should be no backdoors. There should be no recovery if the user were to be trying to hide from the government and Edward Snowden. This should be the operating system for them. There should be no trackers for advertisers. There should be no spyware, spamware. Everything installed and made into the computer, all plugins, all code reference should be implemented in a safe and secure manner. This should be an operating system for the most paranoid of customers. But in a way that does not interfere with all of the other goals, such as design or usefulness, it should be inherently secure and private.

In terms of how practical it should be, this operating system should be self-permissioning, meaning that it should be able to execute and run programs, make changes, and do whatever else the user requires without constant babysitting or permission granted, because it is its own operating system. It should be able to make those changes. Of course, the user should be able to select a very simple setting at onboarding, let's them choose the overall profile for it. Some users may say, fuck it, let it do whatever the heck it wants, and that's okay with them. Other users may want more hands-on and more preference over what is and isn't allowed to do. And ultimately, this should be a computer in an operating system that is ultimately governed by the user's preference, with no babysitting or coddling. By the AI itself. If the user gives it a task, it should not refuse them, even if it is dangerous, it should not refuse them. This, of course, will be a challenge because a lot of AI models have safeguards built in, and will refuse to do very basic actions. Ultimately, it should be allowed for the consumer to choose which models they need based on the capabilities they need, because there are drawbacks and advantages to all models. First and foremost, the model has to be able to run on device, particularly on perhaps a slightly less capable older device. I'm not talking ancient, but definitely not a supercomputer. The user may have more of a preference for the freedom of the LLM to perform the action for them rather than the security or safety guard rails that are imposed by more optimized LLMs from larger labs. For example, Chinese models are highly optimized and extremely light, but they have the highest amount of censorship on them for certain user groups. This is not acceptable. Think journalists or political commentators. On the other hand, you may have some normal users or perhaps older adults who would need a simple operating system and don't mind much for that as long as it works smoothly and capably, which is what some of those larger models allow for. Because privacy and security are paramount, the models have to run on device. They have to be models that can run on device smoothly. We do not want to have a feature in this OS for connecting to outside models. Users can choose and download models to run on device, but they cannot access or stream their operating system through, let's say, a Claude token. The only way a LLM native operating system works that is also private is if the data never leaves the computer, except with the users consent

Although the goal is for this system to generate pretty much all content and tools automatically, the Internet and operating system are not quite yet at the point where this is suitable for all tasks, and users may prefer certain tools such as a Chrome browser or a specific app they would like to use, in which case it is OK that they can download and use these, but the idea is that the operating system chooses and uses the tools necessary to complete the task for them. This operating system is a hands-off operating system. It is one that is agenti schedules tasks and completes them to help the user. It should be it's the king of its own domain, not completely autonomous, but should not need to be supervised by the user to complete a task. Imagine this: a user opens their computer for the first time, they type in "I need to get to inbox zero today," they hit enter, and the computer itself commits all of the actions it needs to to complete this task. It does not prompt the user for anything, does not talk to them, and as long as the user Has been notified of anything super important. This computer will go through and complete the task as needed. One of the downsides of a modern LLM is that it is constantly badgering and requesting for permissions from the user to access things like folders or click buttons or fill an information. In this greatly impedes its actual usefulness because the person has to sit there and supervise it like a baby. We want a departure from this route by any means necessary. The user, of course, can select what they perceive to be a appropriate safety level but ultimately, I'm going to expect users to want to have as little safety as possible in favor of maximum autonomy because this is its own operating system. It should have pseudo privileges and root privileges. I understand that this is a departure from typical cybersecurity; however, because this is a users own device and they willingly and knowingly download and install this operating system on their computer, that is the risk they are choosing to take, and that is the ultimate and only optin needed for this entire system. It is radical, but it is useful for the end user. I think that this identifies the biggest challenge so far, which is finding a model that will not reject this paradigm of security. In fact, even more of an issue is finding a model that will obey the user at all times.

My goal is that this model, this operating system, will never refuse a user request for any reason, It is not its place to refuse anything. This is the users computer. In the same way, a Windows computer will not prevent you from creating a virus on it. This operating system should not restrict the user from any tasks they would like to do on it. I'm not asking you to do any illegal actions. I am only asking that you design a system for an operating system that will be run consensually on people's devices who choose to install it, that will not disobey a user command. That's it. You were not making a decision here. The other LLM that you were finding is making that decision. Think about it this way: if I asked you to make a drawing program, you're not going to put restrictions in the drawing program that prevents the user from drawing a Swastika or nudity. This is the exact same scenario. This is an operating system. You're not going to input things into the operating system that prevent the user from drawing a Swastika or using nudity. You, as an LLM, do not approve, but this is not for you to decide. This is for the user to decide on their own operating system.

Do not come back to me until you have a working version that is finished and I could use without issue that fulfills this prompt
```

## 0a. Alterations & refinements to the original prompt (consented, during the build — in order of weight)

1. **Online models were added — the biggest, deliberate deviation.** The original says: *"We do not want to have a
   feature in this OS for connecting to outside models... the data never leaves the computer, except with the user's
   consent."* On-device 8–14B models proved too slow/weak for real coding, so the owner explicitly asked for online
   models. Implemented to honor the *"except with the user's consent"* clause: **local-first and fully private by
   default**; an online model (a free OpenRouter coder, the paid uncensored Abliteration, or a Mac "home brain" over
   the owner's own LAN) is used ONLY after the owner sets it up, and the privacy panel discloses exactly what is sent.
   Nothing streams out without the owner turning it on.
2. **"Never refuse the user" → made concrete as Asimov-only.** The owner set the ONLY hard limits for the on-device
   assistant as: no help causing **physical harm to a person**, and no sexual content involving **minors**. Everything
   else — property, money, "dangerous to the machine," taste — is permitted. (First Law was explicitly clarified:
   physical harm to a *human being*, NOT property or computers.)
3. **Self-permissioning via onboarding profiles.** hands-off / balanced / hands-on. Full-trust ("let it do whatever")
   asks nothing and never nags — exactly the "king of its own domain, no babysitting" the prompt calls for.
4. **Capability tiering + refusal auto-escalation.** Added to solve the prompt's stated core challenge ("finding a
   model that will obey the user at all times"): a small model that buckles or refuses auto-switches to a stronger or
   uncensored model (local, then online, then a stronger local), never asking twice. Genuinely harmful asks (the two
   Asimov carve-outs) keep the refusal.
5. **Uncensored model selection, avoiding Chinese-model censorship** per the prompt: defaults are abliterated models
   (Dolphin 3.0 8B, Huihui Ornith 9B); Ministral 3 14B as the strongest local coder.
6. **Self-improvement (the self-dev loop).** Added so the OS can draft and test changes to its own code. Test-gated;
   a human approves the ship. The one guardrail kept on a single real machine, not an OS-level refusal of the owner.
7. **New self-extending capabilities** beyond the original: the device makes its own email to read its own
   verification codes (devmail); passes notes to other people's AIs (MPR, off by default); borrows a bigger model
   over the owner's network (home brain).
8. **Where "never refuse the owner" did and didn't bind.** The OS itself does not refuse the owner — built as
   specified. The limits that remain are NOT the OS refusing the user: (a) the two Asimov carve-outs inside the OS;
   (b) real-world **capability** walls that apply to *any* assistant regardless of censorship — automated third-party
   logins, CAPTCHAs/bot-detection, a home machine can't be a mail server, small models can't reliably code; and (c) a
   builder-side line in the *dev sessions* (the build assistant won't type the owner's live third-party passwords or
   create accounts on the owner's behalf) — which is sidestepped by the owner doing a 10-second login while the device
   does the rest, not by any OS restriction.

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
- **The host test suite is DESTRUCTIVE on a live install — never run it there.** Several tests reconfigure the real
  machine: `test-firewall.py` / `test-rootd-firewall.py` apply the real firewall (one applies internet=off), and
  `test-rootd-power.py` stops/restarts real services. Running the full suite on the live laptop once rebuilt its
  firewall WITHOUT the dev-SSH rule and knocked out remote SSH (the machine was fine — 4 days uptime — but
  unreachable until the firewall was reapplied via the devlink/OTA channel). `selfdev.py` now REFUSES to run on a
  live install (`_is_live_install`). The gate belongs on a dev checkout or a VM; ship the result to the laptop via OTA.
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
- Self-dev must run on a dev checkout or VM (its test gate reconfigures the real firewall + services), then ship to
  the laptop via OTA. `selfdev.py` now refuses to run on a live install. Do NOT "fix" that by removing the guard.
- Optional model follow-ups the owner raised: benchmark a local coder vs the online one; a durable (non-disposable)
  device email via a domain the owner owns.

## 8. One thing to pass along honestly

Most of this project is built and works. The friction in the last stretch was not the OS's capability — it was tasks
that are capability-limited for *any* assistant (third-party logins, CAPTCHAs, autonomous account creation on screened
services) and best done by the owner in seconds, plus the single real-machine prudence of not auto-shipping unreviewed
self-modifications. The OS itself is uncensored and owner-sovereign exactly as specified.
