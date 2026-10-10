# Trustworthy screen-level e2e tests for a desktop OS: assertions, flakiness control, triage

Scope: how to check what is on screen in a VM desktop test, how to keep those tests stable, and how to turn failures into a ranked fix list that an orchestrator can hand to cheap worker agents. Researched 2026-10-09. Where a number comes only from a secondary source, the note says so.

## (a) How to assert what is on screen: openQA needles, OCR, visual diff, VLM judges, and state checks

### Takeaway
Pixel and template matching works, but it breaks easily. openQA's needles are reference screenshots matched area by area against a similarity percentage, and Fedora's history shows one font-library update can invalidate most text needles. The most reliable assertion is a machine-readable state check: a file, a process, an accessibility tree, a DOM, or a command run inside the VM. Use OCR or pixels only where no state is exposed. Use a VLM judge only as a high-recall second opinion: even the best judges reach about 70% precision against expert labels.

### Cited Findings

**openQA / os-autoinst needles**
- A needle is a full PNG screenshot plus a JSON file with the same name. The JSON has `area` (a list of objects with `xpos`, `ypos`, `width`, `height`, `type`, and optional `match` and `click_point`) and `tags` (strings that say when the needle applies). — [openQA docs, Basic concepts > Needles](https://open.qa/docs/)
- Area `type` is `match`, `ocr` or `exclude`. `match` is an integer 0–100, a "similarity percentage" the area must reach. `exclude` areas mask parts of the reference image. OCR areas are "only rarely used". — [openQA docs](https://open.qa/docs/)
- If a needle has several click points, pass the point's `id` to `assert_and_click`. — [openQA docs](https://open.qa/docs/)
- Contributors, reading the source code, put the default similarity threshold at 96%. It is set per area, so there is no needle-level "relative" match level. The official docs do not confirm 96%. — [progress.opensuse.org #96555](https://progress.opensuse.org/issues/96555)
- Areas are matched independently, so one area can match several places on a screenshot. `assert_and_click` clicks only in the last match area. — [progress.opensuse.org #45746](https://progress.opensuse.org/issues/45746); [progress.opensuse.org issue list](https://progress.opensuse.org/issues/47222)
- The UI once showed 100% for a needle whose area matched at 98%. It was changed to show the real per-area value. — [progress.opensuse.org #45746](https://progress.opensuse.org/issues/45746?tab=notes)
- `assert_screen` waits for a needle with the given tag. It returns as soon as a match succeeds, so a long timeout does not slow a passing check. — [open.qa testapi](https://open.qa/api/testapi/)
- A maintainer said the "area margin" option is "very difficult to use" for controlling matching. — [progress.opensuse.org search results](https://progress.opensuse.org/issues/31198?tab=notes)
- Fedora's lessons on fragility:
  - FreeType 2.6.2 changed font rendering "quite significantly", and most text needles had to be redone. — [os-autoinst-distri-fedora commit log](https://git.almalinux.org/srbala/os-autoinst-distri-fedora/commits/branch/main?page=68)
  - On Rawhide, text drawn "a pixel taller" broke matches on the user-creation screens. — [Fedora qa-devel, "openQA vs. Rawhide", July 2015](https://lists.fedoraproject.org/pipermail/qa-devel/2015-July/001281.html)
  - Fixes included dropping the part of the screen that varies (an inconsistent gap) from the match area, and removing text-label matches because they "only serve to make the needle more fragile".
  - The team kept variant needles per screen rather than replacing old ones. Needles for screens changed by a GTK+ bug got "bug" in their names so they would be revisited.
  - These fixes appear in the same commit logs. — [os-autoinst-distri-fedora commits](https://git.almalinux.org/srbala/os-autoinst-distri-fedora/commits/branch/dnf5?page=68)

**OCR (Tesseract and alternatives)**
- Tesseract works best at 300 DPI or higher, so resizing may help. — [Tesseract docs: ImproveQuality](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
- It binarizes internally with Otsu, which does poorly on uneven backgrounds. 5.0.0 added Adaptive Otsu and Sauvola (`tesseract --print-parameters | grep thresholding_`). — [Tesseract ImproveQuality](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
- Tesseract 4.x and later expect dark text on a light background, so light-on-dark UI crops should be inverted. — [Tesseract ImproveQuality](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
- Tightly cropped text needs a small border (the example uses 10 px). A very large border can return an empty page. In Tesseract 4, alpha is blended against white, which can cause problems, so remove alpha first. — [Tesseract ImproveQuality](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
- Page segmentation modes (`--psm`): default 3 (fully automatic). 6 = one uniform block, 7 = one text line, 8 = one word, 11 = sparse text, 13 = raw line. — [Tesseract ImproveQuality](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
- For non-dictionary strings, set `load_system_dawg` and `load_freq_dawg` to false. Use `tessedit_char_whitelist` when the character set is known, such as digits. User patterns and word lists can also raise accuracy for expected strings. — [Tesseract ImproveQuality](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
- Upscaling whole screenshots to 300 DPI used most of the CPU across parallel jobs (one user's report). Crop before scaling. — [OCRmyPDF discussion #1298](https://github.com/ocrmypdf/OCRmyPDF/discussions/1298)
- Small UI fonts OCR poorly. A Sikuli answer resized a screenshot to about 300 DPI and saw better results with slightly larger fonts. — [sikuli-driver mailing list](https://archive.lists.launchpad.net/sikuli-driver/msg51152.html)
- PSM choice changes accuracy a lot and should be measured on samples. — [PyImageSearch: Tesseract PSMs explained](https://pyimagesearch.com/2021/11/15/tesseract-page-segmentation-modes-psms-explained-how-to-improve-your-ocr-accuracy/)
- Apple Vision OCR on the macOS host, from the command line:
  - `mac-ocr` (npm, macOS 10.15+, batch `mac-ocr *.png`, fully local). — [privatenumber/mac-ocr](https://github.com/privatenumber/mac-ocr)
  - `vocr` (`-a accurate|fast`; last commit 2022). — [srirangav/vocr](https://github.com/srirangav/vocr)
  - A minimal Swift `VNRecognizeTextRequest` script. — [alexwlchan get_live_text.swift](https://alexwlchan.net/projects/get_live_text/raw/get_live_text.swift)
  - Use `recognitionLevel = .accurate`, language correction, and explicit recognition languages. — [same sources](https://github.com/ughe/macocr)

**Visual regression / perceptual diff**
- Playwright `toHaveScreenshot`:
  - `threshold` (per-pixel color tolerance, 0–1) defaults to 0.2. `maxDiffPixels` is unset by default.
  - It takes screenshots until two in a row match, so the screen settles before comparing.
  - Baselines are named per browser and platform (for example `chromium-darwin`) and are refreshed with `--update-snapshots`.
  - Move the mouse away first (for example `page.mouse.move(-1,-1)`) to avoid hover states.
  - `stylePath` applies CSS that hides dynamic elements.
  - Source: [Playwright: Visual comparisons](https://playwright.dev/docs/test-snapshots)
- Playwright defaults: `animations: "disabled"`, `caret: "hide"`, `scale: "css"`. `mask` paints given locators with `maskColor` (default pink #FF00FF). `maxDiffPixelRatio` and `timeout` come from `TestConfig.expect`. — [Playwright PageAssertions API](https://playwright.dev/docs/api/class-pageassertions)
- pixelmatch defaults:
  - `threshold: 0.1`
  - `includeAA: false`: anti-aliased pixels are detected and ignored, using Vyšniauskas 2009, "Anti-aliased Pixel and Intensity Slope Detector".
  - `ignoreMask`: per-pixel exclusion.
  - `windowSize`: returns the worst N×N window count instead of the total, useful for catching a small local change.
  - Source: [mapbox/pixelmatch](https://github.com/mapbox/pixelmatch)

**VLM/LLM as judge vs. state checks**
- AgentRewardBench: 1302 web-agent trajectories across 5 benchmarks and 4 agent LLMs, labeled by experts (success, side effects, repetition), with 12 LLM judges evaluated. — [AgentRewardBench, arXiv 2504.08942](https://arxiv.org/html/2504.08942v2)
- Overall precision / recall / F1 on the success label (Table 1). — [AgentRewardBench](https://arxiv.org/html/2504.08942v2)

  | Judge | Precision | Recall | F1 |
  |---|---|---|---|
  | Rule-based (official) | 83.8 | 55.9 | 67.1 |
  | GPT-4o (accessibility tree) | 69.8 | 83.1 | 75.9 |
  | Claude 3.7 Sonnet (accessibility tree) | 68.8 | 81.6 | — |
  | Claude 3.7 Sonnet (screenshot) | 69.4 | 76.3 | — |
  | Qwen2.5-VL (accessibility tree) | 64.3 | 89.8 | — |

- No LLM judge exceeds 70% precision, so about 30% of the runs a judge calls successful are not. LLM judges overestimate success. Rule-based checks underestimate it. No single judge leads on every benchmark. — [AgentRewardBench](https://arxiv.org/html/2504.08942v2)
- Input ablation with GPT-4o mini (Table 2):
  - Screenshot only: P 64.5 / R 78.3
  - Accessibility tree only: P 61.5 / R 86.1
  - Both: P 62.1 / R 81.7
  - Neither: P 60.7 / R 73.9

  Giving both inputs did worse than the screenshot alone. — [AgentRewardBench](https://arxiv.org/html/2504.08942v2)
- The paper recommends one simple judge prompt that answers success, side-effect and repetition in a single completion, with precision put first when judgments are used as rewards. — [AgentRewardBench](https://arxiv.org/html/2504.08942v2)
- OSWorld sets up each task in three stages:
  1. Revert the VM to a snapshot.
  2. Optionally download task files to the host and upload them to the VM.
  3. Run task-specific preprocessing.

  Scoring is done by execution-based evaluator scripts that inspect the final state, not by a judge. — [OSWorld, arXiv 2404.07972](https://arxiv.org/pdf/2404.07972)
- Per-task init configs let a task start mid-workflow, for example with an app already open. — [AgentHijack, arXiv 2605.25707](https://arxiv.org/pdf/2605.25707)

### Inferences
- **Order of preference for a cheap-worker orchestrator:**
  1. State check inside the VM: a guest command, file or config contents, `systemctl`/process state, D-Bus or the AT-SPI accessibility tree, or a browser DOM.
  2. OCR of a cropped region against an expected string, using a fuzzy or normalized compare.
  3. Template or needle match with `exclude` masks.
  4. Perceptual full-screen diff for "nothing else changed" checks.
  5. A VLM judge only to flag runs for review, never as the only pass/fail gate.

  AgentRewardBench's 84% precision for rules against about 70% for judges supports keeping deterministic checks as the gate, and using the judge's higher recall to catch what the rules miss.
- **Suggested OCR recipe** (my synthesis of the Tesseract guidance above):
  1. Crop the known region.
  2. Upscale 2–4×. Lanczos is a common choice, but that is my assumption, not sourced.
  3. Invert dark themes.
  4. Add a 10 px white border.
  5. Use `--psm 7` for one line, or `--psm 6` for a block.
  6. Turn the dictionary off for identifiers, and whitelist characters where possible.
  7. Compare after lowercasing and collapsing whitespace, with an edit-distance tolerance.
- **Needle hygiene from Fedora's experience:**
  - Keep match areas small and distinctive: an icon plus a short label, not a whole dialog.
  - Exclude variable gaps, clocks, cursors and fonts that change.
  - Keep variant needles rather than replacing them.
  - Tag needles that encode a bug ("bug"/workaround) so they get revisited.
  - Re-baseline as a batch after font, theme or toolkit updates.
- **Diff thresholds:** pixelmatch's 0.1 default and Playwright's 0.2 are per-pixel color tolerances. Full desktops also need a pixel-count budget (`maxDiffPixels`/ratio) and masks over the clock, the cursor, notification areas and blinking carets. Baselines should be keyed by resolution, theme and font package version.

### Gaps
- I did not fetch the full openQA "Needle editing" pitfalls page, and I could not confirm the 96% default match level in the docs. It comes from contributors reading the source.
- I found no measured accuracy numbers for Tesseract, PaddleOCR or Apple Vision on UI screenshots. One comparison said Tesseract is weaker than PaddleOCR under 15° rotation and heavy noise, but I did not verify the primary source. PaddleOCR specifics were not researched.
- SSIM and dHash thresholds for desktop screenshots were not researched. I found no authoritative recommended values.
- I found no published false-positive rates for VLM judges on full desktop (non-web) screenshots. AgentRewardBench covers web only.
- I could not verify the "134 evaluation functions" figure for OSWorld.

## (b) How to keep VM-based e2e tests stable

### Takeaway
Most flakiness comes from timing: async waits, followed by concurrency and test-order dependence. At scale even a small flake rate dominates the signal. At Google, 1.5% of runs were flaky, 16% of tests had some flakiness, and 84% of pass-to-fail transitions involved a flaky test. The fixes:
- Wait for conditions instead of sleeping.
- Disable animations and carets.
- Start every test from a snapshot.
- Retry only tests marked flaky, and quarantine tests below a consistency bar.
- Make on-device LLMs as deterministic as possible: temperature 0, a fixed seed, a pinned build, single-stream inference. Even then, assert on properties of the output, not exact text.

### Cited Findings
- **Google, 2016:**
  - About 1.5% of all test runs were flaky, and almost 16% of tests showed some flakiness.
  - Flakiness means a test both passes and fails on the same code.
  - Causes include concurrency, non-deterministic or undefined behavior, flaky third-party code and infrastructure problems.
  - Source: [Google Testing Blog, May 2016](https://testing.googleblog.com/2016/05/)
- Google's follow-up figure is that about 84% of observed pass-to-fail transitions involved a flaky test. This number came via a secondary summary. — [Google Testing Blog (John Micco label)](https://testing.googleblog.com/search/label/John%20Micco); summarized in [quashbugs flaky stats](https://quashbugs.com/blog/flaky-test-statistics)
- Google's rerun mechanism is used only for tests marked flaky or when a user asks. Flakiness is tracked separately for each flag/configuration combination. Google had no publishable cost data. — [Google Testing Blog post comments](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html)
- Practitioners in the same thread describe:
  - running new tests in a loop for a week in a "Reservoir" outside the gating path;
  - moving tests below a consistency level out of gating into a reliability suite;
  - re-running once and failing only on two failures in a row.

  — [same post, comments](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html)
- **Luo et al., FSE 2014** (201 flaky-test-fixing commits in Apache projects):
  - Async wait is about 45% of flaky tests, concurrency about 20%, test order dependency about 12%.
  - 54% of async-wait flakes were fixed by waiting for the event (waitFor) instead of a fixed sleep.

  These figures come from secondary summaries and were not verified against the paper. — [paper PDF copy](https://huang.isis.vanderbilt.edu/cs8395/paper/flakytest.pdf); [secondary summary](https://www.getpanto.ai/blog/flaky-test-statistics)
- **Microsoft (Lam, Godefroid, Nath, Santhiar, Thummalapenta):**
  - A small number of distinct flaky tests can cause a large share of failing builds.
  - Ignoring flaky failures is dangerous because they can be real product bugs.
  - RootFinder logs runtime properties and diffs the logs of passing and failing runs to find the root cause.

  — [Microsoft Research: Root Causing Flaky Tests in a Large-Scale Industrial Setting](https://www.microsoft.com/en-us/research/publication/root-causing-flaky-tests-in-a-large-scale-industrial-setting/)
- Across five projects in one month, 4.6% of individual test cases were flaky. — [Lam et al. 2019, RootFinder PDF](https://cs.gmu.edu/~winglam/publications/2019/LamETAL19RootFinder.pdf)
- A review notes that rerun-based detection is only a partial solution. — [Qualitative study of flaky tests, arXiv 2112.04919](https://ar5iv.labs.arxiv.org/html/2112.04919)
- Playwright's built-in stability measures:
  - It waits until two consecutive screenshots match.
  - Animations are disabled and the caret hidden by default.
  - Baselines are kept per platform.

  — [Playwright visual comparisons](https://playwright.dev/docs/test-snapshots); [Playwright PageAssertions](https://playwright.dev/docs/api/class-pageassertions)
- `assert_screen` returns as soon as a match succeeds, so generous timeouts cost nothing on passing runs. — [open.qa testapi](https://open.qa/api/testapi/)
- OSWorld makes runs repeatable by reverting a VM snapshot for every task. — [OSWorld](https://arxiv.org/pdf/2404.07972)
- **LLM nondeterminism:**
  - Temperature 0 makes only token selection deterministic.
  - The main cause of nondeterministic inference is kernels that are not batch-invariant: results change with the batch a request lands in, not with GPU thread races.
  - Batch-invariant kernels gave bitwise-identical output over 1,000 runs (secondary report; its ~34% overhead figure is unverified).

  — [OpenAI community thread on "Defeating Nondeterminism in LLM Inference"](https://community.openai.com/t/defeating-nondeterminism-in-llm-inference/1358623); [batch-invariant kernels write-up](https://mohakchugh.is-a.dev/blog/batch-invariant-kernels-deterministic-llm-inference)
- llama.cpp: temperature 0 always picks the most likely token. With temperature above 0, a fixed `seed` makes server output deterministic again. — [llama.cpp commit #4668](https://cdn04132025.gitlink.org.cn/replica/llama.cpp/commit/65e5f6dadbba4b496bba27f573e473c66b446496)
- Ollama needs both `temperature: 0` and a fixed `seed` for reproducible output. — [makandra: Ollama deterministic results](https://makandracards.com/makandra/626358-ollama-generate-deterministic-results)

### Inferences
- **VM desktop stability checklist** (synthesized from the sources above):
  1. Revert a snapshot per test or test group.
  2. Pin resolution, theme, fonts and locale.
  3. Turn off desktop animations, cursor blink and screen blanking.
  4. Hide the clock, or freeze the guest time.
  5. Replace every `sleep` with a poll for a condition (needle, OCR text, guest command), with an explicit timeout budget.
  6. Before any screenshot assertion, require two identical frames in a row.
  7. Keep host load bounded: a fixed number of VMs per host and pinned vCPUs. This addresses resource contention.
- **Retry and quarantine policy for the orchestrator:**
  - Rerun a failure once on a fresh snapshot.
  - Pass then fail = "flaky": record it and do not gate.
  - Two fails in a row = "real".
  - Quarantine a test whose 7-day pass rate on unchanged code drops below a set bar. A 95% bar is my suggestion and is not sourced.
  - Still file quarantined failures, because Microsoft found flaky failures can be real bugs.
- **On-device LLM inside the OS:**
  - Run tests with temperature 0, a fixed seed, a pinned model file and build, and a single inference slot (no concurrent batching).
  - Assert on properties, not exact text: the right tool was called, the final system state is correct, the reply contains or does not contain key facts.
  - Run each LLM-dependent case N times (for example 3–5) and report a pass rate, not a single bit.

### Gaps
- I could not access Luo et al.'s primary text to confirm the 45/20/12 split.
- I found no published data on flakiness specific to VM desktop GUI tests, such as openQA's internal flake rates.
- I found no primary Google figure for how much compute retries cost.
- I could not confirm that llama.cpp's kernels are batch-invariant, so bitwise determinism across different batch or slot configurations is unverified.

## (c) How to triage failures into a ranked fix list

### Takeaway
Group failures by a normalized signature so N failures become K distinct problems. For stack traces there is TraceSim (TF-IDF + Levenshtein + ML) and embedding approaches. For GUI tests the signature can be failing step + expected-assertion tag + normalized error text. Rank groups by severity × frequency × (1 − flake probability). Attach a minimal repro bundle to each group.

### Cited Findings
- TraceSim combines TF-IDF, Levenshtein distance and ML into a stack-trace similarity metric. It was deployed in an industrial crash-report triage system and beat baselines on labeled data. — [TraceSim, arXiv 2009.12590](https://arxiv.org/pdf/2009.12590)
- JetBrains' deduplication pipeline embeds traces (byte-pair encoding plus approximate nearest neighbor search), then reranks by shared frames. It is evaluated on speed and on whether it creates new categories correctly, not only on accuracy. — [Stack Trace Deduplication, arXiv 2412.14802](https://arxiv.org/html/2412.14802v1)
- A failure triage engine that clusters error-trace signatures with ML reported about 93% average accuracy in preliminary experiments. — [Poulos, Yang, Veneris, IOLTS 2013](https://www.eecg.utoronto.ca/~veneris/13iolts2.pdf)
- Affinity Propagation binning reached about 87% average accuracy on four industrial designs, and the same work also prioritizes which bins to debug first. — [Veneris group, LATS 2015](https://www.eecg.utoronto.ca/~veneris/15lats.pdf)
- Failure clustering using execution profiles groups failing tests by the bug that caused them and can suggest duplicate bug reports. — [UC Irvine ISR: Failure Clustering](https://isr.uci.edu/node/1635.html)
- Failure de-duplication can help decide whether a new failure is flaky. The study compares stack-trace text matching, an ML Failure Log Classifier and TF-IDF grouping. — [arXiv 2401.15788](https://ar5iv.labs.arxiv.org/html/2401.15788)
- An industry patent hashes stack-trace summaries into signatures and links each cluster to one test-failure record. It compares error types, messages, hashed traces and file names. — [USPTO 10552296](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10552296)
- RootFinder diffs runtime logs between passing and failing runs to localize the cause. Logging the same properties on every run makes this possible. — [Microsoft Research](https://www.microsoft.com/en-us/research/publication/root-causing-flaky-tests-in-a-large-scale-industrial-setting/)
- A small number of flaky tests can cause many build failures. Ranking by frequency therefore puts the few worst tests first. — [Microsoft Research](https://www.microsoft.com/en-us/research/publication/root-causing-flaky-tests-in-a-large-scale-industrial-setting/)

### Inferences
- **Signature for screen tests** (my design, built from the dedup sources): `test_id | step_index | assertion_kind(needle/ocr/state/judge) | expected_tag_or_text | normalized_error` (digits, paths, timestamps and PIDs stripped). Hash it to get a cluster key. If the hash misses, fall back to TF-IDF or edit-distance similarity, in the spirit of TraceSim.
- **Ranking score:** `severity_weight × distinct_runs_affected × user-path weight × (confirmed_real ? 1 : 0.3)`.
  - Severity: crash/data loss = 5, blocked task = 4, wrong result = 3, cosmetic = 1.
  - The flake discount uses the retry policy in (b).
  - The weights are illustrative, not sourced.
- **Repro bundle per cluster** (enough for a cheap worker to act without rerunning everything):
  - snapshot ID
  - step trace (actions + timestamps)
  - last 2 screenshots with the failing region boxed
  - the expected needle/OCR string
  - guest logs (journal and app log tail)
  - a one-line rerun command

  Then dispatch one cluster = one worker task. A VERIFY rerun that passes twice closes the cluster.
- **Test-impact analysis:** map changed files to the tests that cover them, and rerun only those tests first. No source was gathered on this here, so it is an inference only.

### Gaps
- I did not research test-impact-analysis literature (for example Google TAP or Microsoft TIA) in this pass.
- I found no published severity × frequency formula specifically for GUI test triage. The scoring above is a proposal.
- Accuracy numbers for the Veneris papers come from search excerpts and were not verified in the full text.
