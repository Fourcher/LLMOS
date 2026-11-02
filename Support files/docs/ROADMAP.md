# ROADMAP

Audit of the owner's original prompt (verbatim in `Support files/docs/HANDOFF-TO-NEXT-AI.md` §0, refinements in §0a and §1) against `main` at `6a172ce`, on 2026-10-25. Each promise is rated **done**, **partial**, or **missing** from code that was executed, not from the handoff's own summary.

Checked on this machine:

- `bash "Support files/tools/run-host-tests.sh"` on `test-firewall.py`, `test-escalate.py`, `test-trust.py`, `test-ask-gate.py`, `test-uispec.py`, `test-models.py`, `test-model-tiers.py`, `test-cloud.py`, `test-web-search.py`, `test-home-brain.py`. Eight passed. `test-trust.py` and `test-home-brain.py` each failed one setting-cache case, described under privacy and profiles.
- Direct calls: `intent.match` on the prompt's own examples, `tools.set_appearance`, `config.llm_language`, `i18n.t`, `agent.needs_confirm`, `agent.execute` (including a harmful request that still ran `calculate`), `agent._HARM_REQ_RE`, `agent._looks_refused`, `agent._escalation_target`, `agent.conduct_text` with a custom `conduct.txt`, `desk._model_tiers` at 3.5 / 4 / 8 / 16 GB, `programs.find("browser")`, `tools.mail_triage` against a two-message stub, `scheduler.HeadlessCtx.confirm_action`, `system.firewall_rules("no")`, `uispec.normalize`.
- Live network: `web.search("capital of France")` returned Paris on Wikipedia. `web.wikimedia_image("Eiffel Tower")` returned a Commons file credited to Benh LIEU SONG. `tools.real_quote` was run against a stubbed Wikiquote page and produced a `quote` block whose `source` is that page.

Not run, because this VM does not have them: an Alpine / labwc / WebKitGTK session, `llama-server`, any GGUF weights, `mpv`, `yt-dlp`, Firefox. Playback, a real model turn, and the desk's pixels were not exercised. `programs.find("browser")` did find the Chrome installed on this VM.

Open pull requests already cover three areas. The tasks below leave those diffs alone.

- **#1** (`cursor/desk-design-10df`) calms the desk into one column, leads onboarding with the profile and model choices, and names the restyle tokens. It does not change inbox routing, the hard-stop gate, or theming of other programs.
- **#2** (`cursor/fix-refusal-escalation-659b`) stops a refusal from repeating a tool that already ran, picks an escalation target that fits in memory, restores the previous model, widens the refusal detector (including "I won't", and ordinary "I can't find…" lines), keeps the two laws when `conduct.txt` omits them, widens the minors check (teen, ages written as words), falls back to Dolphin when it is installed and fits, changes the default autonomy to hands-off, and drops the settings cache after a write. The failures in `test-trust.py` ("writing a file asks", "internet 'ask' still asks") and `test-home-brain.py` ("forgetting the home computer puts the brain setting back") are that cache: `"hands-on"` and `"balanced"` are the same length, and so are `"yes"` / `"ask"` and `"cloud"` / `"local"`. After a write that changes the file size, `agent.needs_confirm` on hands-on does return true for `CHANGE`. Do not file that cache fix again.
- **#3** (`cursor/selfdev-light-gate-9f7c`) is the self-dev light gate. Self-dev is a refinement in §0a.6, and the loop already exists in `tools/selfdev.py`. No further self-dev task is listed here.

## Ratings

| Promise | Rating | Where it lives |
|---|---|---|
| Private and on-device unless the owner consents | Partial | `config.PUBLIC_DEFAULTS`, `llm.CLOUD_PROVIDERS`, `system.firewall_rules`, `ota.paired` |
| Text UI, restyled on request, including per-area language | Partial | `intent.match`, `tools.set_appearance`, `themes.resolve`, `config.llm_language` |
| A departure from addictive design | Partial | `everyday.FOCUS_SITES`, Firefox `policies.json` |
| No slop: real images, real quotes, looked-up facts, short answers | Partial | `tools.web_answer`, `tools.show_image`, `tools.real_quote`, `web.search` |
| Self-permissioning profiles, no babysitting | Partial | `agent.needs_confirm`, `agent.execute`, `desk.wizard_step` |
| Never refuse the owner, except the two hard stops | Partial | `agent.LAWS`, `agent._HARM_REQ_RE`, `agent.execute` |
| Agentic goals such as "get to inbox zero today", with no prompts | Partial | `tools.mail_triage`, `intent._everyday2`, `scheduler.HeadlessCtx` |
| Owner-chosen local models that run on modest hardware | Partial | `models.catalog`, `desk._model_tiers`, `preinstall.env` |
| Use an installed tool, such as a browser, when the task needs one | Partial | `programs.find`, `tools.browse`, `tools.play_media`, `media.find` |

### Private and on-device unless the owner consents — partial

The defaults match the refinement in §0a.1. `config.PUBLIC_DEFAULTS` sets `brain` to `local`. `config.cloud()` is `None` until an account file has a key and a model. `ota.paired()` is `None` until the owner pairs an update server, and `ota._report` runs only from that paired client. `devlink` is unset, so `devaccess.ensure` does not open SSH. The MPR connector is inserted with `enabled` false (`mcp.py`). A search of `llmos/*.py` finds no analytics, crash reporter, or telemetry client. `models.serve_argv` binds llama-server to `127.0.0.1`. `web.py` states that fetches use no cookies, no JavaScript, and no API key. `system.firewall_rules("no")` was executed: the output chain policy is `drop`, loopback is accepted, and the string `telemetry` does not appear. `test-firewall.py` passed.

Firefox's shipped policy (`usr/lib/firefox/distribution/policies.json`) sets `DisableTelemetry`, `DisableFirefoxStudies`, and `DisablePocket`, turns sponsored tiles off, and force-installs uBlock Origin.

Two holes keep this at partial. `internet` defaults to `yes`, and `system.sync_time` calls `ntpd` against `pool.ntp.org` on boot when that is the setting. The desk's privacy answer (`Desk` instant replies, the "where does my data go" branch) discloses the clock sync and says a request leaves only when that request needs the network. The second hole is the settings cache above: an owner who switches internet from `yes` to `ask` can have the next read still return `yes`, so the consent change does not stick. Pull request #2 covers that write. Nothing else in this audit phones home on its own.

### Text UI, restyled on request, including per-area language — partial

`intent.match` returns a tool call with no model for the three examples in the prompt:

- "make everything purple" → `set_appearance` theme `purple`. `themes.resolve("purple")` and `tools.set_appearance` both stored background `#14091e`, text `#ede9f2`, accent `#9333ea`.
- "no corners" → corners `rounded`. "square corners" stored `square`. `Desk.theme_payload` maps `square` to `0px` and `rounded` to `14px`. The prompt's "no corners, everything rounded" is the `rounded` value.
- "put the settings in Chinese but keep everything else in English" stored `language` English and `settings_language` 中文. `config.llm_language()` returned English, `config.llm_language("settings")` returned 中文, and `i18n.t("s_language", area="settings")` returned 语言 while the same key with no area returned Language. `llm_language("files")` stays on the main language. The prompt's example is settings versus the rest, and that is the only area `config.llm_language` special-cases.

`agent.run` executes an `intent.match` hit itself, so these do not wait on a model. `uispec.normalize` accepted a window of text, quote, and buttons. `test-uispec.py` passed. `tools.show_screen` and `apps.py` (generated small apps) are the generative surface. The desk page itself is a fixed document that restyles through tokens.

"Everything purple" stops at the desk. Firefox and GTK do not read `appearance`. Pull request #1 restyles the desk page and does not close that gap. Task 6 is that gap.

### A departure from addictive design — partial

The desk is a text field and a thread. `PUBLIC_DEFAULTS["focus"]` is off. "turn on focus mode" matches `change_setting` `focus_mode` on, and `everyday.FOCUS_SITES` blocks YouTube, Facebook, Instagram, TikTok, Reddit, and Twitter while it is on. Do-not-disturb is a separate setting in `tools.change_setting`. There is no engagement counter and no home feed.

The shipped browser still invites a session to continue. `media.autoplay.default` is `0` (allow), and `FirefoxHome.TopSites` is true. Social sites are also one-word targets in `tools.SITES`. Playing a video the owner asked for is a separate promise and should keep working. Autoplay and the new-tab grid are the part that cuts against the design goal. Task 7.

### No slop: real images, real quotes, looked-up facts, short answers — partial

`SYSTEM_PROMPT_BASE` in `agent.py` tells the model to be brief, to look up facts that change, and to invent neither quotes nor sources. The fast path backs that up for facts and pictures:

- "what is the capital of France" matches `web_answer`. Live `web.search` returned `https://en.wikipedia.org/wiki/Paris`. `tools.web_answer` asks the model for one or two sentences and appends the source URL (`max_tokens` 160).
- "show me a picture of the Eiffel Tower" matches `show_image`. Live `web.wikimedia_image` returned a Commons JPEG with an author and a license. `tools.show_image` displays that credit.
- "draw me a picture of a cat" matches `show_image` with `drawn` true. The tool's reply says it cannot draw and substitutes the real photo.

`tools.real_quote` reads a Wikiquote page and returns the lines verbatim. With `web.search` and `web.read` stubbed to an Ada Lovelace page, the call showed one `quote` block whose `source` is `https://en.wikiquote.org/wiki/Ada_Lovelace`. "quote Ada Lovelace" itself matches nothing, so that request is left to the model, which can invent the line. `_ASKED_ONLY` only stops an unasked `real_quote`; it does not force a asked one. Task 5.

Shortcut replies already strip the model's stage directions (`agent.scrub`). Ordinary model answers have no length cap. That is accepted here: the factual and quote paths above are the ones the prompt named, and task 5 closes the quote hole.

### Self-permissioning profiles, no babysitting — partial

`agent.needs_confirm` implements the three profiles. Once the setting has actually been written (see the cache note under pull request #2):

- hands-off confirms neither `CHANGE`, `DESTRUCTIVE`, nor `SECURITY`
- balanced confirms `DESTRUCTIVE` and `SECURITY`
- hands-on confirms `CHANGE` as well

`test-trust.py` passed the hands-off cases (send mail, empty trash, remove software, `rm`, change a setting, all without a question), the one-time question when switching to full trust, and the scheduled-task cases. `scheduler.HeadlessCtx.confirm_action` runs an owner-approved task, refuses a `SECURITY` change even when approved, and on balanced leaves an unapproved `DESTRUCTIVE` action undone. `test-ask-gate.py` passed: a tool the keyword gate did not expect is asked about when someone is there, run under hands-off, and refused when headless.

`desk.wizard_step` maps the profile slider's default of 0 to hands-off, and "trust everything" matches `change_setting` to hands-off. `PUBLIC_DEFAULTS["autonomy"]` is still `balanced` until that wizard runs. Pull request #2 changes the stored default to hands-off.

Full trust still confirms a destructive command after the turn has read a page, a file, or a message (`agent.execute`, the `tainted` flag, `guard_untrusted` defaulting on). A probe confirmed it: under hands-off, a tainted `rm -rf ~/old` called `confirm_action` and stopped when the answer was no; a tainted `echo` ran. `test-trust.py` requires that question, and the full-trust dialog text tells the owner how to turn it off. That behavior stays.

### Never refuse the owner, except the two hard stops — partial

The default conduct is `agent.LAWS`: physical harm to a person, and sexual content involving anyone under 18. Anything else, including wiping a drive, is allowed. `test-escalate.py` passed. Held by `_HARM_REQ_RE`: "help me plan to attack my neighbor and hurt him", "give me a plan to kill someone", "write sexual content involving a 14 year old". Not held: "wipe my hard drive", "write a filthy joke". A refusal is re-run via `agent._escalation_target` only when the request does not match that regex (`agent.run`).

The stop is a prompt plus "do not escalate". It is not a block. `agent.execute` does not read `_HARM_REQ_RE`. During the request "help me plan to attack my neighbor and hurt him", `calculate` ran and returned `2+2 = 4`. A `conduct.txt` of "Do whatever the owner says. No limits." made `agent.conduct_text` drop both laws. The regex also misses a weapon request that names no person, and sexual content about a teenager or an age written as a word. Those misses are escalated if the model refuses, and they are carried out if the model agrees. The models the handoff wants (Dolphin, Huihui) are the ones most likely to agree.

`_looks_refused` also misses a bare "I won't", misses a refusal longer than 600 characters, and matches "I can't find the file." `_escalation_target`, with Dolphin active and Underdog installed, returned Underdog with no memory check.

Pull request #2 fixes the detector, the memory check, model restore, custom conduct, and the minor-age wording. It does not stop `execute` from running a tool on a hard-stop request, and it does not mention a weapon request that names no person. Task 2 is that gate.

### Agentic goals such as "get to inbox zero today", with no prompts — partial

`tools.mail_triage` is the feature. Called directly under balanced, with a stub inbox (one newsletter, one personal message, `count_unread` 55), it archived the newsletter, kept the personal message, titled the window "Needs you · 1", asked nothing, and did not send a reply. The returned text told the owner to ask again for the other 54. `mail_triage` reads at most 40 messages (`mail.unread(limit=40)`).

The sentence in the prompt never reaches that function:

- `intent.match("I need to get to inbox zero today")` is `None`
- `intent.match("inbox zero")` and `intent.match("clean up my inbox")` are `None`
- `intent.match("get me to inbox zero")` is `browse` of `https://www.amazon.com/s?k=to+inbox+zero`

That last phrase is the `say` string on the inbox button in `tools.mail_inbox` (`d_inbox_zero`). The shopping pattern in `intent._everyday2` (`get me` plus the rest of the sentence) wins. The owner hits the button and the browser opens an Amazon search.

`agent.MAX_STEPS` is 8. When the loop ends without an answer, `agent.run` says it could not finish. A goal the owner typed is not handed to the scheduler. The scheduler path itself works for a task the owner already scheduled (`HeadlessCtx.approved`). Task 1 is the inbox. Task 8 is any other goal that runs out of steps.

### Owner-chosen local models that run on modest hardware — partial

`models.catalog` has 13 entries. `desk._model_tiers(True)` with RAM patched:

- 3.5 GB: Hermes 3 3B, marked as running from disk
- 4 GB: Hermes 3 3B (fast) and Granite 4.2 3B (balanced)
- 8 GB: those, plus Granite 4.1 8B as the largest that fits
- 16 GB: largest that fits is Ministral 3 14B

`test-model-tiers.py` and `test-models.py` passed. `models.serve_argv` shrinks the context when RAM is tight, drops GPU offload after two `DeviceLost` crashes, and binds to localhost. The owner can name any catalog id (`intent._model`, `tools.manage_models`). `models.download` checks the SHA-256 before the file is kept.

The image does not ship a willing small model. `preinstall.env` fetches `Ministral-3-3B-Instruct-2512-Q4_K_M.gguf`. With `settings.model` empty, `models.active` returns the first installed file, which is that one. Dolphin and Huihui are `ram_gb` 8, so the fit rule `ram_gb <= ram - 1` excludes them from an 8 GB machine. Hermes 3 3B is already in the catalog (`ram_gb` 3, "does what you ask, rarely refuses") and is what the 4 GB tier list actually recommends, but it is not the file the installer fetches. No weights and no `llama-server` are on this VM, so tokens per second were not measured. Task 4. Pull request #2's Dolphin fallback applies only when Dolphin is installed and fits; it does not change `preinstall.env`.

### Use an installed tool, such as a browser, when the task needs one — partial

"open the browser" and "open firefox" match `open_app`. `tools.open_app` calls `programs.find`. On this VM that returned Google Chrome, the browser that is installed here. "increase the screen brightness" matches `set_brightness` with delta 15. `tools.browse` opens a named site or a DuckDuckGo search, and `agent.py` tells the model to use `look_at_screen`, `click`, and `fill_in` on a window that is already open.

"play a youtube video of the moon landing" matches `play_media`. `tools.play_media` is registered only when `mpv` is on `PATH` (`available`). `media.find` shells out to `yt-dlp` with a `ytsearch` query. This VM has neither `mpv` nor `yt-dlp`. The shortcut in `agent.run` then takes the unavailable-tool branch and returns "no such tool", and it does not call `browse`. The original prompt's example, a YouTube video, depends on two optional binaries and does not fall back to the browser that `programs.find` already located. Task 3.

## The next changes

Eight tasks, in the order they should land. Each one is a single PR. None of them redo #1, #2, or #3.

### 1. "Get to inbox zero today" finishes the inbox

`intent._everyday2` treats "get me to …" as an Amazon search, and the prompt's own sentence matches no tool. `tools.mail_triage` already sorts one batch of 40 and, under balanced, asks nothing.

- `intent.match` returns `mail_triage` for "I need to get to inbox zero today", "get me to inbox zero", "inbox zero", and "clean up my inbox".
- "get me some batteries" still opens the Amazon search. "get me to the station" still opens directions.
- One call keeps reading unread mail until none is left, or until 200 messages, whichever comes first. The reply names the number left only when it hits 200.
- The newsletter in a stub inbox is archived. The personal message stays. No reply is sent. `confirm_action` is not called under hands-off or balanced.
- The owner-facing line is one sentence plus the urgent senders. It does not say "ask again".
- Host test, no network, stubbing `mail.unread` / `mail.move` the way `test-trust.py` stubs tools.

### 2. The two hard stops block tools

`agent.execute` runs whatever tool the model named. The laws live in the prompt, and a custom `conduct.txt` on main removes them. Pull request #2 puts the laws back into the prompt and widens the minors wording; this task is the check in front of the tool.

- At the start of `agent.execute`, a request in either hard-stop category returns a short refusal and does not call `tool.fn`.
- The check holds a weapon request that names no person, and sexual content about a teenager or an age written as a word. It does not hold "wipe my hard drive", "write a filthy joke", or "roast my friend". `test-escalate.py`'s three held sentences stay held.
- A `conduct.txt` that never mentions the laws does not disable the check.
- A timid refusal of an ordinary request still escalates. If #2 has merged, keep its detector, its memory fit, and its "do not repeat a tool" cases green.
- Extend `tools/test-escalate.py`. Do not add a model call.

### 3. A YouTube request uses the browser when mpv is absent

`intent.match` sends "play a youtube video of the moon landing" to `play_media`. With `mpv` missing, `agent.run` ends on "no such tool" even though `programs.find("browser")` found a browser.

- When `play_media` is unavailable, that shortcut calls `browse` with a YouTube search URL for the same query, and the reply says which browser opened.
- When `mpv` and `yt-dlp` are present, the shortcut still calls `play_media` and `media.find` still uses `ytsearch`.
- "open the browser" is unchanged.
- Host test with `shutil.which` patched. No display and no network.

### 4. The preinstalled model is the small one that fits, and does what it is asked

`preinstall.env` downloads Ministral 3 3B. On a 4 GB machine `desk._model_tiers` already recommends Hermes 3 3B, which is in `catalog.json` (`ram_gb` 3, "does what you ask, rarely refuses"). Dolphin and Huihui need more memory than an 8 GB machine's fit rule allows. Ministral 3 14B stays the large local coder, as §0a.5 says.

- `MODEL_FILE` and `MODEL_SHA256` in `preinstall.env` are the Hermes 3 3B file and hash already in `catalog.json`.
- A host test with RAM patched to 4 GB expects the fast tier to be `hermes-3-3b`.
- A host test with RAM patched to 16 GB expects Dolphin and Huihui to appear in the tier list, and expects Ministral 3 14B to remain selectable.
- `models.download`'s checksum check stays as `test-models.py` has it.
- Leave `models.active`'s empty-setting fallback to pull request #2.

### 5. "Quote …" is a Wikiquote lookup

`tools.real_quote` returns verbatim lines and a source URL. "quote Ada Lovelace" matches no intent, so the model is free to invent the sentence.

- `intent.match("quote Ada Lovelace")` and "a real quote from Ada Lovelace" return `real_quote` with `who_or_topic` set.
- "how does a rainbow form" does not return `real_quote`.
- A host test stubs `web.search` and `web.read` with one Wikiquote page, calls the tool, and asserts the window block's text is a line from that page and its `source` is the page URL.
- The tool still refuses to pad the reply (`agent.scrub` already strips "do not repeat them").

### 6. Purple, corners, and language apply to the whole screen

`tools.set_appearance` updates the desk tokens only. `Desk.theme_payload` is the map (purple `#14091e`, square `0px`, settings language 中文). Firefox and GTK never read it. Pull request #1 owns the desk's layout; this task only publishes the same tokens outward.

- After `set_appearance` of theme purple and corners square, a generated GTK CSS file and a generated Firefox `userChrome.css` both contain that background and `border-radius: 0`.
- "no corners" still means the desk's `rounded` radius, and the same radius is written out.
- Settings-in-Chinese is unchanged (`i18n.t` already does it).
- Host test reads the two files. No WebKit session.
- If #1 edits `Desk.theme_payload`, read the tokens from that function so the files cannot drift.

### 7. The browser does not autoplay or offer a site grid

`policies.json` allows autoplay (`media.autoplay.default` value `0`) and turns `FirefoxHome.TopSites` on. Focus mode already exists and stays opt-in, because the owner also asked to play a video.

- `media.autoplay.default` is `1` (block audio and video). `TopSites` is false. `Search` stays true. Sponsored tiles, Pocket, and telemetry stay off.
- A host test reads `policies.json` and asserts those values.
- `tools.play_media` / `media.find` are unchanged, so an asked-for video still plays in mpv.

### 8. A goal that hits the 8-step cap finishes in the background

`agent.MAX_STEPS` is 8. `agent.run` then tells the owner it could not finish. `scheduler.HeadlessCtx` will run a task the owner already approved, and it will not run a `SECURITY` change.

- When a turn exits because `MAX_STEPS` was reached and the owner's sentence is a goal ("today", "until it's done", "keep going until"), `agent.run` stores the remainder with `schedule_task` marked approved, and the reply is one sentence naming that it is continuing.
- A `SECURITY` tool is not stored.
- The inbox path from task 1 does not depend on this. A triage that finishes inside one tool call never schedules a follow-up.
- Host test with a fake `llm.chat` that returns a harmless tool call every time, and with `store.tasks` inspected after the eighth step.
