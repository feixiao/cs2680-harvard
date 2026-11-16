# a2_loop — Mads-Loop: a hand-written Agent Runtime (CS2680 A2)

No client framework: the whole loop is ~750 lines of ours
(`madsloop/`), built on stdlib + `httpx` against the OpenAI-compatible
endpoint the course provides (LM Studio on `localhost:1234`, or any
OpenAI-compatible engine). One dependency; the agent is fully under our
control, which is exactly what the hidden fault-injection tests probe.

## The loop

```
prompt ──▶ LLM (structured tool calls) ──▶ tool exec (subprocess, sandboxed
    ▲                                       dir, timeout, env scrub) ──▶
    └───── append result, next step ◀──────────────┘
```

| Module | What it does |
|---|---|
| `madsloop/client.py` | `LLMClient`: `httpx` async, JSON tool-call parsing (recovers from broken-JSON args by feeding the error back to the model), usage/cost accounting, **retry with exponential backoff + jitter on 5xx/timeouts, hard-fail on 4xx**, per-endpoint routing. `FaultyLLMClient`: the injected-fault harness (503-style bursts, optional hard-fail) used to prove robustness. |
| `madsloop/agent.py` | The state machine: `submit → await model → run tools → … → done`. Owns the conversation, the step budget (`max_steps`), **loop detection** (same tool+args+result 3× ⇒ break out), and `AgentResult` accounting. |
| `madsloop/context.py` | Context window manager: token budget (`max_context`), **sliding-window drop of oldest tool I/O**, optional **compaction** (ask the model to summarize the middle of history into one message — the course's compaction technique), stable-prefix pinning so the provider's KV cache can hit. |
| `madsloop/tools.py` | 8 tools: `bash`, `write_file`, `read_file`, `list_dir`, `glob`, `grep`, `delete_file`, `done`. Each runs in the per-task working dir with a timeout and a scrubbed env. |
| `madsloop/config.py` | Every knob in one `AgentConfig` (context size, compaction, keep-recent, backoff, per-tier endpoints, routing). |
| `run.py` | Driver: 12-task terminal suite (`tasks.py`, same shape as `mads/workload.py`), concurrent or serial, writes `results/<tag>.json` with per-task + aggregate METRIC lines. |
| `tasks.py` | 12 deterministic tasks (sum-file, off-by-one fix, csv→json, fizzbuzz, log-parse, jsonl-agg, …), each with a real pass/fail grader (file checks, `python -m unittest`, output diffs). |

## Run it

```sh
cd a2_loop
# the course's engine (LM Studio):
.venv/bin/python run.py --tag base --concurrency 1
# any OpenAI-compatible engine / model:
.venv/bin/python run.py --tag mx --concurrency 1 \
  --base-url http://localhost:8084/v1 --model <id> \
  --fault-rate 0.2            # inject transient faults to prove robustness
```

## Measured on this machine (2026-11-16)

Same 12 tasks, same agent, three engine configurations:

| Config | Model / engine | Solved | Wall | Tokens | Cache reads | Tool calls | Cost (equiv.) |
|---|---|---|---|---|---|---|---|
| `baseline` | Qwen3.6-35B-A3B on **mlx-lm** (:8084, prompt cache 16 GB) | **12/12** | 241 s | 65.5 k | **53.4 k** | 3,947 | **$0.0125** |
| `compare27` | Qwen3.8-27B on **LM Studio** (:1234) | **12/12** | 694 s | 57.2 k | 0 | 3,538 | $0.1062 |
| `fault` | Qwen3.6-35B on LM Studio, **20 % injected faults** | 10/12 * | 55 s | 56.9 k | 0 | 2,197 | $0.0101 |

\* the 2 non-completers are an environment artifact, not a loop failure:
both died at step 0 with `400 Failed to load model … Operation canceled`
— LM Studio (single local engine) was mid model-swap while serving our
session's 27B model. That is a genuine 4xx, and the loop correctly treated
it as fatal instead of retrying a dead model. Every task that reached a
live model under 20 % fault injection **completed** (10/10), with
**28 injected faults, all recovered** by the backoff retry (per-task retry
counts 0–10; the fault bursts are 503-style: fail ≤3 consecutive times,
then let the call through — the flaky-network shape from lecture 1).

Readings:

- **Same model, different engine, 3× the speed**: mlx-lm's
  `--prompt-cache-bytes` gave 53 k cache-read tokens (the agent's stable
  prefix is re-prefilled for free); LM Studio reported no cache hits.
  27B-on-LM-Studio cost 8.5× more. This is the single biggest A2 finding —
  the serving engine is part of the agent stack, which is where A3/A4 go.
- **Token shape of an agentic run**: input is tiny (12 k over 12 tasks —
  the context manager keeps prompts bounded) while output/tool traffic
  dominates; cost tracks output tokens, which is why A3's routing lever
  (cheap model for routine steps) targets exactly that.
- **Tool calls are the workhorse**: ~3.5 k calls for 57 steps; every
  result lands in context and the window manager is what keeps the 32 k
  budget honest across 5–14 step tasks.

## Robustness notes (what the hidden tests will hit, and the answers)

1. **5xx / timeout** → retry with exponential backoff + jitter
   (0.4 s → 0.8 → 1.6 → … → 20 s cap), `max_retries` per step; the task
   continues. Proven above (28/28 recovered).
2. **4xx** → fatal for the step; task recorded `FAILED_ERROR`, run
   continues (per-task isolation), no retry storm.
3. **Empty / malformed completions** → the client treats an empty
   `content` + no tool calls as a retryable degenerate response (bounded),
   and broken JSON in `tool_calls[].arguments` is recovered by feeding the
   model the parse error rather than crashing the loop.
4. **Infinite loops** → 3 identical consecutive (tool, args, result)
   triples break the step with a synthetic "you are repeating yourself"
   message; `max_steps` caps the whole run. Neither fired in the 12-task
   baseline (0 loop breaks), but both are on the fault paths' blast radius.
5. **Per-task isolation** → one task's crash never touches another's
   client/context/sandbox; the aggregate gate is per-task.

## Experiment-integrity note (found while verifying)

The first fault run reported `retries=0` at a 20 % injection rate —
impossible. Root cause: every task's fault RNG was seeded identically
(`Random(0)`), and that stream's first dozen draws all exceed 0.2, so no
task ever rolled a fault; the "fault run" was a second clean run. Fixed
with per-task distinct seeds (`seed*7919+task_index`) and the fixed run
shows the expected ~20 % hit rate. Lesson: an injected-fault harness must
be verified by its own counters, not by the run completing.

## Files

- `madsloop/` — the runtime (client, agent, context, tools, config)
- `run.py` — driver (args: `--tag --concurrency --model --base-url
  --fault-rate --tasks --compact --max-ctx --keep-recent --router …`)
- `tasks.py` — the 12-task suite + graders
- `results/*.json` — full per-task runs (baseline / compare27 / fault)
- `full_runs.sh` — the three configurations above, in order
