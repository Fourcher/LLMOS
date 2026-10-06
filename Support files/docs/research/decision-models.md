# Small "decision models" as a request router — measured 2026-10-05

Question: could a tiny classifier served by llama.cpp's `/v1/systemone` endpoint (build b11361+) route each request
(music / look / setting / web / files / apps / reminders / volume / system / chat) faster than the 3B model, so the
OS answers more requests without the model?

Setup: llama.cpp b11434 built in the arm64 test VM (4 cores, CPU only, `GGML_NATIVE=OFF`, armv8.2-a+dotprod+fp16 —
native detection fails on Apple M4 hosts: gcc has no SME without SVE2). 260 labelled phrases from the use-case runs
(`run/decision-cases.json`), one `choice` question with a one-line description per label (`run/decision-eval.py`).

| model | size (Q8) | memory | accuracy | median | p90 |
|---|---|---|---|---|---|
| Julia-1 (mmBERT-small, Apache-2.0) | 168 MB | 330 MB | 64/260 = 25% | 62 ms | 72 ms |
| Laya (ModernBERT 0.4B, Apache-2.0) | 449 MB | 870 MB | 115/260 = 44% | 232 ms | 283 ms |

For comparison, the OS's own word routes (`intent.match` plus the desk's instant lanes and `everyday.py`) answer
these phrases at once and pass `tools/test-intent.py` 270/270; anything they don't cover goes to Ministral 3B.

Typical mistakes: Julia-1 calls most requests "setting" ("music", "install spotify", "use dark mode"); Laya
confuses neighbouring labels ("turn on night light" → system, "bigger text please" → setting, "uninstall spotify"
→ music). Zero-shot with label descriptions is not enough for either; both would need fine-tuning on our phrases.

Verdict: not adopted. A wrong route is worse than a slow one (the request goes to the wrong handler), and at 25–44%
neither is close. Worth a second look only if a fine-tuned checkpoint for OS commands appears, or if we train one
ourselves from the labelled use-case phrases.
