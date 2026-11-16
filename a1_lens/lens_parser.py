"""lens_parser — turn Claude Code JSONL session logs into an event graph.

The Claude Code log is an append-only JSONL *event stream*, not a transcript:

  * every "real" line (user / assistant / system / attachment / summary)
    carries `uuid` and `parentUuid`, forming a linked list that weaves
    through ALL those line types (a user line can have a `system` line as
    its direct parent — see README, "where the chain breaks");
  * a single API *response* is written as several lines (one per content
    block: thinking, text, tool_use) that all share `message.id` and repeat
    the same `usage` — naive summing would 3-4x overcount tokens;
  * tool results arrive as separate `user` lines whose blocks reference the
    tool via `tool_use_id` (and whose `parentUuid` points at the tool_use
    line, but we pair by id — it is the stable key);
  * sub-agents do NOT appear in the main file. Their lines go to separate
    files `<session>/<sessionId>/subagents/agent-<agentId>.jsonl` with
    `isSidechain: true` and `agentId` set; the link back into the main
    stream is the `toolUseResult.agentId` on the `Agent`/`Task` tool result
    (plus `<task-id>` in later `task-notification` user lines);
  * a pile of telemetry lines (api-request, api-request-blob, queue-operation,
    cost-state, mode, atis-latch, ...) are interleaved and must degrade to
    generic "meta" events, never crash.

Everything degrades gracefully: an unparseable line or an unknown shape
becomes a `raw`/`meta` step; the parser never raises on file content.
"""

import glob
import json
import os
import re
import time

try:
    from . import lens_cost
except ImportError:  # imported as a top-level module (server.py does this)
    import lens_cost

# --------------------------------------------------------------------------
# low-level line reading

def iter_lines(path):
    """Yield (seq, obj_or_None) for every physical line; seq is 0-based."""
    try:
        f = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with f:
        seq = 0
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield seq, json.loads(line)
                except Exception:
                    yield seq, None
            seq += 1


def _get(obj, *keys, default=None):
    """First present key wins (handles sessionId vs session_id variants)."""
    if not isinstance(obj, dict):
        return default
    for k in keys:
        if k in obj and obj[k] is not None:
            return obj[k]
    return default


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _s(x, default=""):
    return x if isinstance(x, str) else ("" if x is None else default)


def _content_text(content):
    """message.content str or block list -> plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(_s(b.get("text")))
                elif b.get("type") == "image":
                    parts.append("[image]")
                elif b.get("type") == "thinking":
                    pass  # thinking handled separately
        return "\n".join(p for p in parts if p)
    return str(content)


# --------------------------------------------------------------------------
# error detection

ERR_TOOL_PATTERNS = [
    re.compile(r"<tool_use_error>", re.I),
    re.compile(r"(?i)\bexit code (?:is )?0x[0-9a-f]+\b"),
    re.compile(r"(?i)\bexit code [1-9]\d*\b"),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"(?im)^\s*error: .{1,80}$"),
    re.compile(r"(?i)\bcommand not found\b"),
    re.compile(r"(?i)\bpermission denied\b"),
    re.compile(r"(?i)\bAPI Error\b"),
]

ERR_ASSIST_PATTERNS = [
    re.compile(r"(?i)^API Error"),
    re.compile(r"(?i)^Request (timed out|failed)"),
    re.compile(r"(?i)^Error:"),
]

SYNTHETIC_USER_MARKERS = (
    "<command-name>", "<command-message>", "<command-args>",
    "<local-command-stdout>", "<local-command-stderr>", "<local-command-caveat>",
    "<task-notification>", "<system-reminder>", "<bash-stdout>", "<bash-stderr>",
    "[Request interrupted by user]", "<turn-aborted>",
)


def _err_reason(text, limit=160):
    for pat in ERR_TOOL_PATTERNS:
        m = pat.search(text or "")
        if m:
            start = max(0, m.start() - 40)
            frag = (text[start:m.end() + 90]).replace("\n", " ⏎ ")
            frag = re.sub(r"\s+", " ", frag).strip()
            return (frag[:limit] + "…") if len(frag) > limit else frag
    return None


def detect_tool_error(is_error, text):
    if is_error:
        return _err_reason(text) or "tool reported isError"
    return _err_reason(text)


def detect_assist_error(text):
    for pat in ERR_ASSIST_PATTERNS:
        m = pat.search(text or "")
        if m:
            return (text[:160] + "…").replace("\n", " ⏎ ") if len(text or "") > 160 else text
    return None


# --------------------------------------------------------------------------
# block-level rendering helpers

MAX_RESULT_PREVIEW = 16384  # wire cap for tool result text (client shows ~4 KB)
MAX_INPUT_SEND = 32768      # wire cap for tool_use input JSON

PERSISTED_RE = re.compile(r"saved to: (\S+?)(?:\n|$)", re.I)


def _result_text(result):
    c = result.get("content")
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for b in c:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(_s(b.get("text")))
                elif b.get("type") == "image":
                    parts.append("[image]")
                else:
                    parts.append("[" + str(b.get("type", "block")) + "]")
            else:
                parts.append(str(b))
        return "\n".join(parts)
    return json.dumps(c, ensure_ascii=False)


def _truncate(text, limit=MAX_RESULT_PREVIEW):
    if text is None:
        return "", 0, False
    if len(text) <= limit:
        return text, len(text), False
    return text[:limit], len(text), True


def _tool_input_for_display(b):
    """tool_use input; handles __unparsedToolInput variant."""
    inp = b.get("input")
    if isinstance(inp, dict) and "__unparsedToolInput" in inp and len(inp) <= 3:
        up = inp["__unparsedToolInput"]
        raw = _s(up.get("raw"))
        return {"__unparsed": True, "raw": raw, "len": up.get("len")}
    return inp


def _usage_dict(u):
    u = u or {}
    det = u.get("output_tokens_details") or {}
    cc = u.get("cache_creation") or {}
    return {
        "input": _num(u.get("input_tokens")),
        "output": _num(u.get("output_tokens")),
        "cache_read": _num(u.get("cache_read_input_tokens")),
        "cache_create": _num(u.get("cache_creation_input_tokens"), ),
        "cache_create_1h": _num(cc.get("ephemeral_1h_input_tokens")),
        "thinking": _num(det.get("thinking_tokens")),
    }


def usage_all_zero(u):
    return not any(_usage_dict(u).values())


AGENT_TOOL_NAMES = ("Agent", "Task")
TASK_ID_RE = re.compile(r"<task-id>([a-zA-Z0-9_-]+)</task-id>")


# --------------------------------------------------------------------------
# line -> step

META_LABELS = {
    "api-request": "api request",
    "api-request-blob": "api request blob",
    "api-request-shape": "api request shape",
    "queue-operation": "queue",
    "cost-state": "cost state",
    "mode": "mode",
    "permission-mode": "permission mode",
    "atis-latch": "latch",
    "file-history-snapshot": "file snapshot",
    "file-history-delta": "file delta",
    "last-prompt": "last prompt",
    "tools-used": "tools",
    "summary": "summary",
    "attachment": "attachment",
}


def line_to_step(obj, seq, thread_id="main"):
    """Convert one parsed JSONL object into a step dict. Never raises."""
    if not isinstance(obj, dict):
        return _raw_step(seq, thread_id, "non-object line")
    t = obj.get("type")
    try:
        if t == "assistant":
            return _assistant_step(obj, seq, thread_id)
        if t == "user":
            return _user_step(obj, seq, thread_id)
        if t == "system":
            return _system_step(obj, seq, thread_id)
        if t == "attachment":
            return _meta_step(obj, seq, thread_id, "attachment")
        if t in META_LABELS:
            return _meta_step(obj, seq, thread_id, t)
        return _raw_step(seq, thread_id, "unknown type %r" % (t,))
    except Exception as e:  # defensive: a variant line must never kill the parse
        return _raw_step(seq, thread_id, "variant %r: %s" % (t, e))


def _base(obj, seq, thread_id):
    return {
        "seq": seq,
        "thread": thread_id,
        "ts": obj.get("timestamp"),
        "uuid": obj.get("uuid"),
        "parentUuid": obj.get("parentUuid"),
        "isSidechain": bool(obj.get("isSidechain")),
        "agentId": obj.get("agentId"),
        "cwd": obj.get("cwd"),
        "blocks": [],
        "usage": None,
        "model": None,
        "callId": None,
        "callCost": 0.0,
        "priceUnknown": False,
        "isLocal": False,
        "isSynthetic": False,
        "error": False,
        "errorReason": None,
        "turnOrigin": obj.get("turnOrigin"),
        "promptSource": obj.get("promptSource"),
    }


def _raw_step(seq, thread_id, note):
    s = {"seq": seq, "thread": thread_id, "kind": "raw", "blocks": [],
         "usage": None, "model": None, "callId": None, "callCost": 0.0,
         "priceUnknown": False, "isLocal": False, "isSynthetic": False,
         "error": False, "errorReason": None, "ts": None, "uuid": None,
         "parentUuid": None, "isSidechain": False, "agentId": None,
         "cwd": None, "turnOrigin": None, "promptSource": None}
    s["note"] = note
    return s


def _assistant_step(obj, seq, thread_id):
    s = _base(obj, seq, thread_id)
    s["kind"] = "assistant"
    m = obj.get("message") or {}
    model = _get(m, "model", default=None) or obj.get("requestedModel")
    s["model"] = model
    s["callId"] = m.get("id")
    s["thinkingDurationMs"] = obj.get("thinkingDurationMs")
    s["toolInputStreamMs"] = obj.get("toolInputStreamMs")
    s["isSynthetic"] = model == "<synthetic>"
    s["attributionAgent"] = obj.get("attributionAgent")
    blocks = m.get("content")
    if isinstance(blocks, str):
        s["blocks"] = [{"type": "text", "text": blocks}]
    elif isinstance(blocks, list):
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text":
                s["blocks"].append({"type": "text", "text": _s(b.get("text"))})
            elif bt == "thinking":
                s["blocks"].append({"type": "thinking", "text": _s(b.get("thinking"))})
            elif bt == "tool_use":
                s["blocks"].append({
                    "type": "tool_use",
                    "name": _s(b.get("name"), "?"),
                    "id": _s(b.get("id")),
                    "input": _tool_input_for_display(b),
                    "result": None,   # attached later by pairing
                })
            elif bt == "tool_result":  # defensive: assistant should never have these
                s["blocks"].append({"type": "tool_result", "id": b.get("tool_use_id"),
                                    "content": _result_text(b), "isError": bool(b.get("isError"))})
            else:
                s["blocks"].append({"type": bt or "block", "raw": b})
    else:
        s["blocks"] = []

    # usage + cost
    u = m.get("usage")
    s["usage"] = _usage_dict(u) if u else None
    cost, unknown, local, matched, _tok = lens_cost.cost_for_usage(u, model)
    s["callCostRaw"] = round(cost, 8)
    s["priceUnknown"] = unknown
    s["isLocal"] = local
    # attribution happens in the thread builder (dedup by message.id)
    if s["isSynthetic"] or (s["usage"] and usage_all_zero(s["usage"])):
        r = detect_assist_error(_content_text(m.get("content")))
        if r:
            s["error"] = True
            s["errorReason"] = r
    return s


def _user_step(obj, seq, thread_id):
    s = _base(obj, seq, thread_id)
    s["kind"] = "user"
    m = obj.get("message") or {}
    content = m.get("content")
    s["isMeta"] = bool(obj.get("isMeta"))
    is_result_only = False
    if isinstance(content, str):
        text = content
        looks_synth = text.startswith(SYNTHETIC_USER_MARKERS) or obj.get("isMeta")
        s["blocks"] = [{"type": "text", "text": text}]
        if looks_synth:
            s["isSynthetic"] = True
        s["taskIds"] = TASK_ID_RE.findall(text)
    elif isinstance(content, list):
        is_result_only = all(isinstance(b, dict) and b.get("type") == "tool_result"
                             for b in content if isinstance(b, dict))
        for b in content:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "tool_result":
                s["blocks"].append({
                    "type": "tool_result",
                    "id": _s(b.get("tool_use_id")),
                    "isError": bool(b.get("isError")),
                    # raw content kept for pairing; big payloads truncated there
                    "content": b.get("content"),
                    "toolUseResult": obj.get("toolUseResult") if len(content) == 1 else None,
                })
            elif bt == "text":
                txt = _s(b.get("text"))
                s["blocks"].append({"type": "text", "text": txt})
                if txt.strip().startswith(SYNTHETIC_USER_MARKERS) or obj.get("isMeta"):
                    s["isSynthetic"] = True
                if txt:
                    s["taskIds"] = TASK_ID_RE.findall(txt)
    else:
        s["blocks"] = []
    s["isResultOnly"] = is_result_only and bool(s["blocks"])
    s["permissionDecision"] = (obj.get("permissionDecision") or {}).get("behavior")
    # error detection (from result content)
    text = _content_text(content)
    err = detect_tool_error(False, text)
    if err:
        s["error"] = True
        s["errorReason"] = err
    return s


def _system_step(obj, seq, thread_id):
    s = _base(obj, seq, thread_id)
    s["kind"] = "system"
    s["subtype"] = obj.get("subtype")
    text = _s(obj.get("content")) or _s(obj.get("error"))
    s["blocks"] = [{"type": "text", "text": text}] if text else []
    s["label"] = obj.get("subtype") or "system"
    if obj.get("error"):
        s["error"] = True
        s["errorReason"] = _s(obj.get("error"))[:160]
    return s


def _meta_step(obj, seq, thread_id, t):
    s = _raw_step(seq, thread_id, None)
    s["kind"] = "meta"
    s["metaType"] = t
    s["label"] = META_LABELS.get(t, t)
    s["ts"] = obj.get("timestamp")
    s["uuid"] = obj.get("uuid")
    s["parentUuid"] = obj.get("parentUuid")
    s["isSidechain"] = bool(obj.get("isSidechain"))
    s["agentId"] = obj.get("agentId")
    s["cwd"] = obj.get("cwd")
    s["turnOrigin"] = obj.get("turnOrigin")
    s["promptSource"] = obj.get("promptSource")
    # short preview
    if t == "queue-operation":
        s["preview"] = _s(obj.get("content"))[:120]
        s["op"] = obj.get("operation")
    elif t == "cost-state":
        s["preview"] = "$%.2f" % _num(obj.get("totalCostUSD"))
    elif t == "attachment":
        a = obj.get("attachment") or {}
        s["preview"] = _s(a.get("type"))
        s["label"] = "attachment: %s" % (_s(a.get("type")) or "x")
    elif t in ("api-request", "api-request-blob", "api-request-shape"):
        s["preview"] = str(obj.get("querySource") or obj.get("hash") or "")[:80]
    else:
        s["preview"] = ""
    return s


# --------------------------------------------------------------------------
# pairing + thread building

def _pair_results(steps):
    """Attach each tool_result to its tool_use block (paired by tool_use_id).

    Mutates `steps`: result-only user steps get removed from the list (their
    data lives inside the tool_use step's `result`); the truncated raw
    content is dropped from result blocks to keep payloads small.
    Returns the reduced list of timeline steps.
    """
    by_id = {}
    for s in steps:
        for b in s["blocks"]:
            if b["type"] == "tool_use" and b.get("id"):
                by_id[b["id"]] = (b, s)
    out = []
    for s in steps:
        kept = []
        for b in s["blocks"]:
            if b["type"] != "tool_result":
                kept.append(b)
                continue
            content = b.get("content")
            res_text = _result_text({"content": content})
            res_text, res_len, truncated = _truncate(res_text)
            persisted = None
            pm = PERSISTED_RE.search(res_text)
            if pm:
                persisted = pm.group(1)
            reason = detect_tool_error(b.get("isError"), res_text)
            tu_pair = by_id.get(b.get("id"))
            if tu_pair is not None:
                tu_block, tu_step = tu_pair
                tu_block["result"] = {
                    "text": res_text, "len": res_len, "truncated": truncated,
                    "persisted": persisted, "isError": bool(b.get("isError")),
                    "errorReason": reason, "seq": s["seq"],
                }
                tu_block["resultError"] = bool(b.get("isError")) or bool(reason)
                tur = b.get("toolUseResult")
                if tur and isinstance(tur, dict) and tur.get("agentId"):
                    tu_block["agentLaunch"] = {
                        "agentId": tur.get("agentId"),
                        "description": tur.get("description"),
                        "status": tur.get("status"),
                        "model": tur.get("resolvedModel"),
                        "isAsync": tur.get("isAsync"),
                    }
                    tu_step["spawnedAgents"] = (tu_step.get("spawnedAgents") or []) + [tur["agentId"]]
                if reason:
                    tu_step["error"] = True
                    tu_step["errorReason"] = reason
            # strip raw content; keep a small summary on the block itself
            b["content"] = None
            b["text"] = _truncate(res_text, 512)[0]
            b["isError"] = bool(b.get("isError"))
            b["errorReason"] = reason
            b.pop("toolUseResult", None)
            if reason and s.get("kind") == "user" and not s.get("isResultOnly"):
                s["error"] = True
                s["errorReason"] = reason
            kept.append(b)
        if s.get("isResultOnly"):
            continue  # folded into the tool_use step
        s["blocks"] = kept
        out.append(s)
    return out


def _attribute_costs(steps):
    """Charge one cost per API response (message.id); zero otherwise.

    A single response is written as several lines (thinking/text/tool_use)
    that all repeat the same usage — attribute to the first line only.
    """
    seen = set()
    for s in steps:
        if s["kind"] != "assistant":
            continue
        if s.get("callId") is None:
            s["callCost"] = s.get("callCostRaw", 0.0)
            continue
        if s["callId"] in seen:
            s["callCost"] = 0.0
            s["sameCall"] = True
        else:
            seen.add(s["callId"])
            s["callCost"] = s.get("callCostRaw", 0.0)
            s["sameCall"] = False
    return steps


def build_thread_steps(steps):
    steps = [s for s in steps if s is not None]
    steps = _pair_results(steps)
    return _attribute_costs(steps)


# --------------------------------------------------------------------------
# session-level discovery

def _dir_matches(sid, d):
    """A session subdir may be named by the full id or a short prefix of it."""
    if d == sid:
        return True
    if len(d) >= 4 and (sid.startswith(d) or d.startswith(sid)):
        return True
    return False


def discover_sessions(root):
    """Walk `root`; return list of session records (dicts with paths).

    Layout:  <root>/<proj>/<sessionId>.jsonl            main file
             <root>/<proj>/<short-id>/subagents/agent-*.jsonl   sub-agents
    (the subagents dir is sometimes named by the *short* session id —
    e.g. "a156c1f0" — so matching is prefix-tolerant).
    """
    sessions = []
    if not os.path.isdir(root):
        return sessions
    for proj in sorted(os.listdir(root)):
        proj_dir = os.path.join(root, proj)
        if not os.path.isdir(proj_dir):
            continue
        files = []
        dirs = {}
        for name in sorted(os.listdir(proj_dir)):
            p = os.path.join(proj_dir, name)
            if name.endswith(".jsonl") and os.path.isfile(p):
                files.append((name[:-6], p))
            elif os.path.isdir(p) and re.fullmatch(r"[0-9a-fA-F-]{8,}", name):
                subs = []
                sub_dir = os.path.join(p, "subagents")
                if os.path.isdir(sub_dir):
                    for sname in sorted(os.listdir(sub_dir)):
                        if sname.endswith(".jsonl"):
                            subs.append(os.path.join(sub_dir, sname))
                dirs[name] = subs
        for sid, p in files:
            sessions.append({
                "id": sid,
                "dir": proj,
                "path": p,
                "subagentPaths": [],
                "orphan": False,
            })
        for dname, subs in dirs.items():
            if not any(_dir_matches(s["id"], dname)
                       for s in sessions if s["dir"] == proj):
                # orphan: session dir whose top-level file is missing
                sessions.append({
                    "id": dname, "dir": proj, "path": None,
                    "subagentPaths": subs, "orphan": True,
                })
        # attach subs (dirs may sort before their .jsonl, so match here)
        for s in sessions:
            if s["dir"] == proj and not s["orphan"]:
                s["subagentPaths"] = sorted(
                    x for d, xs in dirs.items() if _dir_matches(s["id"], d)
                    for x in xs
                )
    return sessions


# --------------------------------------------------------------------------
# summaries (for /api/sessions)

def _first_user_prompt(steps):
    for s in steps:
        if s["kind"] != "user" or s.get("isSynthetic") or s.get("isMeta"):
            continue
        for b in s["blocks"]:
            if b["type"] == "text" and b["text"].strip():
                t = " ".join(b["text"].split())
                return t[:300]
    return None


def session_summary(rec, now=None):
    """One streaming pass over the session file (and subagent files)."""
    now = now or time.time()
    st = os.stat(rec["path"]) if rec["path"] else None
    info = {
        "id": rec["id"],
        "dir": rec["dir"],
        "cwd": None,
        "models": [],
        "firstPrompt": None,
        "messageCount": 0,
        "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0, "thinking": 0},
        "cost": 0.0,
        "priceUnknown": False,
        "isLocalOnly": True,
        "claudeCodeCost": None,
        "claudeCodeModelCosts": None,
        "mtime": st.st_mtime if st else None,
        "size": st.st_size if st else 0,
        "startTime": None,
        "subagents": [],
        "subagentCount": 0,
        "errors": 0,
        "live": False,
        "steps": 0,
    }
    models = {}
    seen_calls = set()
    steps = []

    def ingest_file(path, thread_id, is_sub=False):
        nonlocal info
        for seq, obj in iter_lines(path):
            if obj is None:
                continue
            t = obj.get("type") if isinstance(obj, dict) else None
            if t not in ("user", "assistant"):
                if t == "cost-state" and not is_sub:
                    info["claudeCodeCost"] = _num(obj.get("totalCostUSD"))
                    mu = obj.get("modelUsage") or {}
                    if mu:
                        info["claudeCodeModelCosts"] = {
                            k: {kk: vv for kk, vv in v.items() if isinstance(vv, (int, float))}
                            for k, v in mu.items()
                        }
                    if obj.get("hasUnknownModelCost"):
                        info["priceUnknown"] = True
                continue
            s = line_to_step(obj, seq, thread_id)
            steps.append(s)
            if s.get("cwd"):
                info["cwd"] = s["cwd"]
            if t == "assistant" and s.get("model") and s["model"] != "<synthetic>":
                models[s["model"]] = models.get(s["model"], 0) + 1
            if s["kind"] == "user":
                info["messageCount"] += 1
            if s["kind"] == "assistant":
                info["messageCount"] += 1
            if s["kind"] == "assistant" and s.get("usage"):
                for k in info["tokens"]:
                    info["tokens"][k] += s["usage"].get(k, 0)
                if s.get("callId") is None or s["callId"] not in seen_calls:
                    if s.get("callId") is not None:
                        seen_calls.add(s["callId"])
                    info["cost"] += s.get("callCostRaw", 0.0)
                    if s.get("priceUnknown"):
                        info["priceUnknown"] = True
                    if not s.get("isLocal"):
                        info["isLocalOnly"] = False
            if s.get("error"):
                info["errors"] += 1
            if info["startTime"] is None and s.get("ts"):
                info["startTime"] = s["ts"]

    if rec["path"]:
        ingest_file(rec["path"], "main")
    for sp in rec["subagentPaths"]:
        aid = sp.rsplit("/", 1)[-1].replace("agent-", "").rsplit(".jsonl", 1)[0]
        for seq, obj in iter_lines(sp):
            if obj is None:
                continue
            if obj.get("type") not in ("user", "assistant"):
                continue
            s = line_to_step(obj, seq, "agent:" + aid)
            if s.get("model") and s["model"] != "<synthetic>":
                models[s["model"]] = models.get(s["model"], 0) + 1
            if s["kind"] == "assistant" and s.get("usage"):
                for k in info["tokens"]:
                    info["tokens"][k] += s["usage"].get(k, 0)
            if s["kind"] == "assistant" and s.get("callId") not in seen_calls:
                seen_calls.add(s["callId"])
                info["cost"] += s.get("callCostRaw", 0.0)
            if s.get("error"):
                info["errors"] += 1
        sub = {
            "agentId": aid,
            "path": sp,
            "size": os.path.getsize(sp) if os.path.exists(sp) else 0,
        }
        # description comes from the Agent tool_use in the main file
        for s in steps:
            for b in s["blocks"]:
                if b["type"] == "tool_use" and (b.get("agentLaunch") or {}).get("agentId") == aid:
                    sub["description"] = b.get("agentLaunch", {}).get("description") or \
                        (b.get("input") or {}).get("description")
                    sub["prompt"] = _s((b.get("input") or {}).get("prompt"))[:200]
                    break
            if sub.get("description"):
                break
        info["subagents"].append(sub)
    info["subagentCount"] = len(info["subagents"])
    info["models"] = sorted(models)
    info["firstPrompt"] = _first_user_prompt(steps)
    info["steps"] = len(steps)
    info["live"] = bool(st and st.st_mtime > 0 and (now - st.st_mtime) < 120)
    for sp in rec["subagentPaths"]:
        try:
            if (now - os.path.getmtime(sp)) < 120:
                info["live"] = True
        except OSError:
            pass
    info["cost"] = round(info["cost"], 6)
    return info


# --------------------------------------------------------------------------
# full graph (for /api/session/<id>)

def session_graph(rec, claude_code_cost=None, now=None):
    now = now or time.time()
    steps_main = []
    if rec["path"]:
        for seq, obj in iter_lines(rec["path"]):
            steps_main.append(line_to_step(obj, seq, "main"))
    steps_main = build_thread_steps(steps_main)

    threads = [{
        "id": "main", "name": "main", "isMain": True,
        "agentId": None, "spawnedByThread": None, "spawnedBy": None,
        "tool": None, "steps": steps_main,
    }]
    for sp in rec["subagentPaths"]:
        aid = sp.rsplit("/", 1)[-1].replace("agent-", "").rsplit(".jsonl", 1)[0]
        tsteps = []
        for seq, obj in iter_lines(sp):
            tsteps.append(line_to_step(obj, seq, "agent:" + aid))
        tsteps = build_thread_steps(tsteps)
        threads.append({
            "id": "agent:" + aid,
            "name": aid[:12],
            "isMain": False,
            "agentId": aid,
            "spawnedByThread": None,
            "spawnedBy": None,
            "tool": None,
            "steps": tsteps,
        })

    # resolve spawn links across ALL threads (agents can spawn their own
    # sub-agents, whose launch tool_use lives in another sidechain file)
    spawn_lookup = {}
    for t in threads:
        for s in t["steps"]:
            for b in s["blocks"]:
                if b["type"] == "tool_use" and (b.get("agentLaunch") or {}).get("agentId"):
                    spawn_lookup.setdefault(b["agentLaunch"]["agentId"], {
                        "thread": t["id"],
                        "stepSeq": s["seq"],
                        "description": b["agentLaunch"].get("description") or
                            _s((b.get("input") or {}).get("description")),
                        "tool": b.get("name"),
                    })
    for t in threads:
        if t["isMain"] or not t["agentId"]:
            continue
        spawned = spawn_lookup.get(t["agentId"])
        if spawned:
            t["spawnedByThread"] = spawned["thread"]
            t["spawnedBy"] = spawned["stepSeq"]
            t["tool"] = spawned["tool"]
            if spawned.get("description"):
                t["name"] = spawned["description"]

    # thread totals (nested under "totals" to avoid clobbering the steps list)
    for t in threads:
        t["totals"] = _thread_totals(t["steps"])

    totals = _aggregate(threads)
    live = False
    last_seq = 0
    if rec["path"]:
        try:
            live = (now - os.path.getmtime(rec["path"])) < 120
            with open(rec["path"], "r", encoding="utf-8", errors="replace") as f:
                last_seq = sum(1 for _ in f)
        except OSError:
            pass
    return {
        "id": rec["id"],
        "dir": rec["dir"],
        "cwd": info_cwd(threads),
        "startTime": _first_ts(threads),
        "totals": totals,
        "claudeCodeCost": claude_code_cost,
        "live": live,
        "lastSeq": last_seq,
        "size": os.path.getsize(rec["path"]) if rec["path"] else 0,
        "mainFile": rec["path"],
        "sparkline": _sparkline(steps_main),
        "threads": threads,
    }


def _thread_totals(steps):
    tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0, "thinking": 0}
    cost = 0.0
    calls = 0
    errors = 0
    for s in steps:
        if s.get("usage"):
            for k in tokens:
                tokens[k] += s["usage"].get(k, 0)
        if s["kind"] == "assistant" and not s.get("sameCall"):
            calls += 1
            cost += s.get("callCost", 0.0)
        if s.get("error"):
            errors += 1
    tokens = {k: v for k, v in tokens.items()}
    return {"tokens": tokens, "cost": round(cost, 6), "calls": calls,
            "errors": errors, "steps": len(steps)}


def _aggregate(threads):
    tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0, "thinking": 0}
    cost = 0.0
    calls = 0
    errors = 0
    nsteps = 0
    for t in threads:
        tt = t.get("totals") or _thread_totals(t["steps"])
        for k in tokens:
            tokens[k] += tt["tokens"][k]
        cost += tt["cost"]
        calls += tt["calls"]
        errors += tt["errors"]
        nsteps += tt["steps"]
    return {"tokens": tokens, "cost": round(cost, 6), "calls": calls,
            "errors": errors, "steps": nsteps,
            "subagents": sum(1 for t in threads if not t["isMain"])}


def _first_ts(threads):
    ts = [s.get("ts") for t in threads for s in t["steps"] if s.get("ts")]
    return min(ts) if ts else None


def info_cwd(threads):
    for t in threads:
        for s in t["steps"]:
            if s.get("cwd"):
                return s["cwd"]
    return None


def _sparkline(steps, max_points=240):
    cost_cum = []
    tok_cum = []
    c = 0.0
    tk = 0
    for s in steps:
        if s["kind"] == "assistant" and not s.get("sameCall"):
            c += s.get("callCost", 0.0)
        if s.get("usage"):
            tk += s["usage"].get("input", 0) + s["usage"].get("output", 0)
        cost_cum.append(round(c, 6))
        tok_cum.append(tk)
    if len(cost_cum) <= max_points:
        return {"cost": cost_cum, "tokens": tok_cum}
    idx = [round(i * (len(cost_cum) - 1) / (max_points - 1)) for i in range(max_points)]
    return {"cost": [cost_cum[i] for i in idx], "tokens": [tok_cum[i] for i in idx]}


# --------------------------------------------------------------------------
# incremental tail

class TailState:
    """Per-session state for /tail: remembers what the client last saw."""

    def __init__(self):
        self.offset = 0          # bytes consumed from the main file
        self.last_seq = 0        # next physical line index to deliver
        self.line_count = 0      # physical lines consumed
        self.tool_index = {}     # tool_use_id -> (thread, step_seq)
        self.steps_emitted = 0


def tail_events(rec, state, after=None):
    """Return new steps delivered after the client's `after` seq.

    Result: {"events": [...], "lastSeq": N, "size": M, "reload": bool,
             "pairs": [{toolUseId, stepSeq, thread, result?/flagError?}]}
    `pairs` let the client attach results / error flags to tool steps that
    were already rendered. `reload: true` means the file was rewritten
    (e.g. compaction) and the client must refetch the full graph.
    """
    path = rec["path"]
    base = {"events": [], "lastSeq": state.last_seq, "size": 0,
            "reload": False, "pairs": []}
    if not path or not os.path.exists(path):
        return base
    size = os.path.getsize(path)
    # client desync guards
    if after is not None and after < state.last_seq:
        # client is behind the server state — only happens after a reset;
        # tell it to refetch the full graph
        base["reload"] = True
        base["lastSeq"] = 0
        return base
    if after is not None and after > state.last_seq:
        # server state was reset (compaction) but the client re-anchored on
        # the new full parse: skip the first `after` physical lines and
        # resume from there
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                n = 0
                while n < after:
                    if not f.readline():
                        break
                    n += 1
                state.offset = f.tell()
        except OSError:
            pass
        state.last_seq = after
        base["lastSeq"] = after
    if size < state.offset:
        # file was rewritten (compaction) — refetch full graph
        state.offset = 0
        state.last_seq = 0
        state.tool_index = {}
        base["size"] = size
        base["reload"] = True
        return base
    if size == state.offset:
        base["size"] = size
        return base

    try:
        f = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        base["size"] = size
        return base
    with f:
        f.seek(state.offset)
        buf = f.read()
    size = os.path.getsize(path)
    partial = not buf.endswith("\n")
    lines = buf.splitlines()
    if partial and lines:
        partial_line = lines[-1]
        lines = lines[:-1]
    else:
        partial_line = None
    state.offset = size if not partial_line else \
        state.offset + (len(buf) - len(partial_line) - 1)

    for line in lines:
        line = line.strip()
        state.last_seq += 1
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        thread = "main"
        if obj.get("isSidechain") and obj.get("agentId"):
            thread = "agent:" + obj["agentId"]
        s = line_to_step(obj, state.last_seq - 1, thread)
        # index tool_use blocks for later pairing
        for b in s["blocks"]:
            if b["type"] == "tool_use" and b.get("id"):
                state.tool_index[b["id"]] = {"thread": thread, "stepSeq": s["seq"]}
        # results: always delivered as pairs; orphan results become steps
        for b in s["blocks"]:
            if b["type"] != "tool_result":
                continue
            content = b.get("content")
            res_text, res_len, truncated = _truncate(_result_text({"content": content}))
            persisted = None
            pm = PERSISTED_RE.search(res_text)
            if pm:
                persisted = pm.group(1)
            reason = detect_tool_error(b.get("isError"), res_text)
            res = {
                "text": res_text, "len": res_len, "truncated": truncated,
                "persisted": persisted, "isError": bool(b.get("isError")),
                "errorReason": reason,
            }
            tur = b.get("toolUseResult")
            launch = None
            if tur and isinstance(tur, dict) and tur.get("agentId"):
                launch = {k: tur.get(k) for k in
                          ("agentId", "description", "status", "resolvedModel")}
                b["agentLaunch"] = launch
                s["spawnedAgents"] = (s.get("spawnedAgents") or []) + [tur["agentId"]]
                for b2 in s["blocks"]:
                    if b2["type"] == "tool_use" and \
                            (b2.get("agentLaunch") or {}).get("agentId") == tur.get("agentId"):
                        b2["agentLaunch"] = launch
            prior = state.tool_index.get(b.get("id"))
            if prior is not None:
                pair = {"toolUseId": b["id"],
                        "stepSeq": prior["stepSeq"], "thread": prior["thread"]}
                if launch:
                    pair["agentLaunch"] = launch
                pair["result"] = res
                base["pairs"].append(pair)
                if reason:
                    base["pairs"].append(dict(pair, result=None,
                                              flagError=True,
                                              errorReason=reason))
            else:
                b["result"] = res
                b["resultError"] = bool(b.get("isError")) or bool(reason)
        # cost for the (possibly single) response line
        if s["kind"] == "assistant":
            u = s.get("usage") or {}
            cost, unknown, local, matched, _t = lens_cost.cost_for_usage(u, s.get("model"))
            s["callCost"] = round(cost, 8)
            s["priceUnknown"] = unknown
            s["isLocal"] = local
            s["sameCall"] = False
        # result-only user steps are not timeline steps — drop them
        if s["kind"] == "user" and s.get("isResultOnly"):
            continue
        # keep payload small: truncate raw content on emitted result blocks
        for b in s["blocks"]:
            if b["type"] == "tool_result":
                b["content"] = None
                b["text"] = (b.get("result") or {}).get("text", "")[:512]
        base["events"].append(s)
        state.steps_emitted += 1

    base["size"] = size
    return base


def init_tail_state(rec, full_graph):
    """Initialize TailState from a full parse so /tail starts clean."""
    st = TailState()
    if rec["path"]:
        st.offset = os.path.getsize(rec["path"])
        # physical line count (steps may be fewer: result-only lines folded)
        with open(rec["path"], "r", encoding="utf-8", errors="replace") as f:
            st.last_seq = sum(1 for _ in f)
    for t in full_graph["threads"]:
        for s in t["steps"]:
            for b in s["blocks"]:
                if b["type"] == "tool_use" and b.get("id"):
                    st.tool_index[b["id"]] = {"thread": t["id"], "stepSeq": s["seq"]}
    return st
