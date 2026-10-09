# Task queue (LLM OS buildout)

Owned by llmos-orchestrator. One line per task. Status: open, running, done, failed.

- [running] Finish the 1.7.1 image build with the security toolkit; check-fresh must say FRESH; package and smoke-test it.
- [open] Make computer control fast and smart: AT-SPI accessibility for buttons and fields, OCR only as a fallback. Test: open the calculator, press 7 + 2 =, read 9.
- [open] Run docs/research/basic-sweep.md on the VM; read every reply; fix each failure with a test.
- [done] Give the Hermes/Ministral default decision a written verdict in docs/research/model-bakeoff.md. Evidence: verdict section appended; grounded in run/bake-hermes + run/bake-ministral (read by hand). ux-grade Hermes "Flag counts: LECTURE 1, SLOW 1 / Clean 13 of 15" but hand-read shows 5 confabulations (Q05,Q06,Q07,Q10,Q13) -> keep Ministral.
