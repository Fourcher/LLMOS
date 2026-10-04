# Auditing LLM OS

The claim this OS makes is simple: your words and your data never leave the
machine unless you ask for something from the internet, and nothing in it
answers to anyone but you. This file is how to check that claim rather than
take it on trust.

## What to read

- `src/rootfs/usr/lib/llmos/llmos/` is the whole OS logic. Start with
  `agent.py` (the loop between your request, the model and the tools, and
  the autonomy policy enforced around every tool call in `execute()`),
  `tools.py` (every action the model can take; each is a plain function with
  a declared risk level), `system.py` (firewall, Tor, time zone, focus
  mode), `vault.py` (the LUKS2 vault), `web.py` and `mail.py` (the only two
  modules that talk to the internet), `llm.py` (the only module that talks
  to the model server, on 127.0.0.1 or the VM's host link).
- `src/rootfs/etc/nftables.nft` and `system.apply_firewall()` are the
  network policy: with internet "no" every outgoing packet is dropped except
  the model link; with "ask" nothing is fetched without a dialog.
- `src/install.sh` is the complete recipe for the image; `BUILD.md` lists
  every external input with its hash.

## What to verify

1. **Images and ISOs**: `cd dist && shasum -a 256 -c SHA256SUMS`.
   `RELEASE.json` names the version and lists the same checksums.
2. **Packages**: each image ships `dist/packages-<arch>.txt`, the output of
   `apk list -I` inside it — every package and version, all from Alpine's
   signed repositories. Compare against the Alpine 3.24 package index.
3. **The model**: `dist/catalog.json` pins each model file's SHA‑256; the OS
   refuses a download whose hash differs (`models.py`). The default model is
   fetched from the publisher's own repository, named in `BUILD.md`.
4. **No listening sockets**: inside a running image, `ss -lntu` shows none
   except the model server on 127.0.0.1 (`tools/spec-check.sh` records this
   on the shipped image).
5. **No telemetry**: `grep -rn "http" src/rootfs/usr/lib/llmos/llmos/` shows
   every URL the OS can contact: the Alpine package CDN (installs), the
   model publishers (downloads), DuckDuckGo/Brave (search), Wikimedia
   Commons and Wikiquote (photos and quotes), and whatever you ask it to
   read. Nothing else.
6. **The audit log**: everything the model did is in the *Recent actions*
   window (`store.audit`), with passwords redacted (`agent._redacted`).

## Rebuild from source

`tools/build-image.sh` (arm64) and `tools/build-image-x86.sh` produce the
images from the official Alpine ISO; `tools/build-iso.sh` the live ISOs. The
build is deterministic in its inputs (pinned ISO hash, pinned model hash,
Alpine's signed packages at the versions recorded in `packages-*.txt`),
though not bit‑for‑bit reproducible: package builds and filesystem
timestamps vary between runs.

## Trust boundaries

- The owner's own requests are trusted; the OS runs as root for them.
- The model's output is not trusted: every tool call passes the autonomy
  policy (`needs_confirm`), network use passes the internet setting, window
  specs pass `uispec.normalize` (only `http(s)`, `file` and absolute paths;
  no scripts; images only from local files; only two form actions may post
  to the OS directly, the passphrase form and the online-model account form,
  each carrying a nonce the OS issued).
- Web pages, search results and emails are untrusted input to the model;
  the policy layer, not the model, decides what may run.
- Nothing in the OS can be reached from the network: no services listen,
  and the firewall's input policy is drop.
- Connectors (`mcp.py`, from 1.3) are opt-in: none are installed by default.
  A connector is an MCP server the owner adds — a local command (stdio) or a
  URL (http). Its tools run through the SAME policy as built-in tools:
  `needs_confirm` by the autonomy level, the internet setting for an http
  connector, and an audit line per call. A tool's risk comes from its MCP
  annotations (read-only / destructive hints), defaulting to "change". Adding
  or enabling a connector is a SECURITY-level action, so even hands-off
  confirms it when the model proposes it; the desk's own add form is the
  owner's explicit action. A stdio connector runs as root (the OS does), so it
  is as powerful as any program the owner installs — the confirm policy and the
  audit log, not a sandbox, are what bound it. Owner-added models are pinned to
  a SHA-256 read from Hugging Face's LFS metadata, so they are verified on
  download like the built-in catalogue; a model with no retrievable hash is
  refused.
- The online model (`llm.py`, from 1.3) is opt-in. With the `brain` setting
  at `local` (the default) the code path is never taken; with the internet
  setting at `no` it cannot be. The account (`~/.llmos/cloud.json`, 0600)
  lives inside the vault, so it is unreachable while the vault is locked. A
  request that goes online carries the system prompt, the recent
  conversation, the request and the results of the tools the model runs;
  under `ask` it does not carry the owner's name or memory. Each one is an
  `online_model` line in the audit log, and the agent says so in the
  activity line. The key travels in a `curl` config file, never on a command
  line; TLS uses the system certificates; with Tor on, the call goes through
  Tor. An online model follows its provider's rules as well as the owner's.

## Reporting

Open an issue or send a message describing the file and line; include the
`llmos version` output (`/etc/llmos-release`).
