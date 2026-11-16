"""The local task set: 12 deterministic coding tasks, each self-checking.

A task materializes starter files into a fresh workspace and verifies the
outcome by running tests / inspecting outputs. This plays the role the course
leaderboard's 26 containerized tasks play (we don't have api.cs2680.com access
from here; the checks are written to the same spirit: verify observable
behavior, not internal state).
"""

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Task:
    id: str
    prompt: str
    setup: callable = None
    check: callable = None
    tags: list = field(default_factory=list)


def _write(ws: Path, name: str, content: str) -> None:
    p = ws / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


# --------------------------------------------------------------- tasks

def t01():
    def setup(ws):
        _write(ws, "numbers.txt", "\n".join([str(n) for n in range(1, 101)]))
    def check(ws):
        out = ws / "answer.txt"
        if not out.exists():
            return False, "answer.txt missing"
        return (out.read_text().strip() == "5050"), f"answer.txt={out.read_text().strip()!r}, want 5050"
    return Task("t01_sum_file",
                "The file numbers.txt contains one integer per line. Compute their "
                "sum and write it (just the number) to answer.txt. Verify your work.",
                setup, check, ["file", "bash"])

def t02():
    def setup(ws):
        _write(ws, "count.py",
               "import sys\nn = int(sys.argv[1])\nprint(sum(range(1, n)))\n")
        _write(ws, "test_count.py",
               "import subprocess, sys\nr = subprocess.run([sys.executable, 'count.py', '10'],\n"
               "    capture_output=True, text=True)\nexpected = '55'\n"
               "assert r.stdout.strip() == expected, f'got {r.stdout.strip()!r}'\nprint('PASS')\n")
    def check(ws):
        import subprocess, sys
        r = subprocess.run([sys.executable, "test_count.py"], cwd=ws,
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0, f"test output: {r.stdout.strip()} {r.stderr.strip()[:120]}"
    return Task("t02_off_by_one",
                "count.py is buggy: `python3 count.py 10` prints 45 but should print 55 "
                "(sum of 1..10). Fix count.py (not the test) so that "
                "`python3 test_count.py` prints PASS.",
                setup, check, ["debug", "edit"])

def t03():
    def setup(ws):
        _write(ws, "people.csv",
               "name,age,city\nAlice,30,NYC\nBob,25,Boston\nCarol,41,Chicago\n")
    def check(ws):
        out = ws / "people.json"
        if not out.exists():
            return False, "people.json missing"
        data = json.loads(out.read_text())
        ok = (isinstance(data, list) and len(data) == 3
              and data[0]["name"] == "Alice" and data[0]["age"] == 30
              and all(isinstance(p["age"], int) for p in data))
        return ok, f"people.json invalid: {str(data)[:120]}"
    return Task("t03_csv_to_json",
                "Convert people.csv to people.json: a JSON array of objects where 'age' "
                "is a number (not string) and other fields stay strings. Use bash "
                "(python3) if you like; verify the result parses.",
                setup, check, ["data", "bash"])

def t04():
    def setup(ws):
        _write(ws, "lines.txt", "banana\napple\ncherry\napple\ncherry\nbanana\ndate\n")
    def check(ws):
        out = ws / "clean.txt"
        if not out.exists():
            return False, "clean.txt missing"
        got = out.read_text().splitlines()
        want = ["apple", "banana", "cherry", "date"]
        return got == want, f"clean.txt={got}"
    return Task("t04_dedup_sort",
                "lines.txt has duplicate lines. Write the deduplicated, lexicographically "
                "sorted lines to clean.txt (one per line, no extras).",
                setup, check, ["file", "bash"])

def t05():
    def setup(ws):
        _write(ws, "test_fizzbuzz.py",
               "import subprocess, sys\nr = subprocess.run([sys.executable, 'fizzbuzz.py'],\n"
               "    capture_output=True, text=True)\nlines = r.stdout.splitlines()\n"
               "assert len(lines) == 100, f'{len(lines)} lines'\n"
               "assert lines[2] == 'Fizz' and lines[4] == 'Buzz' and lines[9] == 'Buzz'\n"
               "assert lines[14] == 'FizzBuzz' and lines[19] == 'Buzz' and lines[29] == 'FizzBuzz'\n"
               "assert lines[99] == 'Buzz'\nprint('PASS')\n")
    def check(ws):
        import subprocess, sys
        r = subprocess.run([sys.executable, "test_fizzbuzz.py"], cwd=ws,
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0, f"test: {r.stdout.strip()} {r.stderr.strip()[:150]}"
    return Task("t05_fizzbuzz",
                "Create fizzbuzz.py: prints the numbers 1..100, one per line, replacing "
                "multiples of 3 with 'Fizz', of 5 with 'Buzz', of 15 with 'FizzBuzz'. "
                "Then run `python3 test_fizzbuzz.py` until it prints PASS.",
                setup, check, ["write", "bash"])

def t06():
    def setup(ws):
        log = "\n".join([
            "2024-01-01 ERROR db timeout", "2024-01-01 INFO start",
            "2024-01-01 ERROR api 500", "2024-01-02 INFO ok",
            "2024-01-02 ERROR db timeout", "2024-01-03 WARN slow",
            "2024-01-03 ERROR disk full", "2024-01-03 ERROR api 500",
        ])
        _write(ws, "errors.log", log + "\n")
    def check(ws):
        out = ws / "counts.json"
        if not out.exists():
            return False, "counts.json missing"
        data = json.loads(out.read_text())
        want = {"2024-01-01": 2, "2024-01-02": 1, "2024-01-03": 2}
        return data == want, f"counts.json={data}"
    return Task("t06_log_parse",
                "errors.log has lines like 'YYYY-MM-DD LEVEL message'. Count how many "
                "ERROR-level lines each date has and write counts.json mapping date -> "
                "count (only dates that have errors).",
                setup, check, ["data", "bash"])

def t07():
    def setup(ws):
        _write(ws, "vals.txt", "10\nabc\n20\n\n30\nxx\n40\n")
        _write(ws, "sumvals.py",
               "total = 0\nfor line in open('vals.txt'):\n    total += int(line)\n"
               "print(total)\n")
    def check(ws):
        import subprocess, sys
        r = subprocess.run([sys.executable, "sumvals.py"], cwd=ws,
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0 and r.stdout.strip() == "100", \
            f"rc={r.returncode} out={r.stdout.strip()!r} err={r.stderr.strip()[:100]}"
    return Task("t07_add_error_handling",
                "sumvals.py crashes because vals.txt contains some non-numeric lines. "
                "Modify sumvals.py to skip invalid lines (keep the valid ones) so that "
                "`python3 sumvals.py` prints 100 and exits 0.",
                setup, check, ["debug", "edit"])

def t08():
    def setup(ws):
        events = [
            {"user": "a", "amount": 5}, {"user": "b", "amount": 10},
            {"user": "a", "amount": 3}, {"user": "c", "amount": 7},
            {"user": "b", "amount": 2},
        ]
        _write(ws, "events.jsonl", "\n".join(json.dumps(e) for e in events))
    def check(ws):
        out = ws / "totals.json"
        if not out.exists():
            return False, "totals.json missing"
        data = json.loads(out.read_text())
        return data == {"a": 8, "b": 12, "c": 7}, f"totals.json={data}"
    return Task("t08_jsonl_agg",
                "events.jsonl is one JSON object per line with fields user and amount. "
                "Compute the total amount per user and write totals.json (user -> total).",
                setup, check, ["data", "bash"])

def t09():
    def setup(ws):
        _write(ws, "config.txt",
               "host: localhost\nport: 8080\ndebug: true\nname: myapp\n")
    def check(ws):
        out = ws / "config.json"
        if not out.exists():
            return False, "config.json missing"
        data = json.loads(out.read_text())
        return data == {"host": "localhost", "port": 8080,
                        "debug": True, "name": "myapp"}, f"config.json={data}"
    return Task("t09_extract_config",
                "config.txt has 'key: value' lines. Convert it to config.json with proper "
                "JSON types: port as number, debug as boolean, strings quoted. "
                "(true/false -> JSON booleans, integers -> numbers.)",
                setup, check, ["data", "bash"])

def t10():
    def setup(ws):
        words = ("the dog quick brown fox jumps over lazy cat "
                 "elephant programmer keyboard").split()
        _write(ws, "words.txt", " ".join(words))
    def check(ws):
        out = ws / "buckets.json"
        if not out.exists():
            return False, "buckets.json missing"
        data = json.loads(out.read_text())
        want = {"short": 0, "medium": 0, "long": 0}
        for w in ("the dog quick brown fox jumps over lazy cat elephant programmer keyboard".split()):
            n = len(w)
            want["short" if n <= 4 else "medium" if n <= 8 else "long"] += 1
        return data == want, f"buckets.json={data} want={want}"
    return Task("t10_word_buckets",
                "words.txt contains space-separated words. Bucket them by length: "
                "'short' (1-4 chars), 'medium' (5-8), 'long' (9+). Write buckets.json "
                "mapping bucket name -> count.",
                setup, check, ["data", "bash"])

def t11():
    def setup(ws):
        _write(ws, "app.py", "print('app')\n")
        _write(ws, "util.py", "print('util')\n")
        _write(ws, "notes.md", "# notes\n")
        _write(ws, "README.md", "# readme\n")
        _write(ws, "data.csv", "a,b\n1,2\n")
        _write(ws, "train.py", "print('train')\n")
    def check(ws):
        want = {"src/app.py", "src/util.py", "src/train.py",
                "docs/notes.md", "docs/README.md", "data/data.csv"}
        got = {str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file()}
        return got == want, f"files={sorted(got)}"
    return Task("t11_organize",
                "The workspace is a flat mess. Reorganize into: src/ for .py files, "
                "docs/ for .md files, data/ for .csv files. Move (don't copy) each file "
                "to the right place; nothing should remain in the top level.",
                setup, check, ["file", "bash"])

def t12():
    def setup(ws):
        _write(ws, "pipeline.py",
               "def run():\n"
               "    lines = open('in.txt').read().splitlines()\n"
               "    out = []\n"
               "    for line in lines:\n"
               "        parts = line.split(',')\n"
               "        name, num = parts[0], int(parts[1])\n"
               "        out.append(name.upper() + ':' + str(num * 2))\n"
               "    open('out.txt', 'w').write('\\n'.join(out))\n"
               "\n"
               "run()\n")
        _write(ws, "in.txt", "alpha,1\nbeta,2\ngamma,3\n")
    def check(ws):
        import subprocess, sys
        r = subprocess.run([sys.executable, "pipeline.py"], cwd=ws,
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return False, f"pipeline broke: {r.stderr.strip()[:150]}"
        got = (ws / "out.txt").read_text().splitlines()
        want = ["ALPHA:2", "BETA:4", "GAMMA:6"]
        src = (ws / "pipeline.py").read_text()
        has_fns = all(k in src for k in ("def load", "def transform", "def save"))
        return got == want and has_fns, f"out={got}, extracted_fns={has_fns}"
    return Task("t12_refactor",
                "pipeline.py works but is one blob. Refactor it into three functions — "
                "load(), transform(lines), save(lines) — with the same observable "
                "behavior: `python3 pipeline.py` must still produce the same out.txt. "
                "Verify by running it before and after.",
                setup, check, ["refactor", "edit"])


TASKS = [t() for t in (t01, t02, t03, t04, t05, t06, t07, t08, t09, t10, t11, t12)]


def make_workspaces(root: str, task_ids=None) -> dict:
    """Fresh sandbox workspace per task; returns {task_id: workspace_path}."""
    root = Path(root)
    out = {}
    for t in TASKS:
        if task_ids and t.id not in task_ids:
            continue
        ws = root / t.id
        if ws.exists():
            shutil.rmtree(ws)
        ws.mkdir(parents=True)
        if t.setup:
            t.setup(ws)
        out[t.id] = ws
    return out
