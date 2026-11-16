"""Sandboxed coding-agent tools.

Every path is resolved inside the workspace; escapes (.., absolute paths
outside) are refused. Tool-level failures are returned as result TEXT (the
model must be able to see and recover from them) — only harness-level bugs
raise.
"""

import asyncio
import glob as _glob
import os
import re
from pathlib import Path

MAX_OUTPUT = 16_000          # per-tool result truncation
BASH_TIMEOUT = 60.0
GREP_MAX_MATCHES = 100
GLOB_MAX_RESULTS = 200

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "bash",
        "description": "Run a shell command in the workspace directory. "
                       "Use for running scripts, tests, git-free file operations.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "the command to run"},
            "timeout": {"type": "number", "description": "seconds, default 60, max 300"}},
            "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "read",
        "description": "Read a text file from the workspace. 1-based line ranges.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write",
        "description": "Write (create or overwrite) a text file in the workspace.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "edit",
        "description": "Replace an exact string in a file. Fails if old_string is "
                       "not found (or not unique when replace_all is false).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"}},
            "required": ["path", "old_string", "new_string"]}}},
    {"type": "function", "function": {
        "name": "glob",
        "description": "List files matching a glob pattern (e.g. '**/*.py').",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "grep",
        "description": "Regex search over workspace files (or one file).",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "file or dir, default workspace"}},
            "required": ["pattern"]}}},
]


def _truncate(s: str) -> str:
    if len(s) <= MAX_OUTPUT:
        return s
    return s[:MAX_OUTPUT] + f"\n…[truncated {len(s) - MAX_OUTPUT} chars]"


class ToolExecutor:
    def __init__(self, workspace: str | Path, env_extra: dict | None = None):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.env_extra = env_extra or {}
        self.schemas = TOOL_SCHEMAS
        self.calls = 0
        self.errors = 0

    # ------------------------------------------------------------- sandbox

    def _resolve(self, p: str) -> Path:
        q = (self.workspace / p).resolve()
        if q != self.workspace and self.workspace not in q.parents:
            raise PermissionError(f"path escapes workspace: {p}")
        return q

    async def run(self, name: str, args: dict) -> str:
        self.calls += 1
        try:
            if name == "bash":
                return await self._bash(args)
            fn = {
                "read": self._read, "write": self._write,
                "edit": self._edit, "glob": self._glob, "grep": self._grep,
            }.get(name)
            if fn is None:
                self.errors += 1
                return f"Error: unknown tool '{name}'"
            out = fn(args)
            if asyncio.iscoroutine(out):
                out = await out
            return out
        except PermissionError as e:
            self.errors += 1
            return f"Error: {e}"
        except Exception as e:  # harness-internal failure → surface to model
            self.errors += 1
            return f"Error: {type(e).__name__}: {e}"

    # ------------------------------------------------------------- tools

    async def _bash(self, args: dict) -> str:
        cmd = args.get("command", "")
        if not cmd:
            return "Error: empty command"
        timeout = min(float(args.get("timeout", 60)), 300)
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.update(self.env_extra)
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, cwd=str(self.workspace), env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return f"Error: command timed out after {timeout:.0f}s"
        out = out.decode(errors="replace")
        err = err.decode(errors="replace")
        parts = [f"exit code: {proc.returncode}"]
        if out:
            parts.append(f"stdout:\n{out}" if len(out) < 8000 else _truncate(out))
        if err:
            parts.append(f"stderr:\n{_truncate(err)}")
        return "\n".join(parts) if len(parts) > 1 or out or err else "exit code: 0 (no output)"

    def _read(self, args: dict) -> str:
        q = self._resolve(args.get("path", ""))
        if not q.is_file():
            return f"Error: no such file: {args.get('path')}"
        lines = q.read_text(errors="replace").splitlines(keepends=True)
        s = int(args.get("start_line", 1))
        e = int(args.get("end_line", len(lines)))
        sel = lines[max(s - 1, 0):e]
        body = "".join(sel)
        if len(body) > MAX_OUTPUT:
            body = _truncate(body)
        hdr = f"[{q.name} lines {max(s, 1)}-{min(e, len(lines))} of {len(lines)}]\n"
        return hdr + body

    def _write(self, args: dict) -> str:
        q = self._resolve(args.get("path", ""))
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text(args.get("content", ""))
        return f"wrote {len(args.get('content', ''))} bytes to {q}"

    def _edit(self, args: dict) -> str:
        q = self._resolve(args.get("path", ""))
        if not q.is_file():
            return f"Error: no such file: {args.get('path')}"
        text = q.read_text(errors="replace")
        old, new = args.get("old_string", ""), args.get("new_string", "")
        if not old:
            return "Error: empty old_string"
        n = text.count(old)
        if n == 0:
            return "Error: old_string not found in file"
        if n > 1 and not args.get("replace_all"):
            return f"Error: old_string is not unique ({n} occurrences); " \
                   "add context or use replace_all"
        text = text.replace(old, new) if args.get("replace_all") else text.replace(old, new, 1)
        q.write_text(text)
        return f"edited {q.name} ({n if args.get('replace_all') else 1} replacement(s))"

    def _glob(self, args: dict) -> str:
        pat = args.get("pattern", "")
        matches = []
        for p in sorted(self.workspace.rglob("*")):
            rel = str(p.relative_to(self.workspace))
            if _glob.has_magic(pat) and _glob_match(rel, pat):
                matches.append(rel)
            elif not _glob.has_magic(pat) and rel == pat:
                matches.append(rel)
            if len(matches) >= GLOB_MAX_RESULTS:
                matches.append(f"…(more than {GLOB_MAX_RESULTS} matches)")
                break
        return "\n".join(matches) if matches else "no matches"

    def _grep(self, args: dict) -> str:
        pat = args.get("pattern", "")
        target = self._resolve(args.get("path", "")) if args.get("path") else self.workspace
        try:
            rx = re.compile(pat)
        except re.error as e:
            return f"Error: bad regex: {e}"
        files = [target] if target.is_file() else sorted(target.rglob("*"))
        hits, checked = [], 0
        for f in files:
            if not f.is_file() or f.stat().st_size > 2_000_000:
                continue
            checked += 1
            rel = str(f.relative_to(self.workspace))
            try:
                for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{rel}:{i}: {line[:200]}")
                        if len(hits) >= GREP_MAX_MATCHES:
                            break
            except Exception:
                continue
            if len(hits) >= GREP_MAX_MATCHES:
                break
        if not hits:
            return f"no matches (checked {checked} files)"
        tail = f"\n…({len(hits)} matches, capped at {GREP_MAX_MATCHES})" if len(hits) >= GREP_MAX_MATCHES else ""
        return "\n".join(hits) + tail


def _glob_match(rel: str, pat: str) -> bool:
    # pathlib-style ** semantics on a relative path
    rx = re.escape(pat).replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
    return re.fullmatch(rx, rel) is not None
