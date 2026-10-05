# LLM OS

> **Just want to use it?** Open the **`dist`** folder and double-click the
> **"1 - START HERE"** file for your computer (Mac, Windows or Linux). It opens
> **LLM OS Setup**, which recognises your computer and walks you through
> trying LLM OS in a window, making a USB stick, or installing it.
>
> **Prefer an AI to guide you?** Give **`dist/2 - Set up with AI.md`** to Claude,
> ChatGPT or another assistant and say *"Read this and help me set up LLM OS."*
>
> To share LLM OS with someone, give them the `dist` folder (zipped or not):
> everything they need is in it, starting with those two files.

An operating system whose only interface is a language model running on the
machine itself. No apps, no menus: you say what you want, in words, and the
computer does it, drawing whatever needs showing as a window. Private by
construction (nothing leaves the machine unless you ask for something from
the internet), simple, and built to be the opposite of attention‑harvesting
software.

Private by construction is the default, not the only way to run it. The
first-run set-up is six sliders, and one of them, *where it thinks*, chooses
between answering only on this computer, asking before a big request goes to
an online model such as Claude, or letting that online model answer
everything (with this computer answering when it can't be reached). The
others set how much it asks before acting, the internet policy, the size of
the on-device model, whether it follows your instructions on your own machine
without lectures or keeps a standard assistant's caution, and how lively the
screen is. Each slider maps to a setting you can change later in words, and
every request that leaves the computer is written to the audit log.

- `src/` — the OS: an Alpine Linux base plus `src/rootfs/` (the Python OS,
  about 9 000 lines, no third‑party libraries) and `src/install.sh`, the
  script that builds an image from the official Alpine ISO. `src/live/` is
  the live‑ISO boot.
- `tools/` — the build and test tooling (QEMU drivers, smoke tests, the
  installer and hardware‑matrix tests, the ISO builder).
- `dist/` — what a user gets, and what to share: the **"1 - START HERE"**
  launchers and **LLM OS Setup** (`dist/setup/`: recognises the computer, runs
  LLM OS in a window, saves the ISO, writes a USB stick, shows install and
  dual-boot steps), **"2 - Set up with AI.md"** (a prompt that lets any AI
  assistant guide the setup), the images and ISOs, the model catalog,
  `RELEASE.json` and `SHA256SUMS`.
- `BUILD.md` — how it was built, every source and hash, the design in one
  page, the brief checked point by point, measured hardware requirements
  and the full test record. `CHANGELOG.md` — versions. `AUDIT.md` — how to
  audit and verify it. `VERSION` — the current version.

## Build it yourself

On an Apple Silicon Mac with Homebrew QEMU: `tools/build-image.sh` makes the
arm64 image, `tools/build-image-x86.sh` the x86‑64 image (emulated, slower),
`tools/build-iso.sh arm64|x86` the live ISOs. Each run starts from the
official Alpine ISO (hash in `BUILD.md`), installs signed Alpine packages,
copies `src/rootfs/` in, fetches the default model from its publisher's
repository and checks its SHA‑256, and writes `dist/SHA256SUMS` and
`dist/RELEASE.json`. `tools/desk-smoke.sh`, `tools/x86smoke.sh` and
`tools/isosmoke.sh` boot the results and exercise them; `tools/test-intent.py`,
`tools/test-uispec.py`, `tools/test-cloud.py` (the online-model client
against fake services, no network) and `tools/test-routines.py` run on the
host without a VM; `tools/brain-smoke.sh` drives the quiz, the online route,
routines and the desk layouts inside the test VM against `tools/fake-cloud.py`.

## Run it

Double-click `dist/1 - START HERE` for your computer: LLM OS Setup takes it
from there (in a window with UTM, VirtualBox or Boxes; on a Mac with Homebrew
QEMU, `dist/run-llmos.sh` with the model on the Mac's GPU; or from a USB stick
it writes, then install from the running desk by saying so). The user guide is
`dist/README.md`.

## License

Apache License 2.0 (see `LICENSE`). The base system is Alpine Linux and
its packages under their own licenses (recorded per image in
`/etc/llmos/packages.txt` inside each image); llama.cpp and whisper.cpp are MIT; each model in
`dist/catalog.json` carries its publisher's license.
