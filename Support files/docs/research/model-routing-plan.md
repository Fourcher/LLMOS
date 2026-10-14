# Picking a model per task: plan (2026-10-13)

The owner asked for the OS to choose the best model for each task, the way Perplexity's agent does, and to suggest downloading a model that is faster or better at something. This is the plan. Nothing here is built yet.

## Where things stand
- **One on-device model at a time.** Setup picks Fast, Balanced or Most capable from the machine's memory (`desk.py _model_tiers`). There is an optional online model, and `agent.py` already routes between on-device and online with a one-step yes/no from the model (`llm.decide`, ROUTE_QUESTION).
- **Many requests skip the model entirely.** The instant lanes (`intent.py`, `everyday.py`, the desk's shortcuts) handle them. Those are milliseconds; anything that reaches the model costs seconds to minutes on a CPU.
- **Cost is mostly reading, not writing.** Each request sends a ~1,400-token system prompt plus a ~6,000–7,000-token tool list (76 tools, ~25,000 characters). A cold read of that on a laptop CPU is the multi-minute wait the owner saw. Ask mode (no tools) already cuts it to ~1,400 tokens.
- **The catalog lists 12 models** with speed and memory notes (`usr/share/llmos/catalog.json`). `docs/research/model-bakeoff.md` and `tools/decide-eval.py` measure some of them. The measurements aren't yet broken down by kind of task.

## The plan, in order (each step pays off on its own)
1. **More requests never reach a model.** Every request the model handles that a phrase rule could have handled is waste. The settings delay was one. A nightly check runs the use-case lists and flags each request that went to the model but ended in a single built-in action, so it becomes a phrase rule.
2. **Smaller prompts per request.**
   - Ask mode is done.
   - Next, offer only the tools that fit the request. `tool_schemas(text)` already has groups; every request still gets all 76 today.
   - Keep the reused part of the prompt in the same order every time, so the model server's prompt cache covers it. Warm-up already does this for the system prompt.
   - Target: a typical "do" request reads under 2,500 new tokens.
3. **Two models when memory allows (16 GB or more).**
   - A small fast model (Gemma 4 E2B or Ministral 3B, ~3 GB) stays loaded. It answers Ask-mode questions, routes, and does one-step actions.
   - The larger model (8B to 14B) is loaded only for multi-step work: tools over several steps, writing, research.
   - llama-server runs one model per process, so this means two processes on two ports. The router (`agent.py`) sends a request to one of them by kind:
     - one built-in action
     - a question
     - a multi-step task
     - writing
     - code
     - another language
   - Below 16 GB, one model, as now.
4. **Measured strengths, not guesses.**
   - Extend the bake-off to score each catalog model per task kind: the same requests, timed, judged by outcome as in the real-use test plan.
   - Store the table in the catalog: per model, per kind, the median seconds and success rate on a reference machine, scaled by the owner's own measured speed.
5. **Suggestions the owner can act on.**
   - When a kind of request is slow or failing on the current model and the table shows a better fit that fits this machine's memory, the Models page shows it. For example: "Gemma 4 E4B answers questions in other languages about 2× faster here. Download (4.6 GB)?" One button downloads it.
   - Never a pop-up mid-request, never nagging. At most one suggestion at a time, and "not interested" hides it for good.
6. **The owner stays in charge.**
   - Settings → Models gets a choice: one model / pick for me / always use this one.
   - The reply shows which model answered: the live view's "About to:" line plus the model name.

## How to tell it worked
- **Steps 1–2:** median time to first visible action for "do" requests on the reference VM. Cold should drop below 30 s; today it's minutes.
- **Step 3:** on a 16 GB machine, Ask-mode answers in under 5 s warm. Multi-step success rate is unchanged or better.
- **Steps 4–5:** a suggestion only appears when its measured gain is at least 1.5× speed, or 10 points of success rate, on that task kind.
