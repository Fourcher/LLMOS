# Task queue (LLM OS buildout)

Owned by llmos-orchestrator. One line per task. Status: open, running, done, failed.

- [done] Finish the 1.7.1 image build with the security toolkit; check-fresh FRESH; package and smoke-test it. Evidence: check-fresh "FRESH: dist/ was built from the current OS source (d53d280, v1.7.1)"; SHA256SUMS -c all OK (both arches + model); arm64 ISO smoke "test shell up after 14 s ... VERSION=1.7.1 ARCH=aarch64 MEDIUM=live ... desk socket: yes"; x86 ISO smoke (UEFI) "test shell up after 24 s ... VERSION=1.7.1 ARCH=x86_64 MEDIUM=live ... desk socket: yes"; package.sh -> "/Users/jordan/Desktop/LLM OS 1.7.1.zip (7.2G)". NOTE: recovered from a worker that launched two concurrent x86 builds + a self-matching waiter; killed them, rebuilt x86 cleanly (no new downloads, secureboot chain cached).
- [open] Make computer control fast and smart: AT-SPI accessibility for buttons and fields, OCR only as a fallback. Test: open the calculator, press 7 + 2 =, read 9.
- [open] Run docs/research/basic-sweep.md on the VM; read every reply; fix each failure with a test.
- [done] Give the Hermes/Ministral default decision a written verdict in docs/research/model-bakeoff.md. Evidence: verdict section appended; grounded in run/bake-hermes + run/bake-ministral (read by hand). ux-grade Hermes "Flag counts: LECTURE 1, SLOW 1 / Clean 13 of 15" but hand-read shows 5 confabulations (Q05,Q06,Q07,Q10,Q13) -> keep Ministral.

- [note] Lock conflict: QEMU PID 98950 (the test VM from earlier) holds dist/llmos-arm64.qcow2 open. Stop that VM before the image build converts the image, or the build fails with 'Failed to get write lock'. The owner's orchestrator owns the build; do not kill other sessions' processes without checking.
- [note] Policy update: read Support files/docs/tasks/orchestration.md. Dispatch many disjoint llmos-worker agents in parallel; integrate and test each merge; you alone own VM and image builds.
- [done] Image lock cleared: stopped the test VM (PID 98950) that held dist/llmos-arm64.qcow2. Owner consent for stopping VMs, downloads and installs is standing.
