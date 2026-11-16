# a1_lens — Mads-Lens: a trustworthy Web UI for Claude Code sessions (CS2680 A1)

Read-only visualizer for Claude Code's on-disk session logs
(`~/.claude/projects/**/*.jsonl`). It renders the real event stream —
tool calls with inputs/returns, sub-agent threads, errors, and per-call
token/cost — as a browsable, live-tailing web app. No frameworks, no
CDNs, no writes: Python stdlib server + one static SPA.

## Architecture

```
~/.claude/projects/<dir>/<session>.jsonl  (+ <sid>/subagents/*.jsonl)
        │  (read-only, mtime-gated reparse)
        ▼
lens_parser.py     JSONL → session graph: threads → steps, tool-result
                   pairing, error classification, usage attribution,
                   sub-agent nesting, token/cost aggregation
        │
        ▼
lens_cost.py       model-name normalization (claude-* / lmstudio/* /
                   antigravity/* / <synthetic>) + price table → 5 cost
                   components (input / output / cache-read / cache-
                   creation / thinking); unknown model → 0 with an
                   explicit `price_unknown` flag, never a fabricated number
        │
        ▼
server.py          stdlib ThreadingHTTPServer:
                   GET /api/sessions            list (newest first, summary
                                                fields + subagent counts)
                   GET /api/session/<id>        full parsed graph
                   GET /api/session/<id>/tail?after=N   incremental steps
                   GET /                        static/ (index/app/style)
        │
        ▼
static/            single-page client: session list → step timeline
                   (color-coded: tool / error / thinking / meta),
                   per-step token + cost chips, error reasons, sub-agent
                   tree, live tail loop
```

Design rules that keep it trustworthy:

- **Never fabricate**: a step with zero usage stays zero-cost; an unknown
  model renders "unpriced" (badge + tooltip), local models render "$0
  (local)". The UI never invents a dollar figure.
- **Errors are typed**: `is_error` tool results and assistant error text
  are detected (`detect_tool_error` / `detect_assist_error`), truncated to
  160-char reasons, and rendered in a distinct error style — so a failed
  3rd-party API call is visible the moment the session loads.
- **Read-only + incremental**: the server only reads; live tailing is
  an `after=<seq>` poll of new lines, so a running session updates without
  re-parsing, and a closed session parses once (mtime-gated).

## Run it

```sh
cd a1_lens
python3 server.py --port 8787 --root ~/.claude/projects   # works on 3.9+
# → http://localhost:8787
```

No pip installs. Verified live against this machine's sessions: the API
returns the real `~/.claude/projects` tree (session list with tokens/cost/
error/subagent summary fields; per-session step graph; incremental tail).

## Files

| File | Role |
|---|---|
| `lens_parser.py` | the parser: `discover_sessions`, `session_graph`, step builder per JSONL record type, tool-result pairing, cost attribution, sub-agent ingest |
| `lens_cost.py` | `PRICES` table (Claude Opus/Sonnet/Haiku 4.x, gateways, local), `normalize_model`, `price_for`, `cost_for_usage` (5 components) |
| `server.py` | stdlib HTTP server + the three API routes + static file serving |
| `static/index.html`, `app.js`, `style.css` | the UI |

## What it shows (the brief's four requirements)

1. **Live tool-call trajectory** — every assistant step with its tool
   calls (name + pretty-printed input) and paired results (truncated
   preview, full text on expand); timestamps and per-step tokens.
2. **Sub-agent tree** — `Task`-spawned subagents appear as nested threads
   under their spawn step; the session list shows subagent counts.
3. **Error localization** — errors render inline at the failing step with
   the detected reason; the session list carries an error count.
4. **Per-call token & cost** — five cost components per step and per
   session, with unpriced/local models flagged rather than guessed.
