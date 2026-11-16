/* Mads-Lens — single-page client. No frameworks, no CDNs. */
"use strict";

// ---------------------------------------------------------------------------
// tiny helpers

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function fmtTok(n) {
  if (!n) return "0";
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(Math.round(n));
}
function fmtCost(c) {
  if (!c) return "$0";
  if (c < 0.01) return "$" + c.toFixed(4);
  if (c < 100) return "$" + c.toFixed(2);
  return "$" + Math.round(c);
}
function fmtDur(ms) {
  if (ms == null) return "";
  if (ms < 1000) return Math.round(ms) + "ms";
  if (ms < 60000) return (ms / 1000).toFixed(1) + "s";
  return Math.floor(ms / 60000) + "m" + Math.round((ms % 60000) / 1000) + "s";
}
function relTime(t) {
  if (!t) return "";
  const d = new Date(t);
  if (isNaN(d)) return "";
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  if (s < 86400 * 30) return Math.floor(s / 86400) + "d ago";
  return d.toISOString().slice(0, 10);
}
function clockTime(t) {
  const d = new Date(t);
  if (isNaN(d)) return "";
  return d.toISOString().slice(11, 19) + "Z";
}
// markdown-lite: escape, then **bold**, `code`, inline tags left escaped
function mdLite(s) {
  let h = esc(s);
  h = h.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  h = h.replace(/`([^`]+)`/g, "<code class=\"inline-code\">$1</code>");
  return h;
}
// JSON syntax highlight: escape first, then annotate via a single regex pass
function highlightJSON(obj) {
  let s;
  try { s = JSON.stringify(obj, null, 2); }
  catch (e) { return esc(String(obj)); }
  s = esc(s);
  return s.replace(
    /(&quot;(?:\\.|[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(true|false|null)\b|-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b/g,
    (m, str, colon, lit) => {
      if (lit) return `<span class="j-lit">${lit}</span>`;
      if (str) return colon
        ? `<span class="j-key">${str}</span>${colon}`
        : `<span class="j-str">${str}</span>`;
      return m;
    }
  );
}
function prettyInput(input) {
  if (input == null) return null;
  if (typeof input === "string") return input;
  if (input.__unparsed) {
    return String(input.raw || "") + (input.len != null ? `\n…(${input.len} bytes, unparsed)` : "");
  }
  try { return JSON.stringify(input, null, 2); } catch (e) { return String(input); }
}

// ---------------------------------------------------------------------------
// app state

const App = {
  sessions: [],          // /api/sessions rows
  sessionFilter: "",
  current: null,         // { id, graph, after, pollTimer, els, toolEls, live }
  filter: "all",         // all | errors | tools | text | meta
  expandedThinking: false,
};

// ---------------------------------------------------------------------------
// sidebar

async function loadSessions() {
  let data;
  try {
    const r = await fetch("api/sessions");
    data = await r.json();
  } catch (e) {
    $("#root-label").textContent = "server unreachable";
    return;
  }
  App.sessions = data.sessions;
  $("#root-label").textContent = data.root || "";
  renderSessions();
  const foot = $("#sidebar-foot");
  const live = App.sessions.filter(s => s.live).length;
  const err = App.sessions.reduce((a, s) => a + (s.errors || 0), 0);
  foot.textContent = `${App.sessions.length} sessions · ${live} live · ${err} errors`;
}

function renderSessions() {
  const list = $("#session-list");
  list.innerHTML = "";
  const f = App.sessionFilter.toLowerCase();
  for (const s of App.sessions) {
    const hay = [s.dir, s.firstPrompt, (s.models || []).join(" "), s.id, s.cwd].join(" ").toLowerCase();
    if (f && !hay.includes(f)) continue;
    const row = el("div", "session" + (App.current && App.current.id === s.id ? " active" : ""));
    row.dataset.id = s.id;

    const dir = el("div", "s-dir");
    if (s.live) dir.append(el("span", "dot live", "live"));
    if (s.errors) dir.append(el("span", "dot err", `${s.errors} err`));
    dir.append(document.createTextNode(" " + s.dir.replace(/^-Users-/, "") + " · " + relTime(s.mtime * 1000)));
    row.append(dir);

    row.append(el("div", "s-prompt", s.firstPrompt || (s.cwd || s.id.slice(0, 8))));

    const meta = el("div", "s-meta");
    const toks = s.tokens || {};
    const tokStr = `in ${fmtTok(toks.input)} / out ${fmtTok(toks.output)}` +
      (toks.cache_read ? ` / cache ${fmtTok(toks.cache_read)}` : "");
    meta.append(document.createTextNode(s.messageCount + " msgs · " + tokStr));
    if (s.subagentCount) meta.append(el("span", "", ` ⬢${s.subagentCount} `));
    if (s.cost > 0) meta.append(el("span", "s-cost", " " + fmtCost(s.cost)));
    else if (s.isLocalOnly && s.messageCount > 0) meta.append(el("span", "s-cost", " local"));
    row.append(meta);

    row.onclick = () => openSession(s.id);
    list.append(row);
  }
}
$("#search").addEventListener("input", e => {
  App.sessionFilter = e.target.value.trim();
  renderSessions();
});

// ---------------------------------------------------------------------------
// top bar

function renderTopBar(g, sum) {
  const bar = el("div", "topbar");
  const r1 = el("div", "topbar-row1");
  const h = document.createElement("h1");
  h.append(document.createTextNode(g.dir.replace(/^-/, "") + "  "));
  h.append(el("span", "sid", g.id.slice(0, 8)));
  r1.append(h);
  for (const m of (sum ? sum.models : uniqueModels(g))) {
    const c = el("span", "chip", m);
    c.title = "model";
    r1.append(c);
  }
  if (g.live) r1.append(el("span", "chip live", "● live"));
  bar.append(r1);

  const st = g.totals || {};
  const tk = st.tokens || {};
  const stats = el("div", "stats");
  const mk = (label, val, cls) => {
    const s = el("span", cls);
    s.append(document.createTextNode(label + " "));
    s.append(el("b", "", val));
    return s;
  };
  stats.append(mk("cost", fmtCost(st.cost), "cost"));
  if (g.claudeCodeCost != null && g.claudeCodeCost > 0)
    stats.append(mk("claude-code", fmtCost(g.claudeCodeCost), "cost"));
  stats.append(mk("in", fmtTok(tk.input)));
  stats.append(mk("out", fmtTok(tk.output)));
  if (tk.cache_read || tk.cache_create)
    stats.append(mk("cache", fmtTok(tk.cache_read) + "r/" + fmtTok(tk.cache_create) + "w"));
  stats.append(mk("calls", st.calls || 0));
  stats.append(mk("steps", st.steps || 0));
  if (st.subagents) stats.append(mk("agents", st.subagents));
  if (st.errors) stats.append(mk("errors", st.errors, "err"));
  bar.append(stats);

  // sparkline
  const spark = el("div", "spark");
  const c1 = drawSpark(g.sparkline && g.sparkline.cost || [], "#38d39f", "cumulative cost");
  const c2 = drawSpark(g.sparkline && g.sparkline.tokens || [], "#5aa9ff", "cumulative tokens");
  spark.append(c1, c2);
  bar.append(spark);
  bar._spark = [c1._canvas, c2._canvas];

  // filters
  const fl = el("div", "filters");
  const mkBtn = (id, label, cls) => {
    const b = el("button", "fbtn" + (App.filter === id ? " on" + (cls ? " " + cls : "") : ""), label);
    b.dataset.f = id;
    b.onclick = () => { App.filter = id; $$(".fbtn", fl).forEach(x => x.classList.remove("on", "err")); b.classList.add("on"); if (cls) b.classList.add(cls); applyFilters(); };
    return b;
  };
  fl.append(mkBtn("all", "all"), mkBtn("errors", `${st.errors || 0} errors`, "err"),
    mkBtn("tools", "tools"), mkBtn("text", "text"));
  const exp = el("button", "fbtn", "expand results");
  exp.onclick = () => toggleAllResults(true);
  const col = el("button", "fbtn", "collapse results");
  col.onclick = () => toggleAllResults(false);
  fl.append(exp, col);
  if (st.errors) {
    const jump = el("button", "fbtn", "jump to errors ▾");
    jump.id = "err-jump";
    jump.onclick = () => {
      const l = $("#err-list");
      if (!l) { const nl = el("div"); nl.id = "err-list"; fl.after(nl); jump.onclick = () => { nl.style.display = nl.style.display === "none" ? "block" : "none"; }; nl.style.display = "block"; fillErrList(nl); }
      else { l.style.display = l.style.display === "none" ? "block" : "none"; }
    };
    fl.append(jump);
  }
  bar.append(fl);
  if (st.errors) {
    const l = el("div"); l.id = "err-list";
    bar.append(l);
    fillErrList(l);
  }
  return bar;
}
function uniqueModels(g) {
  const m = new Set();
  for (const t of g.threads) for (const s of t.steps)
    if (s.kind === "assistant" && s.model && s.model !== "<synthetic>") m.add(s.model);
  return [...m];
}
function drawSpark(values, color, label) {
  const W = 260, H = 44;
  const box = el("div", "spark-box");
  const c = document.createElement("canvas");
  c.width = W * 2; c.height = H * 2;
  c.style.width = W + "px"; c.style.height = H + "px";
  const ctx = c.getContext("2d");
  ctx.scale(2, 2);
  if (values.length > 1) {
    const max = Math.max(...values, 1e-9);
    ctx.beginPath();
    values.forEach((v, i) => {
      const x = i / (values.length - 1) * (W - 8) + 4;
      const y = H - 6 - (v / max) * (H - 14);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.lineTo(W - 4, H - 4); ctx.lineTo(4, H - 4); ctx.closePath();
    ctx.fillStyle = color + "22"; ctx.fill();
  }
  const lab = el("div", "spark-label", label);
  box.append(c, lab);
  box._canvas = c;
  return box;
}
function redrawSparks(g) {
  const bar = App.current && $("#topbar");
  if (!bar || !bar._spark) return;
  const vals = g.sparkline || { cost: [], tokens: [] };
  redrawOne(bar._spark[0], vals.cost, "#38d39f");
  redrawOne(bar._spark[1], vals.tokens, "#5aa9ff");
}
function redrawOne(box, values, color) {
  const c = box._canvas, ctx = c.getContext("2d");
  const W = 260, H = 44;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.scale(2, 2);
  if (values.length > 1) {
    const max = Math.max(...values, 1e-9);
    ctx.beginPath();
    values.forEach((v, i) => {
      const x = i / (values.length - 1) * (W - 8) + 4;
      const y = H - 6 - (v / max) * (H - 14);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();
  }
  ctx.restore();
}
function fillErrList(l) {
  l.innerHTML = "";
  const g = App.current && App.current.graph;
  if (!g) return;
  const errs = [];
  for (const t of g.threads) for (const s of t.steps)
    if (s.error) errs.push({ t, s, reason: s.errorReason || "" });
  for (const e of errs.slice(0, 40)) {
    const it = el("div", "e-item", `⚠ ${e.s.kind} · ${e.reason || "error"}`);
    it.title = e.reason || "";
    it.onclick = () => {
      const stepEl = $(`[data-seq="${e.s.seq}"][data-thread="${e.t.id}"]`, App.current.root);
      if (stepEl) {
        stepEl.scrollIntoView({ behavior: "smooth", block: "center" });
        stepEl.classList.add("flash");
        setTimeout(() => stepEl.classList.remove("flash"), 1600);
      }
    };
    l.append(it);
  }
}

// ---------------------------------------------------------------------------
// step rendering

const TRUNC_RESULT = 4096;
let toolSeq = 0;

function renderStep(s, parent, threadId, thread) {
  const card = el("div", "step " + s.kind);
  card.dataset.thread = threadId;
  card.dataset.seq = s.seq;
  if (s.error) card.classList.add("error");
  if (s.kind === "user" && (s.isSynthetic || s.isMeta)) card.classList.add("synth");

  const head = el("div", "s-head");
  const role = el("span", "role",
    s.kind === "user" ? (s.isSynthetic ? "user (synthetic)" : "user") :
    s.kind === "assistant" ? "assistant" :
    s.kind === "system" ? "system" :
    s.kind === "meta" ? (s.label || "meta") :
    s.kind === "raw" ? (s.label || "raw") : s.kind);
  head.append(role);
  if (s.kind === "assistant") {
    if (s.model) head.append(el("span", "model", s.model));
    if (s.isLocal) head.append(el("span", "badge local", "local"));
    if (s.priceUnknown) head.append(el("span", "badge unknown", "price?"));
  }
  if (s.kind === "user" && s.isMeta) head.append(el("span", "badge", "meta"));
  if (s.sameCall) head.append(el("span", "badge", "same call"));
  if (s.error) head.append(el("span", "badge err", s.errorReason ? s.errorReason.slice(0, 60) : "error"));
  // token + cost badge
  const u = s.usage;
  if (s.kind === "assistant" && u && (u.input || u.output || u.cache_read || u.cache_create)) {
    let b = `↑${fmtTok(u.input + u.cache_read + u.cache_create)} ↓${fmtTok(u.output)}`;
    if (u.thinking) b += ` (th ${fmtTok(u.thinking)})`;
    const badge = el("span", "badge" + (s.callCost > 0 ? " cost" : ""),
      b + (s.callCost > 0 ? ` · ${fmtCost(s.callCost)}` : ""));
    if (u.cache_read) badge.title = `input ${u.input} · cache read ${u.cache_read} · cache write ${u.cache_create} · output ${u.output} (incl. thinking ${u.thinking})`;
    head.append(badge);
  }
  if (s.ts) head.append(el("span", "ts", clockTime(s.ts)));
  card.append(head);

  const body = el("div", "s-body");
  card.append(body);

  for (const b of s.blocks || []) {
    if (b.type === "text") body.append(renderText(b, s));
    else if (b.type === "thinking") body.append(renderThinking(b, s));
    else if (b.type === "tool_use") body.append(renderTool(b, s, threadId, thread));
    else if (b.type === "tool_result") body.append(renderResultBlock(b));
    else if (b.type === "meta") body.append(el("div", "meta-line", b.label || ""));
  }
  // system / meta single-line
  if ((s.kind === "system" || s.kind === "meta" || s.kind === "raw") && !s.blocks.length) {
    body.append(el("div", "meta-line", s.text || s.note || s.label || ""));
  }
  if (s.kind === "user" && s.taskIds && s.taskIds.length) {
    const tn = el("div", "tasknote");
    tn.append(el("span", "badge", "task"));
    for (const tid of s.taskIds) {
      const c = el("span", "chip", "⬢ " + tid.slice(0, 8));
      c.title = "jump to agent " + tid;
      c.onclick = (e) => { e.stopPropagation(); jumpToAgent(tid); };
      tn.append(c);
    }
    body.append(tn);
  }
  return card;
}

function renderText(b, s) {
  const d = el("div", "text" + (s.isSynthetic ? " synth-text" : ""));
  d.innerHTML = mdLite(b.text || "");
  return d;
}
function renderThinking(b, s) {
  const det = document.createElement("details");
  det.className = "thinking";
  if (App.expandedThinking) det.open = true;
  const sum = el("summary", "", "thinking" + (b.durationMs ? ` (${fmtDur(b.durationMs)})` : ""));
  const bd = el("div", "thinking-body", b.text || "");
  det.append(sum, bd);
  return det;
}
function renderResultBlock(b) {
  // orphan/mixed tool_result rendered in place
  const txt = (b.result || {}).text || b.text || "";
  if (!txt && !(b.result || {})) return null;
  const w = el("div");
  w.append(el("div", "io-label", "result" + (b.isError ? " (error)" : "")));
  w.append(resultPre(txt, (b.result || {}).truncated, b.isError,
    b.result ? b.result.len : undefined, b.errorReason));
  return w;
}
function resultPre(text, truncated, isError, fullLen, reason) {
  const wrap = el("div");
  const pre = document.createElement("pre");
  pre.className = "code" + (isError ? " j-err-host" : "");
  pre.textContent = text;
  wrap.append(pre);
  if (reason) {
    wrap.append(el("div", "err-reason", "⚠ " + reason));
  }
  if (truncated && text) {
    wrap.append(el("span", "res-note",
      `… truncated at ${text.length}` + (fullLen ? ` of ${fullLen} chars` : "") +
      " (full output not transmitted)"));
  }
  return wrap;
}

function renderTool(b, s, threadId, thread) {
  const det = document.createElement("details");
  det.className = "tool" + (b.resultError ? " err" : "") + (s.error ? " err" : "");
  det.dataset.toolUseId = b.id || "";
  det.open = !s.error;   // open by default; errors stay open for inspection
  if (b.id && App.current) App.current.toolEls.set(b.id, det);

  const head = el("div", "tool-head");
  head.append(el("span", "tool-toggle", ""));
  head.append(el("span", "t-name", (b.name || "tool").replace(/^./, c => c)));
  head.append(el("span", "t-arg", toolArgSummary(b)));
  const status = el("span", "t-status " +
    (b.result == null ? "pending" : b.resultError ? "err" : "ok"),
    b.result == null ? "…" : b.resultError ? "✗ " + (b.resultError || "error") : "✓ " +
      (b.result && b.result.len != null ? fmtTok(b.result.len) : "done"));
  head.append(status);
  det.append(head);

  const io = el("div", "tool-io");
  // input
  const inStr = prettyInput(b.input);
  if (inStr != null) {
    io.append(el("div", "io-label", "input"));
    const ip = document.createElement("pre");
    ip.className = "code";
    let show = inStr.length > 8192 ? inStr.slice(0, 8192) + "\n…" : inStr;
    ip.innerHTML = inStr.startsWith("{") || inStr.startsWith("[") ? highlightJSONObj(b.input) : esc(show);
    if (inStr.length > 8192) {
      const btn = el("button", "expand-btn", "expand full input");
      btn.onclick = () => { ip.textContent = inStr; btn.remove(); };
      ip.after(btn);
    }
    io.append(ip);
  }
  // result
  if (b.result != null) {
    const rw = el("div");
    rw.append(el("div", "io-label", "output" + (b.resultError ? "  ⚠ error" : "")));
    rw.append(resultPre(b.result.text, b.result.truncated, b.resultError));
    if (b.result.persisted) rw.append(el("div", "res-note", "full output persisted: " + b.result.persisted));
    io.append(rw);
  }
  // error reason (from content patterns even when isError was unset)
  if (s.error && !b.resultError && s.errorReason && !s.isSynthetic) {
    io.append(el("div", "res-note", "⚠ " + s.errorReason));
  }
  // subagent tree
  for (const aid of b.agentLaunch ? [b.agentLaunch.agentId] : []) {
    const t = threadById(aid);
    if (t) io.append(renderAgentTree(t, b));
  }
  det.append(io);
  return det;
}
function highlightJSONObj(obj) {
  let s;
  try { s = JSON.stringify(obj, null, 2); } catch (e) { return esc(String(obj)); }
  const e = esc(s);
  return e.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&")
    .replace(/("[^"]*")(\s*:)/g, '<span class="j-key">$1</span>$2')
    .replace(/: ("(?:\\.|[^"\\])*")/g, ': <span class="j-str">$1</span>');
}
function toolArgSummary(b) {
  const i = b.input || {};
  if (typeof i === "string") return i.slice(0, 80);
  const pick = ["command", "file_path", "path", "pattern", "prompt", "description", "url", "query", "code", "url", "dest"];
  for (const k of pick) {
    if (i[k] != null) {
      let v = String(i[k]);
      if (k === "command") v = v.split("\n")[0];
      return v.slice(0, 90) + (v.length > 90 ? "…" : "");
    }
  }
  return b.name ? "" : "";
}
function threadById(agentId) {
  if (!App.current) return null;
  return App.current.graph.threads.find(t => t.agentId === agentId);
}
function jumpToAgent(agentId) {
  const t = threadById(agentId);
  if (!t) return;
  const det = $(`[data-agent-thread="${t.id}"]`, App.current.root);
  if (det) {
    det.open = true;
    det.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

// agent thread card (nested tree; recursive for nested agents)
function renderAgentTree(t, launchBlock) {
  const det = document.createElement("details");
  det.className = "agent";
  det.dataset.agentThread = t.id;
  const sum = el("summary");
  const tt = t.totals || {};
  const tk = tt.tokens || {};
  sum.append(document.createTextNode(`⬢ ${t.name}`));
  if (t.spawnedBy != null) sum.append(el("span", "badge", "started step " + t.spawnedBy));
  sum.append(el("span", "badge", `${tt.steps || 0} steps`));
  sum.append(el("span", "badge", `↑${fmtTok(tk.input)} ↓${fmtTok(tk.output)}`));
  if (tt.cost > 0) sum.append(el("span", "badge cost", fmtCost(tt.cost)));
  if (tt.errors) sum.append(el("span", "badge err", tt.errors + " err"));
  det.append(sum);
  const body = el("div", "agent-body");
  const tl = el("div", "agent-tl");
  const mainSteps = t.steps;
  for (const s of mainSteps) tl.append(renderStep(s, body, t.id, t));
  body.append(tl);
  // nested agents: threads spawned by THIS thread, attached under their launch step
  const children = App.current.graph.threads.filter(x => x.spawnedByThread === t.id);
  if (children.length) {
    for (const c of children) {
      const host = $(`[data-seq="${c.spawnedBy}"]`, tl);
      const spot = host ? $(".tool-io", host) || host : tl;
      const block = host ? $$(".tool", host).find(d => (d.dataset.toolUseId && true)) : null;
      // simplest robust attach: find the tool details whose launch agentId == c.agentId
      let attached = false;
      for (const toolDet of $$(".tool", host || tl)) {
        const inner = $(`[data-agent-thread="${c.id}"]`, toolDet);
        if (inner) { attached = true; break; }
      }
      if (!attached) {
        // render as a nested tree in the first tool block, or at end
        const target = (host && $(".tool-io", host)) || tl;
        const cDet = renderAgentTree(c, null);
        cDet.open = false;
        target.append(cDet);
      }
    }
  }
  det.append(body);
  return det;
}
function renderAgentTreeLite(c) {
  // placeholder used before final attach (kept minimal: summary only)
  const det = document.createElement("details");
  det.className = "agent";
  det.dataset.agentThread = c.id;
  const tt = c.totals || {};
  det.append(el("summary", "", `⬢ ${c.name} (${tt.steps || 0} steps)`));
  return det;
}

// ---------------------------------------------------------------------------
// filters

function applyFilters() {
  if (!App.current) return;
  const f = App.filter;
  for (const c of $$(".step", App.current.root)) {
    const kind = c.classList.contains("assistant") ? "assistant" :
      c.classList.contains("user") ? "user" :
      c.classList.contains("system") ? "system" :
      c.classList.contains("meta") ? "meta" :
      c.classList.contains("raw") ? "raw" : "?";
    const hasErr = c.classList.contains("error");
    const hasTool = $$(".block, .tool, details.tool", c).length > 0 ||
      $$(".tool", c).length > 0 || (kind === "assistant" && $$(".tool", c).length > 0);
    let show = true;
    if (f === "errors") show = hasErr;
    else if (f === "tools") show = kind === "assistant" && $$(".tool", c).length > 0;
    else if (f === "text") show = (kind === "user" && !c.classList.contains("synth")) || (kind === "assistant" && $$(".text", c).some(x => x.textContent.trim().length > 0));
    else if (f === "meta") show = kind === "meta" || kind === "system" || kind === "raw";
    // default: meta/raw dimmed but visible; hide pure noise? keep visible
    c.classList.toggle("hidden-by-filter", !show);
  }
}

function toggleAllResults(open) {
  if (!App.current) return;
  for (const d of $$("details.tool, details.thinking", App.current.root)) d.open = open;
}

// ---------------------------------------------------------------------------
// session open

async function openSession(id) {
  $$(".session").forEach(x => x.classList.toggle("active", x.dataset.id === id));
  stopPolling();
  const main = $("#main");
  App.current = null;
  $("#empty").hidden = true;
  const sessionEl = $("#session");
  sessionEl.innerHTML = "";
  sessionEl.append(el("div", "empty", "loading " + id.slice(0, 8) + " …"));
  let g, sum = null;
  try {
    g = await (await fetch("api/session/" + encodeURIComponent(id))).json();
  } catch (e) {
    sessionEl.innerHTML = "";
    sessionEl.append(el("div", "empty", "could not load session: " + e));
    return;
  }
  const row = App.sessions.find(s => s.id === id);
  sum = row || null;
  sessionEl.innerHTML = "";
  App.current = {
    id, graph: g, summary: sum,
    after: g.lastSeq || 0,
    pollTimer: null, idleStreak: 0,
    toolEls: new Map(),
    root: sessionEl,
    atBottom: true,
  };
  // top bar + timeline
  sessionEl.append(renderTopBar(g, sum));
  const tl = el("div", "timeline");
  const mainT = g.threads.find(t => t.isMain) || g.threads[0];
  for (const s of mainT.steps) tl.append(renderStep(s, tl, mainT.id, mainT));
  // agents spawned by main: attach under their launch step
  const mainKids = g.threads.filter(t => t.spawnedByThread === "main");
  for (const c of mainKids) {
    const host = $(`[data-seq="${c.spawnedBy}"]`, tl);
    if (!host) { tl.append(renderAgentTree(c, null)); continue; }
    let spot = null;
    for (const toolDet of $$(".tool", host)) {
      if ($(`[data-agent-thread="${c.id}"]`, toolDet)) { spot = null; break; }
    }
    const target = $(".tool-io", host) || host;
    const cDet = renderAgentTree(c, null);
    cDet.open = false;
    target.append(cDet);
  }
  // fully detached agents (no spawn link resolvable)
  const detached = g.threads.filter(t => !t.isMain && t.spawnedByThread == null && t.spawnedBy == null);
  if (detached.length) {
    tl.append(el("div", "io-label", "detached agents (spawn link not found in this file)"));
    for (const c of detached) { const d = renderAgentTree(c, null); d.open = false; tl.append(d); }
  }
  sessionEl.append(tl);
  applyFilters();
  // auto-scroll to top of the session
  main.scrollTop = 0;
  // live polling
  if (g.live) startPolling();
  else updateLiveChip(false);
}

function updateLiveChip(live) {
  if (!App.current) return;
  const chip = $(".chip.live", $("#topbar"));
  if (live && !chip) {
    const c = el("span", "chip live", "● live");
    $("h1", $("#topbar")).after(c);
  } else if (!live && chip) chip.remove();
}

// ---------------------------------------------------------------------------
// live tail

function startPolling() {
  stopPolling();
  App.current.pollTimer = setInterval(pollTail, 2000);
  updateLiveChip(true);
}
function stopPolling() {
  if (App.current && App.current.pollTimer) clearInterval(App.current.pollTimer);
  if (App.current) App.current.pollTimer = null;
  updateLiveChip(false);
}

async function pollTail() {
  const cur = App.current;
  if (!cur) return;
  let r;
  try {
    r = await (await fetch(`api/session/${encodeURIComponent(cur.id)}/tail?after=${cur.after}`)).json();
  } catch (e) { return; }
  if (r.reload) {
    // file rewritten (compaction): refetch everything
    openSession(cur.id);
    return;
  }
  cur.after = r.lastSeq != null ? r.lastSeq : cur.after;
  const added = (r.events || []).length + (r.pairs || []).length;
  if (!added) {
    cur.idleStreak++;
    if (cur.idleStreak >= 15) stopPolling();   // no growth for 30s
    return;
  }
  cur.idleStreak = 0;
  updateLiveChip(true);
  if (!document.hidden) applyTail(r);
  else App.current._pending = mergeEvents(App.current._pending, r);
}

function mergeEvents(a, b) {
  return {
    events: (a ? a.events : []).concat(b.events || []),
    pairs: (a ? a.pairs : []).concat(b.pairs || []),
    lastSeq: b.lastSeq,
  };
}

function applyTail(r) {
  const cur = App.current;
  const g = cur.graph;
  const tl = $(".timeline", cur.root);
  if (!tl) return;
  const nearBottom = cur.root.scrollTop + cur.root.clientHeight > cur.root.scrollHeight - 200;
  const wasBottom = nearBottom;
  const threadEls = new Map();   // thread id -> { stepsEl, thread }
  const mainT = g.threads.find(t => t.isMain);
  const pushStep = (s) => {
    let tid = s.thread;
    let t = g.threads.find(x => x.id === tid);
    let host;
    if (!t) {
      // new sidechain thread appears live
      t = { id: tid, name: (s.agentId || tid).slice(0, 12), isMain: false, agentId: s.agentId || tid.slice(6),
            steps: [], totals: { tokens: { input: 0, output: 0, cache_read: 0, cache_create: 0, thinking: 0 }, cost: 0, calls: 0, errors: 0, steps: 0 } };
      g.threads.push(t);
    }
    if (t.isMain) host = tl;
    else {
      const det = $(`[data-agent-thread="${t.id}"]`, cur.root);
      host = det && $(".agent-tl", det);
      if (!host) return; // thread card not rendered yet; will show on reload
    }
    t.steps.push(s);
    const card = renderStep(s, host, t.id, t);
    host.append(card);
    t.totals.steps = t.steps.length;
    if (s.usage) {
      for (const k in t.totals.tokens) t.totals.tokens[k] += s.usage[k] || 0;
      t.totals.cost += s.callCost || 0;
    }
    if (s.callId) t.totals.calls = (t.totals.calls || 0) + 1;
    if (s.error) t.totals.errors = (t.totals.errors || 0) + 1;
  };
  // pairs first (attach results to existing tools), then steps
  for (const p of r.pairs || []) {
    const key = p.toolUseId;
    const det = cur.toolEls.get(key) || $(`[data-tool-use-id="${cssEsc(key)}"]`, cur.root);
    if (!det) continue;
    if (p.result) {
      const b = fakeToolBlockWithResult(det, p);
      // replace pending status
      const st = $(".t-status", det);
      if (st) { st.className = "t-status " + (p.flagError ? "err" : "ok"); st.textContent = p.flagError ? "✗ " + (p.errorReason || "error") : "✓ done"; }
      const io = $(".tool-io", det);
      if (io && !io.querySelector(".io-label.output")) {
        const rw = el("div");
        rw.append(el("div", "io-label", "output" + (p.flagError ? "  ⚠ error" : "")));
        rw.append(resultPre(p.result.text, p.result.truncated, p.flagError));
        io.append(rw);
        det.classList.toggle("err", !!p.flagError);
      }
      if (p.agentLaunch) {
        const t = g.threads.find(x => x.agentId === p.agentLaunch.agentId);
        if (t) { const c = renderAgentTree(t, null); c.open = false; io.append(c); }
      }
    } else if (p.flagError) {
      const st = $(".t-status", det);
      if (st) { st.className = "t-status err"; st.textContent = "✗ " + (p.errorReason || "error"); }
      det.classList.add("err");
    }
  }
  for (const s of r.events || []) pushStep(s);
  // update totals + sparkline
  g.totals.steps += (r.events || []).length;
  g.totals.errors += (r.events || []).filter(s => s.error).length;
  for (const s of r.events || []) {
    if (s.usage) {
      for (const k in g.totals.tokens) g.totals.tokens[k] += s.usage[k] || 0;
      g.totals.cost = (g.totals.cost || 0) + (s.callCost || 0);
    }
  }
  g.sparkline.cost.push(g.totals.cost);
  g.sparkline.tokens.push(g.totals.tokens.input + g.totals.tokens.output);
  if (g.sparkline.cost.length > 400) { g.sparkline.cost.splice(0, g.sparkline.cost.length - 400); g.sparkline.tokens.splice(0, 200); }
  const stats = $$(".stats b", $("#topbar"));
  // cheap: rewrite the stats numbers
  const bar = $("#topbar");
  const tt = g.totals, tk = tt.tokens;
  $$(".stats > span", bar).forEach((sp, i) => {
    const labels = ["cost", "in", "out", "calls", "steps", "errors"];
    const b = $("b", sp);
    if (!b) return;
    const lbl = sp.textContent;
    if (lbl.startsWith("cost")) b.textContent = fmtCost(tt.cost);
    else if (lbl.startsWith("in")) b.textContent = fmtTok(tk.input);
    else if (lbl.startsWith("out")) b.textContent = fmtTok(tk.output);
    else if (lbl.startsWith("calls")) b.textContent = tt.calls;
    else if (lbl.startsWith("steps")) b.textContent = tt.steps;
    else if (lbl.startsWith("errors")) b.textContent = tt.errors;
  });
  redrawSparks(g);
  if (wasBottom) cur.root.scrollTop = cur.root.scrollHeight;
  applyFilters();
}
function cssEsc(s) { return s.replace(/[^a-zA-Z0-9_-]/g, ""); }
function fakeToolBlockWithResult(det, p) { return null; }

// flush pending (accumulated while tab hidden)
setInterval(() => {
  const cur = App.current;
  if (cur && cur._pending) {
    applyTail(cur._pending);
    cur._pending = null;
  }
}, 3000);

// ---------------------------------------------------------------------------
// boot

$("#search"); // no-op, keeps linters quiet
loadSessions();
setInterval(() => { if (!App.current || !App.current.pollTimer) loadSessions(); }, 30000);
