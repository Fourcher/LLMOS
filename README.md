# LLM OS

An operating system whose only interface is a language model running on the machine itself. No apps, no menus: you say what you want, in words, and the computer does it, drawing whatever needs showing as a window. Private by construction: nothing leaves the machine unless you ask for something from the internet.

The source, build tools and docs live in [`Support files/`](Support%20files/). Start with [`Support files/README.md`](Support%20files/README.md) for the overview and how to build and run it, and [`Support files/docs/HANDOFF-TO-NEXT-AI.md`](Support%20files/docs/HANDOFF-TO-NEXT-AI.md) for the architecture and current state.

Built images, ISOs and model files are not in the repository. `Support files/tools/build-image.sh` and the other build scripts produce them from the official Alpine ISO and the model publishers' files, checked against the hashes in `Support files/BUILD.md`.

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
