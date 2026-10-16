# Magnitude (magnitude.dev) on the real laptop, 2026-10-16

Owner's link: Magnitude, an Apache-2.0 inference engine that tunes kernels per machine ("2x faster than Ollama";
Apple Silicon, NVIDIA CUDA, AMD and other GPUs through Vulkan, or CPU). OpenAI-compatible API on port 10100,
GGUF models (its catalog: Gemma 4, Qwen3.5, LFM2.5, MiniCPM, Nemotron).

## What was tried
- Alpine/musl is not supported (glibc 2.34+ only). It was run in a Debian trixie folder (debootstrap) on the
  spare laptop (i7-1260P, Iris Xe, 16 GB), the 0.2.9 .deb installed there (the CLI tarball alone refuses:
  "not inside a complete Magnitude installation").
- It found the Iris Xe and offered "Vulkan GPU acceleration"; catalog estimate for Gemma 4 E4B Q4: 12-17 tok/s.
- Gemma 4 E4B (Q4 QAT): loading stayed at "Preparing" (its per-chip kernel tuning) while magnitude-inference grew
  to 13.3 GB resident for a 4.3 GB model; the kernel's out-of-memory killer ended it, after killing LLM OS's own
  llama-server three times. A first attempt ended in the laptop restarting.
- Gemma 4 E2B (2.6 GB) in a 7 GB cgroup: still "Preparing" after 11 minutes; free memory fell to 0 (the
  inference process ran outside the limit) and the laptop restarted again. No request was ever answered.
- Probing the NVIDIA card through Vulkan (nouveau) oopses the kernel (nvkm_gr_units). LLM OS ships no nouveau
  Vulkan driver, so its own stack never does this; anything that brings one in must hide the NVIDIA nodes.

## Verdict
Not integrated. On LLM OS's typical hardware (Intel built-in graphics, 8-16 GB) it does not get to a first answer
and takes the machine down while preparing; it also needs glibc. llama.cpp (Vulkan, -ub 256, MTP drafts for Gemma)
stays the engine. Worth a fresh look when Magnitude supports musl or its preparation has a memory bound; its API is
OpenAI-compatible, so llm.py would need only a base URL and model name.

The test folder (12.7 GB) was removed afterwards; nothing of it is left on the laptop.
