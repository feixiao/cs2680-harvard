# a3_opt — Mads-Opt: end-to-end optimization + technical review (CS2680 A3)

Optimizes the A2 runtime (`a2_loop/madsloop`) and reports it. Two
components, one story:

| File | Role |
|---|---|
| `blog.md` | **the deliverable** — the technical review: real E0 measurements (engine + prefix cache: 8.5× cost / 2.9× latency, 12/12), the deterministic 6-point lever sweep (E1–E5: routing 31× cost, concurrency 9.1× latency, full stack 112×/135×, success intact), findings, and what a single Mac cannot measure. |
| `experiments.py` | the harness. `--sim` runs the deterministic `mads/` sweep (no engines needed, byte-identical); with no flag it runs real-engine ablations E1–E5 against the A4 engine + LM Studio (needs two engines hot). |
| `engines.sh` | engine fleet control: `engines.sh status|up|down` for the mlx-lm 1.5 B (:8082) and 35 B (:8084) servers, with the course's prefix-cache flags. |

Run the whole review from scratch:

```sh
a2_loop/.venv/bin/python a3_opt/experiments.py --sim   # sim sweep, seconds
a2_loop/.venv/bin/python a3_opt/experiments.py E1 E2 E5   # real ablations, ~1 h
```

Engine prerequisites for the real ablations (experiments.py checks with
`engines_up`): 1.5 B @8082 (`engines.sh start`), 35 B @8084
(`a4_serve/serve.sh` or `a3_opt/engines.sh start`), 27 B @1234 (LM
Studio). One engine at a time keeps measurements clean; the 35 B @8084
server must run with a **patched** mlx-lm (a4_serve) or N>1 decode will
crash it (see A4).

The numbers in `blog.md` are the ones from 2026-11-16 on this machine
(128 GB Apple Silicon, LM Studio 27 B + two mlx-lm servers); absolute
dollars use published list prices because the local engines cost $0.
