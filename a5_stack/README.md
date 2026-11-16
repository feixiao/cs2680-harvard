# a5_stack — Mads-Stack evaluation infra (CS2680 A5)

Terminal-Bench harness + Mads-Stack (Mads-Loop-backed) agent, standing,
smoke-tested, and run: first full-stack suite measured at 1/5 (20 %) on a
1.5 B brain — the full path proven end to end ([First full-stack run](#first-full-stack-run-measured-2026-11-16-112-min)).

## What is ready

| Piece | State |
|---|---|
| Docker daemon | Docker Desktop 4.96.1 / Engine **29.9.2** (aarch64, **16 CPU, 7.75 GB RAM** — under the 16 GB cap, left as-is). Started with `open -a Docker`. |
| `.venv` | Homebrew **Python 3.14.7**, **terminal-bench 0.2.18** (latest on PyPI) + deps. CLI is `tb` (0.2.x renamed the old `tbench`); a compat shim at `.venv/bin/tbench` forwards to `tb`. |
| Task catalog | `terminal-bench-core` **v0.1.1** (the launch set: 65 tasks per the registry; the sparse clone at `terminal-bench-core/tasks/` holds all 86 dirs of that branch). |
| Curated images | 3 base images pulled + 5 small task images prebuilt = **~1.9 GB total** (≤10 GB budget). All boot-verified with a shell. |
| Agent | `harness_stub.py` — `MadsStackAgent`, terminal-bench's `BaseAgent` driven by the `a2_loop/madsloop` runtime. Smoke: **PASS** (one real command round-trip in the hello-world sandbox, 7 s). |

### Docker resources
Docker Desktop VM: 16 CPU / 7.75 GB RAM (default on this Mac; host has 128 GB —
if the full-stack phase wants headroom for bigger tasks, raise the RAM ceiling
in Docker Desktop → Settings → Resources, **≤16 GB** per the resource budget;
LM Studio + mlx-lm engines hold ~30–40 GB of the host).

### Task catalog
- Dataset: `terminal-bench-core==0.1.1` (simple hand-crafted tasks) is checked
  out locally at `terminal-bench-core/tasks/` — use `--dataset-path` to avoid
  re-downloading (network here is slow; a 650 MB image pull took ~35 min).
- The terminal-bench registry (fetched via `tb datasets list`) also offers
  adapter datasets — `swebench-verified`, `swesmith`, `appworld-*`,
  `mlebench-lite`, `quixbugs`, `usaco`, `algotune`, `aider-polyglot` — all
  `head` versions, all much heavier than the core set.
- Curated small tasks (simple bash/python, no ML/data-science):
  `hello-world`, `count-dataset-tokens`, `grid-pattern-transform`,
  `organization-json-generator`, `fix-permissions`.
  Avoid for small-VM runs: `train-fasttext`, `eval-mteb`, `hf-model-inference`,
  `pytorch-model-cli`, `cartpole-rl-training`, `chess-best-move`, `qemu-*`,
  `build-*`, `swe-bench-*`, `solana-data`, `reshard-c4-data`, `intrusion-detection`.

### Curated images (all boot-verified: shell + tmux + asciinema present)
| Image | Size | Used by |
|---|---|---|
| `ghcr.io/laude-institute/t-bench/python-3-13:latest` | 265 MB | hello-world, count-dataset-tokens, grid-pattern-transform, org-json-generator (and most python tasks) |
| `ghcr.io/laude-institute/t-bench/ubuntu-24-04:latest` | 206 MB | fix-permissions (and other bash tasks) |
| `ubuntu:latest` | 181 MB | git-multibranch |
| `tb__hello-world__client:latest` | 265 MB | prebuilt task image |
| `tb__count-dataset-tokens__client:latest` | 265 MB | prebuilt task image |
| `tb__grid-pattern-transform__client:latest` | 265 MB | prebuilt task image |
| `tb__organization-json-generator__client:latest` | 285 MB | prebuilt task image |
| `tb__fix-permissions__client:latest` | 206 MB | prebuilt task image |

The `tb__*` names are exactly what the harness computes at run time
(`tb__<task_id>__client`), so runs can use `--no-rebuild` and start instantly.
Rebuild any of them: `a5_stack/build_curated.sh` (rebuilds all 5 in ~15 s).

## The harness contract (3 sentences)
terminal-bench 0.2.18 drives an agent through
`BaseAgent.perform_task(instruction, session, logging_dir)`, where `session`
is a `TmuxSession` wrapping the task's docker container: the agent sends input
with `session.send_keys([cmd, "Enter"], block=True)` (which waits on a
`tmux wait -S done` marker) and reads results with
`session.get_incremental_output()` / `capture_pane()`. The harness instantiates
the agent from the CLI via `--agent-import-path module.path:ClassName` and
`--agent-kwarg key=value`, then runs `perform_task` in an executor thread under
`asyncio.wait_for(task.max_agent_timeout_sec)`, after which it executes the
task's `run-tests.sh` in a fresh session and parses the pane for resolved/not.
`MadsStackAgent` fulfils that interface by running the Mads-Loop `Agent`
(OpenAI-chat loop: retry/backoff, sliding context, loop detection) whose only
exposed tool is `bash`, rerouted from the host into the tmux session — the
model therefore acts on the container's own terminal, and usage tokens map to
`AgentResult`.

## Exactly what the full-stack phase runs

Precondition: A4's engine serving OpenAI chat completions on
`http://localhost:8081/v1` — up via `a4_serve/serve.sh` (patched server:
`/metrics` + the concurrency crash fix, so the agent's concurrent
requests are safe).

Run one task:
```bash
cd /Users/fx/wk/github/cs2680-harvard        # repo root on sys.path for the import path
export PYTHONPATH=$PWD
a5_stack/.venv/bin/tbench run \
  --dataset-path a5_stack/terminal-bench-core/tasks \
  --task-id hello-world \
  --agent-import-path a5_stack.harness_stub:MadsStackAgent \
  --agent-kwarg base_url=http://localhost:8081/v1 \
  --agent-kwarg model=<a4 model name> \
  --no-rebuild --no-cleanup \
  --output-path a5_stack/runs
```
Run a suite (5 curated tasks):
```bash
a5_stack/.venv/bin/tbench run \
  --dataset-path a5_stack/terminal-bench-core/tasks \
  --task-id hello-world --task-id count-dataset-tokens \
  --task-id grid-pattern-transform --task-id organization-json-generator \
  --task-id fix-permissions \
  --agent-import-path a5_stack.harness_stub:MadsStackAgent \
  --agent-kwarg base_url=http://localhost:8081/v1 \
  --agent-kwarg model=<a4 model name> \
  --no-rebuild --no-cleanup --n-concurrent 1 \
  --output-path a5_stack/runs
```
Harness sanity check that needs no LLM at all:
```bash
a5_stack/.venv/bin/tbench run --dataset-path a5_stack/terminal-bench-core/tasks \
  --task-id hello-world --agent-name oracle --no-rebuild --no-cleanup --output-path a5_stack/runs
```
Use `--no-cleanup` when you want the prebuilt images to survive the run
(`--cleanup` deletes images with `compose down --rmi all`).

## First full-stack run (measured 2026-11-16, 11.2 min)

The 5 curated tasks, real Docker sandboxes, A2 runtime driving the agent,
1.5 B engine as the brain, `n-concurrent 1`:

| Task | Result |
|---|---|
| `hello-world` | **resolved** — the 1.5 B model completed the task end-to-end in the sandbox |
| `count-dataset-tokens` | unresolved (test timeout) |
| `grid-pattern-transform` | unresolved (test timeout) |
| `fix-permissions` | unresolved (test timeout) |
| `organization-json-generator` | unresolved (test timeout) |

**Accuracy 1/5 (20%).** Honest reading: this is a *1.5 B* model — the
floor, not the ceiling of the stack. hello-world proves the full path
works (model → Mads-Loop retry/context loop → tmux terminal → real shell
→ task tests → verdict). The other four need a model that can follow
multi-step shell instructions; swapping the brain to the 35 B MoE (or
27 B) via `--agent-kwarg` is the next experiment — the harness, images,
and agent are all model-agnostic. Run output: `runs/2026-11-16__17-23-22/`
(`results.json` + per-task dirs + `run.log`).

## Gaps the full-stack phase must close
1. **A4 engine up on :8081** with the real model name — set
   `--agent-kwarg model=...` (env `MADS_MODEL` also works; default
   `qwen3.8-27b-splash`).
2. **File tools**: the stub exposes only `bash` (file tools would hit the
   host filesystem, not the container). Extend `TerminalToolExecutor` to
   route read/write/edit/glob/grep through the session if richer behavior is
   wanted — bash-only already solves file tasks.
3. **RAM budget**: 7.75 GB VM; keep `--n-concurrent 1` and stay on the
   curated small tasks unless Docker Desktop RAM is raised (≤16 GB).
4. If you ever `pip install --force-reinstall terminal-bench`, the Python
   3.14 compat patch re-applies automatically the next time `tbench` is
   invoked (see below).

## Python 3.14 gotcha (fixed, documented)
terminal-bench 0.2.18 defines CLI command functions named `list` in
`terminal_bench/cli/tb/{runs,datasets}.py`. Python 3.14 (PEP 649) evaluates
annotations lazily in module globals, so `list[str] | None` in other commands
of the same module fails typer's resolution: *every* `tb` invocation died with
`TypeError: 'function' object is not subscriptable`. `a5_stack/patch_terminal_bench.py`
renames the shadowing functions (subcommand names preserved via explicit
`name="list"`) and is applied idempotently by the `.venv/bin/tbench` shim.
(There is no newer PyPI release that fixes it; 0.2.18 is current.)

## Files
- `harness_stub.py` — `MadsStackAgent` + `TerminalToolExecutor` + `smoke()`
  (`python harness_stub.py smoke [--task X] [--rebuild]`).
- `build_curated.sh` — rebuild the 5 curated task images.
- `patch_terminal_bench.py` — idempotent 3.14 compat patch (invoked by the shim).
- `terminal-bench-core/` — sparse clone of the v0.1.1 dataset branch
  (tasks/, git-ignored; re-fetch: `git clone --filter=blob:none --sparse
  -b v0.1.1 https://github.com/laude-institute/terminal-bench-core` +
  `git sparse-checkout set tasks` in it).
- `.venv/` — Python 3.14 env; `bin/tb`, `bin/terminal-bench`, `bin/tbench` (shim).
