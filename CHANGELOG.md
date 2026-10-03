# LLM OS changelog

Versions are in `VERSION`; every image and ISO carries its version in
`/etc/llmos-release` (`llmos version` prints it, Settings shows it) and
`dist/RELEASE.json` lists what a release contains with checksums.

## 1.2.0 — 2026-10-03
- Bootable live ISO for PCs (BIOS + UEFI) and arm64 UEFI machines: runs LLM OS
  from a USB stick, installs to the internal disk from the running desk.
- The Exporter app (`dist/exporter`): one click on macOS, Windows or Linux to
  save the ISO, write it to a USB stick, or read the install / dual-boot steps.
- Version tracking (this file, `VERSION`, `RELEASE.json`, `/etc/llmos-release`).
- Desk: system windows share one slot on the right; overlapping windows go
  solid; a reply that opened a window folds at once; two-column "Try saying";
  plain activity names; keyboard focus rings; relative times on notes.

## 1.1.0 — 2026-10-01
- Lists and notes, timers and reminders (delivered word for word, with a chime),
  auto-lock, trash restore / empty, "set up a passphrase" after first boot,
  brightness and volume by voice, Super+Left/Right snapping.
- Hardening: supervised model and scheduler services, no RAM prompt cache,
  long requests clipped and retried, the lock really unmounts the vault
  (ephemeral WebKit session, caches outside the vault, programs closed first,
  passphrase verified against the header), VM lifetime guards in the tooling.

## 1.0.0 — 2026-09-28
- Graphical desk with the presence orb, animations (Full / Reduced / Off),
  first-run wizard, windows generated from specs, files and screenshots,
  host-GPU mode, installers (alongside / whole disk), x86-64 and arm64 images.
