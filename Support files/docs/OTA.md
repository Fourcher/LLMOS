# Updates over the air (from your own computer)

Send LLM OS updates from the computer that builds it straight to a running LLM OS machine. No USB stick.

## On your computer (once)
1. `python3 "Support files/tools/ota.py" keygen`. This makes the signing key in `Support files/ota-keys/`, which is never in git.
2. `python3 "Support files/tools/ota.py" serve`. Leave it running. It prints its address and key code, e.g. `http://192.168.86.159:8781  key BCFE-BACB`.

## On the LLM OS machine (once)
Say **get updates from my computer**. It finds the server on your network and pins its key. The key code it shows must match the one your computer printed. If it can't find the server, say **get updates from 192.168.86.159** with your computer's address.

## Sending an update
`python3 "Support files/tools/ota.py" publish --version 1.8.4`

The machine installs it within seconds. Then:
- `tools/ota.py reports` shows what it said: OK, or why it wasn't installed.
- On the machine, **where do my updates come from** shows the source and the last update.

Options:
- `--restart` lists what to restart (default `llmos-rootd,llmos-scheduler,desk`).
- `--apk pkg1,pkg2` installs Alpine packages first.
- `--note` adds a note.

## What protects the machine
- **Pairing:** nothing happens until the owner pairs. **Stop updates from my computer** undoes it.
- **No incoming port:** the machine keeps one outbound request open to your computer. Nothing listens on it.
- **Narrow firewall exception:** the firewall lets through your computer's address and port only, even when the internet is set to Offline.
- **Signed updates:** each update must be signed by the pinned key (Ed25519, `ssh-keygen -Y verify`) and match its signed SHA-256.
- **Program files only:** an update may change LLM OS's own program files. It never touches settings, owner data or the generated firewall file.
- **Automatic undo:** the files an update replaces are backed up first. If the desk doesn't come back within 90 seconds, the backup is restored and the desk restarted.

## Limits
- **Kernel and boot:** updates cover LLM OS's Python, scripts, services and configuration, plus Alpine packages through `--apk`. A new kernel or boot change still needs an image.
- **Live USB:** on the live USB (not installed), an update lasts until restart.

## Tested
- **Host test:** `tools/test-ota.py`.
- **VM test (1.8.2 arm64, 2026-10-13):** pairing by phrase, a good update installed, another key's signature refused, a tampered archive refused, a broken desk rolled back on its own, and unpairing.
