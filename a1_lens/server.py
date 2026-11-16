#!/usr/bin/env python3
"""Mads-Lens — a trustworthy web UI for Claude Code sessions.

CS2680 A1 deliverable. Serves:

    GET /api/sessions                  list of sessions (newest first)
    GET /api/session/<id>              full parsed event graph (threads + steps)
    GET /api/session/<id>/tail?after=N incremental events for live tailing
    GET /                             static UI (index.html / app.js / style.css)

Python stdlib only, runs on 3.9. Read-only: it never writes into the
projects directory.

    python3 server.py [--port 8787] [--root ~/.claude/projects]
"""

import argparse
import json
import os
import re
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lens_parser import (  # noqa: E402
    discover_sessions, session_summary, session_graph,
    tail_events, init_tail_state,
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ID_RE = re.compile(r"^[0-9a-zA-Z._-]+$")

# --------------------------------------------------------------------------
# state + caching (read-only view of the log directory)

class Store:
    def __init__(self, root):
        self.root = root
        self.lock = threading.Lock()
        self.sessions = []            # discovery records
        self._summary_cache = {}      # id -> (mtime, size, summary dict)
        self._graph_cache = {}        # id -> (mtime, size, graph dict)
        self._tails = {}              # id -> TailState
        self._discovered_at = 0.0

    def discover(self, force=False):
        now = time.time()
        if not force and self.sessions and now - self._discovered_at < 15:
            return
        with self.lock:
            self.sessions = discover_sessions(self.root)
            self._discovered_at = now

    def get(self, sid):
        for s in self.sessions:
            if s["id"] == sid:
                return s
        return None

    def summary(self, sid):
        rec = self.get(sid)
        if rec is None:
            return None
        key = (rec["path"],) + tuple(rec["subagentPaths"])
        st = os.stat(rec["path"]) if rec["path"] else None
        msize = st.st_mtime if st else 0
        ssize = st.st_size if st else 0
        for p in rec["subagentPaths"]:
            try:
                st2 = os.stat(p)
                msize = max(msize, st2.st_mtime)
                ssize += st2.st_size
            except OSError:
                pass
        hit = self._summary_cache.get(rec["id"])
        if hit and hit[0] == msize:
            return hit[2]
        s = session_summary(rec)
        self._summary_cache[rec["id"]] = (msize, ssize, s)
        return s

    def graph(self, sid):
        rec = self.get(sid)
        if rec is None:
            return None
        st = os.stat(rec["path"]) if rec["path"] else None
        msize = st.st_mtime if st else 0
        ssize = st.st_size if st else 0
        hit = self._graph_cache.get(rec["id"])
        if hit and hit[0] == msize:
            return hit[2]
        s = self.summary(sid)
        g = session_graph(rec, claude_code_cost=s.get("claudeCodeCost") if s else None)
        # drop the giant raw steps payload from cache — it's what the client wants
        self._graph_cache[rec["id"]] = (msize, ssize, g)
        return g

    def tail(self, sid, after):
        rec = self.get(sid)
        if rec is None:
            return None
        st = os.stat(rec["path"]) if rec["path"] else None
        msize = st.st_mtime if st else 0
        hit = self._graph_cache.get(rec["id"])
        state = self._tails.get(rec["id"])
        if state is None or (hit and hit[0] != msize and state.offset == 0):
            # first tail call for this session: anchor at the current file end
            g = self.graph(sid)
            state = init_tail_state(rec, g)
            self._tails[rec["id"]] = state
        return tail_events(rec, state, after)


# --------------------------------------------------------------------------
# HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "MadsLens/1.0"
    store = None
    quiet = True

    def log_message(self, fmt, *args):
        if not self.quiet:
            BaseHTTPRequestHandler.log_message(self, fmt, *args)

    # -- helpers ------------------------------------------------------------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, rel):
        path = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not path.startswith(STATIC_DIR) or not os.path.isfile(path):
            self._json({"error": "not found"}, 404)
            return
        ctype = {".html": "text/html; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8"}.get(
                     os.path.splitext(path)[1], "application/octet-stream")
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # -- routes -------------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        try:
            if not parts:
                return self._static("index.html")
            if parts[0] in ("app.js", "style.css", "index.html"):
                return self._static(parts[0])
            if parts == ["health"]:
                return self._json({"ok": True, "root": self.store.root,
                                   "sessions": len(self.store.sessions)})
            if parts == ["api", "sessions"]:
                self.store.discover()
                rows = []
                for rec in self.store.sessions:
                    s = self.store.summary(rec["id"])
                    if s is None:
                        continue
                    rows.append(s)
                rows.sort(key=lambda s: (s.get("mtime") or 0, s.get("size") or 0),
                          reverse=True)
                return self._json({"root": self.store.root, "sessions": rows})
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "session":
                sid = parts[2]
                if not ID_RE.match(sid):
                    return self._json({"error": "bad id"}, 400)
                if len(parts) == 4 and parts[3] == "tail":
                    qs = parse_qs(url.query)
                    after = None
                    if "after" in qs and qs["after"][0] != "":
                        try:
                            after = int(qs["after"][0])
                        except ValueError:
                            return self._json({"error": "bad after"}, 400)
                    out = self.store.tail(sid, after)
                    if out is None:
                        return self._json({"error": "no such session"}, 404)
                    return self._json(out)
                g = self.store.graph(sid)
                if g is None:
                    return self._json({"error": "no such session"}, 404)
                return self._json(g)
            return self._json({"error": "not found"}, 404)
        except BrokenPipeError:
            pass
        except Exception:
            traceback.print_exc()
            try:
                self._json({"error": "internal error"}, 500)
            except Exception:
                pass

    def do_HEAD(self):
        self.do_GET()


def main():
    ap = argparse.ArgumentParser(description="Mads-Lens: visualize Claude Code session traces")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"),
                    help="projects directory to scan (read-only)")
    ap.add_argument("--verbose", action="store_true", help="log HTTP requests")
    args = ap.parse_args()

    root = os.path.expanduser(args.root)
    store = Store(root)
    store.discover(force=True)
    Handler.store = store
    Handler.quiet = not args.verbose
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Mads-Lens serving %d session(s) from %s" %
          (len(store.sessions), root), file=sys.stderr)
    print("http://%s:%d/  (Ctrl-C to stop)" % (args.host, args.port), file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
