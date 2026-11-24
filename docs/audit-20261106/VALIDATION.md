# Audit 2026-11-06: validation of the 104 reconciled candidates

Checked against `main` at 6e39388de5 (PR #24), November 23, 2026. Each candidate was looked up in the current
source, not taken from the audit's line numbers (most have moved).

Owner rules applied: no new confirmation prompts, approval dialogs, refusals, nags, autonomy reductions, hands-off
disablement, raised risk levels that create prompts, or limits on the owner's shell, input, network or files. The
two permanent hard stops were left untouched. No networking changes: `etc/nftables.nft`, `tailscale.py`,
`tailscale-watchdog` and `packages.txt` were not modified. Items 3, 5, 9, 10, 20, 31, 32, 37 and H043 were excluded
before reconciliation and are not in this list.

Status key:
- **FIXED**: the bug was still present, and this PR fixes it. Each fix is covered by `tools/test-audit-fixes.py`.
- **ALREADY**: already fixed, or the current code is not affected.
- **N/A**: not runtime OS code (developer-host tooling, `.claude` agent config, build pipeline), or the feature
  no longer exists.
- **SKIP-OWNER**: the only fix would add an owner prompt, refusal or restriction, or would raise a risk level so
  that more prompts appear.
- **SKIP-NET**: needs networking or firewall changes, which are out of scope by rule.
- **DEFERRED**: real, but too large or risky to ship without on-device GUI or hardware testing. Listed for a
  follow-up.

| # | Status | Notes |
|---|---|---|
| 1 | DEFERRED | WebKit content-world isolation and per-dialog tokens. This is a GUI change that must be tested on the device. |
| 2 | DEFERRED | Main-frame navigation lock and GTK drop controller. This is a GUI change that must be tested on the device. |
| 4 | FIXED | `Desk.describe_args` now shows every command in a `commands` list, not only `command`. |
| 8 | FIXED | OTA `manifest_fresh`: a signed manifest that is older than the installed one (`created`) is refused, which stops replay and rollback. An optional `hosts` list is honored. Manifests without `created` still install. |
| 11 | SKIP-OWNER | Classifying `remote_testing` as SECURITY adds prompts. Clearing `devssh_key` on "off" would break the owner's dev link. `devaccess` already ignores the key while devlink is off. |
| 14 | SKIP-OWNER | Holding tainted-turn facts would need a confirmation. |
| 15 | DEFERRED | The OTA bootstrap path is developer-host tooling (`tools/ota.py`). It needs an owner-supplied fingerprint flow. |
| 16 | ALREADY | Devlink commands and OTA manifests are already signed with the pinned key (`ssh-keygen -Y verify`), and devlink commands must be fresh and unique. |
| 17 | SKIP-OWNER | Adding tools to `UNTRUSTED_READS` sets `ctx.tainted`, which prompts for every later CHANGE under the default `guard_untrusted`. |
| 18 | SKIP-OWNER | Same as 17 (tainting connector tools). |
| 19 | SKIP-OWNER | Replaying UI buttons as tainted would add prompts. |
| 21 | DEFERRED | Structured printer-panel actions need a syspanels/intent refactor (see H060). |
| 22 | SKIP-OWNER | Same as 19. |
| 23 | DEFERRED | Structured Wi-Fi join actions: same refactor as H060. |
| 24 | FIXED | The local website is now `llmos.webserve`. It binds 127.0.0.1, answers only Host 127.0.0.1/localhost (blocks DNS rebinding), does not serve or list hidden files (`.llmos`, `.ssh`), and does not follow symlinks out of its folder. The owner still picks any folder. |
| 25 | FIXED | `mail_reply` resolves its reference exactly: an exact address wins, and words that match more than one sender return those messages' ids instead of replying to the newest match. |
| 26 | FIXED | `llmos serve-argv` prints one argument per line, and `llmos-model-run` splits only on newlines with globbing off, so a model path with spaces stays one argument. |
| 27 | DEFERRED | A root-level factory-reset verb in rootd. This needs a device test of reset. |
| 28 | SKIP-NET | Tailscale logout and state removal (networking). |
| 29 | SKIP-OWNER | Raises the risk of commands with shell metacharacters to SECURITY, which means more prompts. |
| 30 | FIXED | ImageMagick picture edits run with LLM OS's own `policy.xml` (`/usr/share/llmos/imagemagick`, via `MAGICK_CONFIGURE_PATH`): no URL/HTTP/HTTPS/FTP fetches, no MSL/MVG, and no `@file`. Every ffmpeg conversion and trim uses `-protocol_whitelist file,pipe`. |
| 33 | FIXED | `open_app` runs a plain command line as its own argv (`shlex.split`, no shell), so a quoted path with spaces is one argument. Command lines with shell syntax still go through `/bin/sh`, as before. The risk level is unchanged, so there are no new prompts. |
| 34 | SKIP-OWNER | Raises the `type_text` risk for terminals, which means more prompts. |
| 35 | SKIP-OWNER | Limiting `web_security_scan` targets restricts the owner. |
| 36 | FIXED | `restore_backup` restores only the backed-up folders, so `tasks.json` and `connectors.json` (in `.llmos`) can no longer be restored from a stick (see H085). |
| 38 | SKIP-OWNER | A ScreenCast portal chooser is a new prompt. |
| 39 | DEFERRED | `restart_desk` process selection by UID and path. Needs a device test (desk restarts). |
| 40 | FIXED | The share server's `translate_path` resolves symlinks and refuses anything outside the shared folder. |
| 41 | ALREADY | `LLMS_MIC_SECRET` no longer exists in the current code. |
| 42 | N/A | The 8765 `http.server` is developer-host build tooling, not the OS. |
| 43 | SKIP-OWNER | A fetch destination whitelist restricts the owner's network. |
| H001 | N/A | `.claude/hooks` developer-agent config, not the OS. |
| H002 | N/A | `.claude` orchestrator inbox, not the OS. |
| H003 | N/A | `.claude/agents` permissions, not the OS. |
| H004 | DEFERRED | Running selfdev tests in a container or unprivileged user is large and would change the proven local self-improvement loop. |
| H005 | N/A | `build-image.sh` developer-host tooling. |
| H006 | DEFERRED | Pinned llama.cpp tarball digests need release-pipeline digests. |
| H007 | DEFERRED | Reproducible build or signed digests for the `gtk/noroot` shims (build pipeline). |
| H008 | N/A | `dist/setup/llmos-setup.py` developer-host setup tool. |
| H009 | ALREADY | Archive extraction runs as the owner into the owner's chosen folder (`tar --no-same-owner`). tar and unzip refuse absolute and `..` paths. |
| H010 | DEFERRED | Signed `root.sfs` in live/init needs a signing pipeline. |
| H011 | FIXED | After `delete_file` resolves a bare name or guessed path, the confirmation and activity line show the resolved path (`shown` is recomputed). |
| H012 | ALREADY | `agent.execute` sets `confirm_tainted` on the same DeskCtx/ConsoleCtx whose `confirm_action` reads it (desk.py:598, console.py:79). |
| H013 | SKIP-OWNER | Same as 17. |
| H014 | SKIP-OWNER | Same as 17. |
| H015 | SKIP-OWNER | A "locked" state that restricts the serial console restricts the owner. |
| H016 | DEFERRED | Isolating custom CSS from `#overlay .dlg` is a GUI change; needs a device test. |
| H017 | DEFERRED | Turning off `allow_universal_access_from_file_urls` can break desk pages; needs a device test. |
| H019 | DEFERRED | SO_PEERCRED gating of the desk's test shell. Risk of locking the owner out; needs a device test. |
| H021 | DEFERRED | Same as H017. |
| H022 | DEFERRED | Same as H017 (subresource policy). |
| H023 | SKIP-OWNER | Tainting unapproved tasks on unlock adds prompts. |
| H024 | SKIP-OWNER | Same as 19. |
| H025 | FIXED | OTA archive folder entries must be LLM OS's own folders or their parents. Parents (`usr/`, `etc/`) are only created, never re-permissioned. Anything else is refused. |
| H026 | FIXED | Devlink rejects a NaN or infinite `ts` (NaN previously passed the 120 s freshness check). |
| H027 | DEFERRED | Persisting devlink `_seen` across restarts. Low value now that commands are signed, fresh and unique, and the timestamp is finite. |
| H028 | DEFERRED | A longer OTA fingerprint changes both ends and the stored pairing marks (bugfix.py). |
| H030 | FIXED | Same as 24. |
| H034 | SKIP-OWNER | Capping MCP `readOnlyHint` raises connector risk, which means more prompts. |
| H036 | DEFERRED | A minimal environment for stdio connectors could break the owner's connectors; needs per-connector testing. |
| H037 | SKIP-NET | Tor routing for HTTP connectors. |
| H039 | DEFERRED | A brain-server handshake is a protocol change on both ends. |
| H041 | SKIP-OWNER | Refusing plaintext mail transport restricts the owner's account setup. |
| H042 | SKIP-OWNER | A sensitive-file blacklist restricts the owner's files. |
| H044 | DEFERRED | Reset cleanup of `/var/lib/llmos`. Needs a device test of reset (same as 27). |
| H045 | SKIP-NET | Dropbear (SSH) configuration on reset. |
| H046 | DEFERRED | SO_PEERCRED UID check in rootd. Risk of locking the owner out of rootd; needs a device test. |
| H047 | DEFERRED | Same as H019. |
| H048 | DEFERRED | Desk-app UID, path and environment validation in the launcher; needs a device test. |
| H050 | DEFERRED | Separate log directories for root services (service config; needs a device test). |
| H051 | SKIP-OWNER | Re-gating headless instructions adds prompts or skips. |
| H052 | SKIP-OWNER | Re-verifying task approval when text changes adds prompts. |
| H054 | FIXED | The share server's `do_HEAD` hides dot-paths like `do_GET` does. |
| H055 | FIXED | `share.current()` checks `/proc/<pid>/cmdline`, so a stale `share.json` whose pid now belongs to another program is not a share and opens no port. |
| H056 | SKIP-NET | tailscale-watchdog. |
| H057 | SKIP-NET | Ports on `tailscale0`. |
| H058 | SKIP-OWNER | Raising the risk of `undo` adds prompts. |
| H059 | SKIP-OWNER | Blocking shares of system folders restricts the owner (shares already hide dot-files). |
| H060 | DEFERRED | Structured panel actions with deterministic handlers. A large intent/syspanels refactor. |
| H064 | SKIP-NET | DHCP firewall rule. |
| H065 | SKIP-NET | Tor `out_policy`. |
| H069 | DEFERRED | Re-verifying the model pin at load. Hashing many-GB models at every start needs a design (cached digest plus mtime). |
| H073 | FIXED | Text added to a picture: a leading `@` is escaped and `%` is doubled, so ImageMagick draws the words instead of reading a file or expanding properties. The policy also blocks `@*`. |
| H074 | SKIP-OWNER | Confining `edit_image` `save_as` to home restricts the owner's files. It already never overwrites (`_free_path`). |
| H080 | FIXED | `format_drive` takes a `drive`. With several drives plugged in and none named, it erases nothing and lists them (device, name, size) so the right one is named. One drive works as before. |
| H081 | DEFERRED | MAC integrity for policy files. Large. |
| H082 | FIXED | mpv `--title` doubles `$`, so a video title is never property-expanded. The media address goes after `--`, so it is never an option. |
| H083 | FIXED | mpv starts with umask 077, so its IPC socket is owner-only. |
| H084 | FIXED | `restore_backup` never follows symlinks (files or folders) and writes plain modes (0644, or 0755 for executables; no setuid or group/other write). |
| H085 | FIXED | `restore_backup` restores only the folders `backup_files` writes (Documents, Pictures, Music, Videos, Desktop, Downloads, Apps). No hidden folders. |
| H086 | FIXED | The `_POLICY_NAMES` comment now matches `agent.needs_confirm`: hands-off asks nothing. Comment only. |
| H087 | FIXED | Same as 33. |
| H088 | SKIP-OWNER | Same as 34. |
| H089 | SKIP-OWNER | Same as 17 (tainting OCR and AT-SPI). |
| H090 | FIXED | `web_security_scan` keeps a scheme only for a real `http://` or `https://`. `httpfoo.lan` becomes `http://httpfoo.lan` and can no longer reach nikto as a bare word. |
| H091 | SKIP-OWNER | Same as 17 (tainting scan output). |
| H092 | FIXED | `capture_traffic` creates the pcapng 0600 (owner-only) before tshark writes it. Retention is unchanged (the owner keeps their captures). |
| H093 | FIXED | `_in_home` resolves symlinks and `..` (`realpath`) before the prefix check, for `analyze_program` and the copy and move checks. |
| H094 | SKIP-OWNER | Confirming non-local scan targets is a new prompt. |
| H095 | SKIP-OWNER | Approval-flag HMAC and source tagging would gate tasks and add prompts. |
| H096 | SKIP-OWNER | Making headless tasks respect taint would skip or prompt hands-off tasks. |
| H097 | SKIP-OWNER | Same as 19. |
| H098 | FIXED | desk.js form submission (and `fmt`) substitute `{field}` in one pass over the template, so a typed value containing `{other}` is kept as typed. |
| H099 | SKIP-OWNER | Same as 19. |

## Counts (104 candidates)

| Status | Count |
|---|---|
| FIXED | 27 |
| ALREADY | 4 |
| N/A | 6 |
| SKIP-OWNER | 32 |
| SKIP-NET | 7 |
| DEFERRED | 28 |

The DEFERRED items are real follow-ups that need on-device GUI or hardware testing or a larger refactor. None of
them was skipped for owner-rule reasons. SKIP-OWNER items stay skipped: their only fixes would add prompts,
refusals or restrictions.

Tests: `tools/test-audit-fixes.py` (new) covers every FIXED item. `tools/test-everyday-words.py` now expects the
local website to launch as `llmos.webserve` (same check, new launcher). No test was weakened.
