# Verification report: the delivered "LLM OS prototype"

**Deliverable checked:** `llmos.qcow2` (23 parts from muse.ai, reassembled) +
`RUN_GUIDE.md`. **Checked on:** Mac mini, Apple M4, macOS 27, QEMU 11.1.1,
2026‑09‑25.

## Summary

| Area | Result |
|---|---|
| Download + reassembly | ✅ all 23 parts; SHA‑256 matches exactly (`0fb99e65…3c31`) |
| Boots | ✅ x86‑64, BIOS/Syslinux, Alpine 3.24, kernel 6.18.53; `llm>` prompt after ~25 s |
| Non‑LLM commands | ✅ every command in the table works as documented (`info`, `note/notes`, `theme`, `play <url>` fetches a real page title, `brightness`/`volume` answer honestly that the VM has no device, `profile`, `audit`, `date`, `echo`) |
| **Runs usably on this Mac** | ❌ **No.** The guide's macOS command fails: `-accel hvf: invalid accelerator`. HVF cannot run an x86‑64 guest on Apple Silicon; only pure emulation (TCG) works |
| **The LLM (`ask`)** | ❌ Under TCG: `ask what can you do?` took **8 min 51 s** and returned **"(the model returned an empty reply)"**. Generation ran at 0.5 tok/s. The only AI feature produced no usable answer in the one test the guide suggests |
| Matches the brief | ❌ A small fraction — see below |

The image is a real, honestly‑built bootable Alpine VM with a real (tiny)
model and nine hand‑coded tools. It is not usable on the machine it was
delivered to, and it does not implement most of what the brief asked for.

## What was actually inside

- Alpine Linux 3.24 (x86‑64), Syslinux, root autologin on the serial console,
  empty root password.
- `/usr/local/bin/llm-agent`: a 730‑line Python script. `ask` builds a Qwen
  chat prompt by hand and runs `llama-cli` **as a subprocess for every
  question**, so the 640 MB model is re‑loaded from disk on every `ask`
  (the guide's "2–4 minutes model load" is per question, not per boot).
- Model: Qwen3‑0.6B Q8_0 (`/opt/llmos/model.gguf`, 610 MB). A 0.6 B model
  cannot reliably drive tools; in the test it echoed the question back.
- `llama-cli` reports `version: 0.5.0-dev (build 0, commit unknown)` — a
  locally built snapshot, not the "official llama.cpp release" the guide
  claims. `BUILD_NOTES.md`, `TEST_LOG.md`, `ARCHITECTURE.md`, `RESEARCH.md`
  referenced by the guide were not part of the delivery.
- `/etc/apk/repositories` points at `http://10.0.2.2:8123/…` (the builder's
  private mirror). `apk add` on the shipped image cannot install anything.
- `/root/.ash_history` still contains the programmer's debugging session
  (copying the model to `/tmp`, hand‑made prompts, timing runs).

## Brief vs. delivery

| The brief asked for | Delivered |
|---|---|
| "computer does what you say", from brightness to playing a YouTube video | 9 fixed tools; `play` only fetches a page `<title>`; no media, no apps |
| Remembers user preferences | no memory at all (`note` is a text file the model never reads) |
| Agentic, schedules tasks, completes them unattended | nothing runs unattended; no scheduler |
| Voice ("simply speaks what they want") | none |
| Generated UI: "turn everything purple", "no corners", settings in Chinese | 4 fixed colours; no shapes, no languages |
| Private and secure, "for Snowden", no backdoors | root autologin, empty password, no encryption, no firewall; a network service (`play`) with no policy |
| User chooses/downloads models | one baked‑in model, no way to change it |
| Self‑permissioning, no babysitting | profiles exist, but the tools are read‑only or trivial, so autonomy changes nothing |
| Research online instead of guessing | no search; `play` is the only network call |
| Runs on the customer's ordinary machine | x86‑64 only; on the Mac it was delivered to it runs at 0.5 tokens/s |

## What was done about it

The delivered image could not be fixed in place: it is the wrong
architecture for this machine, its agent is a per‑question subprocess around
a 0.6 B model, and the missing features are the product. I rebuilt LLM OS for
Apple Silicon (and any arm64 host with KVM/HVF) from official sources only,
keeping the same idea — a bootable Alpine image with an on‑device model and a
text console — and implementing the brief. See `dist/README.md` for what it
does and how to run it, and `BUILD.md` for how it was built and tested.
