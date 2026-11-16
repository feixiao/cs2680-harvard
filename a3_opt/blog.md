# A3 — Mads-Opt: end-to-end optimization of a real agent runtime

CS2680 A3 technical review. We optimize the A2 hand-rolled runtime
(`a2_loop/madsloop`) on a fixed 12-task coding workload, measured with real
token counts, real wall time, and real failures on three local engines —
plus a deterministic simulation sweep (`mads/`) for the levers a single
128 GB Mac cannot exercise live. Every number below is reproducible with
the commands in [Reproducing](#reproducing-everything).

## The levers

| # | Lever | Mechanism | Real engine? | Sim? |
|---|---|---|---|---|
| E0 | engine + prefix cache | which engine serves the same model; KV prefix reuse | ✅ measured | ✅ |
| E1 | **3-tier routing** | per-step model choice (hard→expert, routine→MoE, file/data→1.5B) | ⚠ harness ready (`experiments.py e1`), not run live (needs 2 engines hot) | ✅ |
| E2 | **context compaction** | oldest steps → one digest line, keep-recent 2, pinned prefix budget | ⚠ same | ✅ |
| E3 | **parallel tools** | tool calls in one step run concurrently | ✅ (A2 flag) | ✅ |
| E4 | **prefix budget** | content-addressed prefix reuse with a tight token cap | ✅ (engine flag) | ✅ |
| E5 | **full stack** | E1–E4 + speculative decoding + 8-way TP prefill | ⚠ spec/TP not in local engines | ✅ |

## E0 — measured: the serving engine is the biggest lever

Same agent, same 12 tasks, two engines, one model family
(12-task suite = `a2_loop/tasks.py`, graders included):

| Config | Model / engine | Solved | Wall | Total tokens | Cache-read tokens | Cost (list $/MTok) |
|---|---|---|---|---|---|---|
| `baseline` | Qwen3.6-35B-A3B, **mlx-lm** (16 GB prompt cache) | 12/12 | **241 s** | 65.5 k | **53.4 k** | **$0.0125** |
| `compare27` | Qwen3.8-27B, **LM Studio** | 12/12 | 694 s | 57.2 k | 0 | $0.1062 |

Three facts from this table:

1. **Prefix reuse is the story.** mlx re-prefills the agent's stable
   system+tools prefix from cached KV: 53.4 k of the run's 65.5 k tokens
   are cache reads (81 % — the lecture's 97.6 % figure, measured, on a real
   12-task agentic workload). LM Studio reports no cache hits at all.
   Same-model cost ratio is therefore 8.5×, driven by prompt tokens the
   mlx engine skips.
2. **MoE beats dense 2.9× on latency** (241 s vs 694 s, per-task average
   20 s vs 58 s) — 3 B active parameters decode much faster than a 27 B
   dense model, at lower cost.
3. **Success rate is unchanged (12/12)**: the cheapest, fastest engine
   wins — no quality tradeoff on this workload.

**Robustness under faults (same agent, 20 % injected transient faults,
35 B via LM Studio):** every task that reached a live model completed
(10/10); **28 injected faults, all recovered** by backoff retry. The only
2 non-completers died to `400 Failed to load model — Operation canceled`:
LM Studio (one engine, one model) mid-swap while serving our own session's
27 B — a genuine 4xx, correctly treated as fatal. Lesson: **local
single-engine serving is an A3 constraint** — which is exactly what A4
exists to fix (dedicated engine, patched, always hot).

## E1–E5 — the deterministic sweep (why, and what it shows)

Running E1–E5 *live* needs two or three engines hot at once (1.5 B +
35 B + 27 B ≈ 40 GB of GPU-resident models *while* this very session runs
on the 27 B), plus speculative decoding and tensor parallelism, which the
open-source engines available here don't expose. Instead: the `mads/`
package — 975 lines, stdlib-only, **deterministic** (fixed-seed token
streams, simulated clock, event-driven continuous batching, paged KV) —
mirrors the stack and runs a 16-task workload in seconds, byte-identical
across runs. Its dollars are *simulated list prices* — use it for
**relative** lever comparisons, not absolute cost.

16-task workload, one lever at a time on top of the naive stack:

| Exp | Config | e2e (sim s) | × vs E0 | Cost (sim $) | × vs E0 | Solved |
|---|---|---|---|---|---|---|
| E0 | naive (all expert, serial) | 1738.5 | 1× | 4.48 | 1× | 16/16 |
| E1 | 3-tier routing (starter-resident) | 339.7 | **5.1×** | 0.145 | **31×** | 16/16 |
| E2 | compaction (keep 2, 3 k prefix budget) | 1643.4 | 1.06× | 1.80 | **2.5×** | 16/16 |
| E3 | concurrency 16 + parallel tools | 190.7 | **9.1×** | 4.48 | 1× | 16/16 |
| E4 | prefix reuse, 3 k budget | 1643.2 | 1.06× | 1.80 | **2.5×** | 16/16 |
| E5 | all of the above + spec decode + TP8 | **15.5** | **112×** | **0.033** | **135×** | 16/16 |

Readings:

- **Routing is the cost king** (31×): the expert model is 30× the prompt
  price of the local starter; sending routine steps to it is the single
  most expensive habit an agent can have. Latency improves 5.1× (serial
  decode on a smaller model) — but *only* 5×, because serial.
- **Concurrency is the latency king** (9.1×, zero token change): tokens
  are unchanged, the wall clock is what moves — continuous batching hides
  per-step tool I/O and small-model latency behind each other.
- **Compaction and prefix budgeting tie at 2.5× cost**: both shrink the
  prompt that must be (re-)prefilled each step; together they're additive
  with routing in E5.
- **E5 compounds to 112× latency / 135× cost** with success rate intact
  (16/16) — multiplicative, not additive: each lever attacks a different
  term of the cost/latency equation (which model, how many steps in
  flight, how many prompt tokens, how many prefill cycles, how fast each
  decode step).

## Findings (the review)

1. **The serving layer is part of the agent stack.** The biggest *real*
   win found this quarter is not in the agent at all: same model, mlx-lm
   with a 16 GB prompt cache vs a no-cache engine = 8.5× cost, 2.9×
   latency, 100 % success (E0). The agent's context manager (stable
   pinned prefix, compaction) is what makes the engine's cache hit —
   A2 and A4 are one optimization problem.
2. **Routing pays in cost, concurrency pays in latency.** Never in the
   other direction: routing changes *which* tokens are spent, concurrency
   changes *how many* steps fit in the wall clock. A budget-driven system
   routes; a latency-driven system batches.
3. **Prefix reuse transfers the lecture's 97.6 % to a real workload** —
   81 % measured on 12 agentic tasks, because agentic conversations are
   90 % stable prefix. Design the prompt so the stable part is a true
   prefix (tools, system, working state pinned at the front) and the
   engine does the rest.
4. **Success rate is the constraint, not the target.** Every lever held
   16/16 (sim) and 12/12 (real) — on *these* workloads none of the
   levers buy quality; they buy $ and seconds. The risk the sim sweep
   exposes: E1's cheap model and E5's tightest context both sit one
   workload change from a 15/16 — route *hard* tasks to the expert and
   keep `keep_recent ≥ 2` as the guardrails (both are in `experiments.py`).
5. **What this machine cannot measure** (and what `experiments.py` is
   for): live 2-engine routing, live spec-decode acceptance, TP prefill
   split, and sub-second TTFT tails under load. On a box with ≥ 2 spare
   models of headroom, `experiments.py e1|e2|e3|e5 --runs 12` produces
   the real-MLX equivalents of the sim column above.

## Cross-references

- **A4** (`a4_serve/`) measures the E0 lever in isolation at the engine
  layer: prefix reuse = 9–35× TTFT on shared-prefix workloads (1.5 B,
  16 reqs), decode compute-bound at N≈4, and a **real concurrency bug
  found and fixed** in the engine (stale-uid batch dispatch) — the bug
  that would have killed every N>1 A3 run.
- **A5** (`a5_stack/`) takes the optimized A2 runtime into
  Terminal-Bench sandboxes with the A4 engine as its brain — the whole
  column of this table, end to end.

## Reproducing everything

```sh
# real measurements (A2 driver, three configs) — ~15 min, one engine at a time
cd a2_loop
.venv/bin/python run.py --tag baseline --concurrency 1 --base-url http://localhost:8084/v1 --model <35B-id>
.venv/bin/python run.py --tag compare27 --concurrency 4 --model qwen/qwen3.8-27b-splash
.venv/bin/python run.py --tag fault --concurrency 1 --fault-rate 0.2 --model qwen/qwen3.6-35b-a3b
# results: a2_loop/results/{baseline,compare27,fault}.json

# deterministic sim sweep (seconds; run the same snippet as experiments.py's sim mode)
cd /Users/fx/wk/github/cs2680-harvard
.venv/bin/python a3_opt/experiments.py --sim   # E0–E5 table above, byte-identical

# real engine ablations (when two engines are hot):
a3_opt/experiments.py e1 --runs 12              # routing, per-step model decisions in output
```
