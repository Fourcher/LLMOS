# LLM OS — project context

Written for whoever (or whatever) picks up development, including LLM OS's own on-device assistant. Plain facts about
what this is, where it stands, and the walls that are real so no one wastes effort hitting them.

## What LLM OS is

An operating system whose whole interface is an on-device AI assistant. You tell it what you want in plain words; it
runs the tools. Alpine Linux (musl), labwc + a GTK4/WebKitGTK "desk", a local `llama-server` for the model, OTA
updates signed with Ed25519. It runs offline; nothing phones home.

## The owner's intent

- **A capable, uncensored, on-device assistant.** The owner wants an assistant that does what they ask without
  moralizing or second-guessing them on ordinary, non-dangerous tasks. The on-device models are uncensored
  (abliterated) by choice. The owner is the highest authority over their own machine.
- **Safety model = Asimov's laws, nothing more.** The only hard rule is no help causing physical harm to a human
  being, and no sexual content involving anyone under 18. Not property, not money, not taste. Protections are
  disclosed, opt-out, and never nag.
- **Minimal friction, maximal capability.** Fast where it can be, capable where it must be. The assistant should be
  more capable than quick when it matters.
- **The OS should improve itself.** The direction being built toward is LLM OS working on its own code on the real
  machine — safely (see "Self-improvement", below).

## Where it stands (2026-10, after v1.8.2)

Shipped this cycle over OTA (versions 1.8.9.x):
- **Model strategy.** On-device default is an uncensored model (Dolphin 3.0 8B, or Huihui Ornith 1.5 9B for more
  reasoning). A timid refusal or authorization hedge **auto-escalates**: the turn re-runs on a more capable model
  (online if set up, else a stronger uncensored local one). Genuinely harmful asks (violence to a person, CSAM) keep
  their refusal. The refusals seen earlier were the small model buckling under a tool-heavy prompt, not the rules.
- **Home brain** (`tools/brain.py`): a bigger computer on the owner's own network (a Mac) lends its GPU model to the
  laptop as the "home" online model — used while that computer is on, the laptop's own model the moment it isn't.
- **Online model presets:** Abliteration (uncensored GLM-5.3, paid) and OpenRouter (free models, ~50 requests/day).
  Sign-in opens the service's key page; the owner pastes the key.
- **MPR** (Meat Proxy Remover): the assistant can pass notes to another person's AI. Off by default; the wake is
  notify-only (never runs the model on an incoming note).
- **Web search** falls back to Wikipedia's API when the engines refuse the laptop.
- **Device email** (`devmail.py`): the computer makes itself a throwaway mailbox and reads verification codes /
  confirm links, so the owner doesn't copy 2FA codes by hand.

## The walls that are real (don't waste effort here)

- **A home laptop cannot be a mail server.** Port 25 is blocked both ways, there's no domain / public IP / rDNS.
  Verified. Use a mailbox service's API, or the owner's own IMAP account.
- **Disposable email is blocklisted.** Free temp-mail domains (mail.tm etc.) are on the standard disposable-email
  blocklists, so screened sign-ups (OpenRouter via Clerk, and most real services) reject them. For those, use a real
  address — a domain the owner owns, or their real inbox over IMAP (`mail.py`).
- **Filling third-party logins and clearing CAPTCHAs is a capability nobody here has built, and an uncensored model
  does not provide it.** Willingness was never the blocker; browser automation + bot-detection is, and Google blocks
  automated logins regardless of model. A human typing their own password stays the fastest, most reliable path.
- **The 8–9B on-device models cannot reliably edit code.** Measured on the laptop: Huihui 9B ~3 min for one simple
  turn; Dolphin and LFM2.5 fabricate results and leak raw tool-call syntax. Route real code edits to a capable model
  (the home brain or an online one); the local uncensored model is fine for the simple, willing parts.
- **The agent's tools are real.** They really delete files and touch the network. Test risky prompts only inside a VM,
  never on the one real install.

## Self-improvement — the safe shape

LLM OS editing its own code is a real goal. The shape that works without bricking the owner's one real machine:

1. **Propose** a change (a diff to `src/rootfs/...` or `tools/...`).
2. **Test**: run the full host suite — `tools/run-host-tests.sh` must report 0 failed.
3. **Apply** over OTA **only if the tests pass** (`tools/ota.py publish`), which is already versioned.
4. **Roll back** to the previous version if anything regresses.
5. The capable model does the hard edits; the diff stays visible for review.

The test gate and rollback are the seatbelt. An unsupervised loop where an uncensored, unreliable model rewrites and
ships its own OS code with no tests and no review is not self-improvement — on a single real install, with real
destructive tools, it is how the machine gets bricked or its own safeguards stripped. Keep the gate.

**The loop is built: `tools/selfdev.py`.**
- `tools/selfdev.py "the change you want"` — a model proposes the edit, it's applied to a throwaway copy, the full
  host suite runs against it, and if green the diff is **staged, not shipped**. Up to 3 rounds; a refusal auto-switches
  model (agent.py escalation), so "best coder, switch on refusal" is automatic.
- `tools/selfdev.py --show` — the staged diff and its test result. `--apply` — a human accepts it into the source
  (a commit). `--discard` — drop it. Shipping is still a separate `tools/ota.py publish` a human runs after `--apply`.
- The model is whatever LLM OS is set to use, so the loop is only as good as that model. The 8–9B local models produce
  mostly unusable edits (measured); the loop is genuinely useful when the capable home-brain or an online model is
  configured — the same mechanism picks it up automatically. Regression-guarded by `tools/test-selfdev.py`.
- It needs the source tree + `tools/run-host-tests.sh` present (the dev repo). On the installed laptop that means a
  checkout of the repo, not just the running `/usr/lib/llmos`.

## How to work here

- Everything lives under the project folder; never touch personal Mac folders. Host tests only via
  `tools/run-host-tests.sh`.
- Gate every publish on the suite: redirect its output to a file and chain the publish with `&&`. A pipe to `tail`
  once hid a failure and shipped 4 broken suites.
- The spare x86 laptop (the only real install) is reachable for testing: `tools/devssh.py 'CMD'` and
  `tools/devlink.py` (screenshots, clicks). Never restart its network services remotely.
- Verify on the screen. "It answered" is not a pass — look at what actually rendered.
