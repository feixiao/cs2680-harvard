"""Mads-Stack evaluation harness: the terminal-bench agent adapter for the
Mads-Loop runtime (CS2680 A5).

============================================================================
CONTRACT — terminal-bench 0.2.18 agent interface
============================================================================
terminal-bench (PyPI ``terminal-bench``; CLI entry points ``tb`` and
``terminal-bench`` — the older ``tbench`` name was renamed, see the shim at
a5_stack/.venv/bin/tbench) runs each trial like this (harness/harness.py,
``_run_trial``):

  1. ``spin_up_terminal(...)``  — docker compose build+up of the task's
     docker-compose.yaml (image name taken from env
     ``T_BENCH_TASK_DOCKER_CLIENT_IMAGE_NAME`` = ``tb__<task_id>__client``),
     unless ``no_rebuild=True``.
  2. ``terminal.create_session("agent")`` — a ``TmuxSession`` inside the
     client container: ``tmux new-session -x 160 -y 40 -d`` (+ asciinema
     recording unless the task sets ``disable_asciinema``).
  3. ``agent = AgentFactory.get_agent(agent_name=..., import_path=...,
     **agent_kwargs)`` — for a custom agent the CLI passes
     ``--agent-import-path a5_stack.harness_stub:MadsStackAgent`` plus
     ``--agent-kwarg key=value`` pairs that land in ``__init__(**kwargs)``.
  4. ``agent.perform_task(instruction, session, logging_dir)`` — run in an
     executor thread, wrapped in ``asyncio.wait_for(timeout)``; ``session``
     is the started TmuxSession from step 2. The agent talks to the sandbox
     exclusively through the session:
       - ``session.send_keys([cmd, "Enter"], block=True, max_timeout_sec=T)``
         (blocking: appends a ``tmux wait -S done`` marker and waits)
       - ``session.get_incremental_output()`` (new pane text since last call)
       - ``session.capture_pane()`` (current screen / full scrollback)
     Returns ``terminal_bench.agents.base_agent.AgentResult`` (pydantic):
     ``total_input_tokens``, ``total_output_tokens``, ``failure_mode``
     (FailureMode enum), ``timestamped_markers`` (asciinema markers; empty
     list is fine).
  5. The harness runs the task's ``run-tests.sh`` in a fresh "tests" tmux
     session (as root), captures the pane, and a parser marks the trial
     resolved/unresolved from the test output.

============================================================================
RUNTIME — our side of the contract
============================================================================
The brain is the Mads-Loop runtime from a2_loop/madsloop (Agent + LLMClient +
ToolExecutor + sliding ContextManager, retry/backoff, loop detection) pointed
at an OpenAI-compatible endpoint. Default base_url is
http://localhost:8081/v1 — A4's mlx-lm engine; if it is not up the agent
degrades to FailureMode.UNKNOWN_AGENT_ERROR (retries then FatalLLMError),
which is the expected state until the full-stack phase. Overridable via env
MADS_BASE_URL / MADS_MODEL / MADS_API_KEY or ``--agent-kwarg``.

The Mads-Loop ToolExecutor executes tools on the HOST filesystem, which is
wrong for a sandboxed benchmark; only the ``bash`` tool is exposed and it is
rerouted through the tmux session (TerminalToolExecutor below). File tools
(read/write/edit/glob/grep) are deliberately absent — the model manipulates
files through bash. The full-stack phase may re-add them by routing through
the session as well.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

# --- madsloop lives in a2_loop (sibling dir); it is not installed as a pkg --
_A2 = Path(__file__).resolve().parent.parent / "a2_loop"
sys.path.insert(0, str(_A2))

from madsloop import Agent, AgentConfig, LLMClient, ToolExecutor  # noqa: E402
from madsloop.client import FatalLLMError  # noqa: E402
from madsloop.tools import TOOL_SCHEMAS  # noqa: E402

from terminal_bench.agents.base_agent import AgentResult, BaseAgent  # noqa: E402
from terminal_bench.agents.failure_mode import FailureMode  # noqa: E402
from terminal_bench.terminal.tmux_session import TmuxSession  # noqa: E402

REPO = Path(__file__).resolve().parent
DEFAULT_TASKS_DIR = REPO / "terminal-bench-core" / "tasks"

# Bash-only variant of the madsloop system prompt (file tools are unavailable
# inside the sandbox bridge — everything goes through bash).
TERMINAL_SYSTEM_PROMPT = """You are a coding agent working in a sandbox terminal (a Docker container) for the terminal-bench benchmark.
You have exactly one tool: bash — it runs a shell command in the sandbox and returns the terminal output.
Work step by step: inspect (ls, cat, grep), act (write files with heredocs: cat > f <<'EOF' ... EOF), verify (run tests, re-read files).
Commands run in a persistent interactive shell; your working directory persists between commands.
When the task is fully done and verified, reply with a short final answer and call no tools."""


@dataclass
class _SandboxTask:
    """madsloop's Agent expects an object with .id and .prompt."""

    id: str
    prompt: str


class TerminalToolExecutor(ToolExecutor):
    """Mads-Loop tools with ``bash`` rerouted into the sandbox's tmux session.

    The parent's other tools address the host filesystem (the task does not
    exist there) and are therefore hidden from the model and rejected if
    somehow called.
    """

    def __init__(self, workspace: str | Path, session: TmuxSession,
                 default_timeout: float = 120.0, max_timeout: float = 600.0):
        super().__init__(workspace)
        self.session = session
        self.default_timeout = default_timeout
        self.max_timeout = max_timeout
        self.schemas = [s for s in TOOL_SCHEMAS
                        if s["function"]["name"] == "bash"]
        # bash schema: widen the advertised timeout to match the sandbox bridge
        for s in self.schemas:
            s["function"]["parameters"]["properties"]["timeout"] = {
                "type": "number",
                "description": (f"seconds, default {self.default_timeout:.0f}, "
                                f"max {self.max_timeout:.0f}")},

    async def run(self, name: str, args: dict) -> str:
        if name != "bash":
            self.errors += 1
            return (f"Error: tool '{name}' is not available in this sandbox; "
                    "use bash (e.g. cat/grep/sed) instead")
        return await self._bash(args)

    async def _bash(self, args: dict) -> str:
        cmd = args.get("command", "")
        if not cmd:
            return "Error: empty command"
        timeout = min(float(args.get("timeout", self.default_timeout)),
                      self.max_timeout)

        def _round_trip() -> str:
            # Blocking: sends the command + Enter, appends the tmux wait marker,
            # and blocks until completion (or raises TimeoutError).
            self.session.send_keys([cmd, "Enter"], block=True,
                                   max_timeout_sec=timeout)
            return self.session.get_incremental_output()

        try:
            out = await asyncio.to_thread(_round_trip)
        except TimeoutError:
            self.errors += 1
            return f"Error: command timed out after {timeout:.0f}s"
        except Exception as e:
            self.errors += 1
            return f"Error: {type(e).__name__}: {e}"
        self.calls += 1
        out = out.strip()
        if len(out) > 16_000:
            out = out[:16_000] + f"\n…[truncated {len(out) - 16_000} chars]"
        return f"stdout:\n{out}" if out else "(no output)"


class MadsStackAgent(BaseAgent):
    """terminal-bench agent backed by the Mads-Loop runtime.

    Instantiate from the CLI:
      tb run -d terminal-bench-core==0.1.1 --task-id hello-world \
        --agent-import-path a5_stack.harness_stub:MadsStackAgent \
        --agent-kwarg base_url=http://localhost:8081/v1 --agent-kwarg model=...
    """

    def __init__(self,
                 base_url: str | None = None,
                 api_key: str | None = None,
                 model: str | None = None,
                 max_steps: int = 60,
                 max_ctx_tokens: int = 32768,
                 temperature: float = 0.2,
                 max_output_tokens: int = 4096,
                 request_timeout: float = 300.0,
                 bash_timeout: float = 120.0,
                 **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url or os.environ.get(
            "MADS_BASE_URL", "http://localhost:8081/v1")
        self.api_key = api_key or os.environ.get("MADS_API_KEY", "lmstudio")
        self.model = model or os.environ.get("MADS_MODEL", "qwen3.8-27b-splash")
        self.max_steps = max_steps
        self.max_ctx_tokens = max_ctx_tokens
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.request_timeout = request_timeout
        self.bash_timeout = bash_timeout

    @staticmethod
    def name() -> str:
        return "mads-stack"

    def perform_task(self,
                     instruction: str,
                     session: TmuxSession,
                     logging_dir: Path | None = None) -> AgentResult:
        t0 = time.monotonic()
        task = _SandboxTask(id="mads-stack", prompt=instruction)
        client = LLMClient(base_url=self.base_url, api_key=self.api_key,
                           model=self.model, timeout=self.request_timeout,
                           temperature=self.temperature,
                           max_output_tokens=self.max_output_tokens)
        config = AgentConfig(base_url=self.base_url, api_key=self.api_key,
                             model=self.model, max_steps=self.max_steps,
                             max_ctx_tokens=self.max_ctx_tokens,
                             temperature=self.temperature,
                             max_output_tokens=self.max_output_tokens,
                             request_timeout=self.request_timeout,
                             system_prompt=TERMINAL_SYSTEM_PROMPT)
        agent = Agent(task, client, config, workdir=str(REPO / ".sandbox-tmp"))
        agent.tools = TerminalToolExecutor(REPO / ".sandbox-tmp", session,
                                           default_timeout=self.bash_timeout)

        if logging_dir is not None:
            logging_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = asyncio.run(agent.run())
        except FatalLLMError as e:
            return AgentResult(failure_mode=FailureMode.UNKNOWN_AGENT_ERROR)
        except Exception as e:
            if logging_dir is not None:
                (logging_dir / "error.txt").write_text(
                    f"{type(e).__name__}: {e}")
            return AgentResult(failure_mode=FailureMode.UNKNOWN_AGENT_ERROR)

        if logging_dir is not None:
            (logging_dir / "madsloop_result.txt").write_text(
                f"status={result.status} seconds={result.seconds:.1f}\n"
                f"steps={len(result.steps)} tool_calls={result.tool_calls} "
                f"tool_errors={result.tool_errors} retries={result.retries}\n"
                f"input_tokens={result.usage.input_tokens} "
                f"output_tokens={result.usage.output_tokens}\n"
                f"final={result.final_answer[:2000]}\n")

        failure = (FailureMode.NONE if result.ok
                   else FailureMode.UNKNOWN_AGENT_ERROR)
        return AgentResult(
            total_input_tokens=result.usage.input_tokens,
            total_output_tokens=result.usage.output_tokens,
            failure_mode=failure,
        )


# =============================================================================
# Smoke test: sandbox connect + one command round-trip (no LLM required)
# =============================================================================

def smoke(task_id: str = "hello-world", tasks_dir: Path = DEFAULT_TASKS_DIR,
          no_rebuild: bool = True) -> bool:
    """Boots the task's compose stack (or a prebuilt image) and round-trips
    one command through the tmux session. ~5-15 s, no LLM involved."""
    from terminal_bench.terminal.terminal import spin_up_terminal

    task_dir = Path(tasks_dir) / task_id
    compose = task_dir / "docker-compose.yaml"
    if not compose.exists():
        print(f"smoke: no docker-compose.yaml for {task_id} at {task_dir}")
        return False

    # Image/container names must match what trial_handler computes at run time.
    prefix = f"tb__{task_id}".replace(".", "-")
    client_image = f"{prefix}__client"
    client_container = "mads-smoke"

    # Log dirs (mirrors what the harness passes); compose volume mounts need
    # the corresponding env vars to be non-empty.
    logs_dir = REPO / ".smoke-logs"
    for sub in ("sessions", "agent-logs"):
        (logs_dir / sub).mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    try:
        with spin_up_terminal(
            client_container_name=client_container,
            client_image_name=client_image,
            docker_compose_path=compose,
            docker_image_name_prefix=prefix,
            sessions_logs_path=logs_dir / "sessions",
            agent_logs_path=logs_dir / "agent-logs",
            commands_path=logs_dir / "commands.txt",
            no_rebuild=no_rebuild,
            cleanup=False,  # keep the prebuilt image for the full-stack phase
            disable_recording=True,
        ) as terminal:
            session = terminal.create_session("agent", as_configured_user=True)
            # Prime the incremental-output baseline.
            first = session.get_incremental_output()
            print(f"smoke: session up; initial screen:\n{first.strip()[:200]}")

            cmd = "echo MADS_SMOKE_OK_$((6*7))_$(uname -s)"
            session.send_keys([cmd, "Enter"], block=True, max_timeout_sec=30)
            out = session.get_incremental_output()
            print("smoke: round-trip output:\n" + out.strip())

            ok = "MADS_SMOKE_OK_42" in out
            print(f"smoke: {'PASS' if ok else 'FAIL'} "
                  f"({time.monotonic() - t0:.1f}s total)")
            return ok
        # the with-block tears the stack down (terminal.stop -> compose down)
    except Exception as e:
        print(f"smoke: FAIL ({time.monotonic() - t0:.1f}s): "
              f"{type(e).__name__}: {e}")
        return False
    finally:
        # Belt and braces: kill the container if teardown was skipped.
        import docker
        try:
            docker.from_env().containers.get(client_container).kill()
        except Exception:
            pass


def main(argv: list[str]) -> int:
    args = argv[1:]
    task_id = "hello-world"
    no_rebuild = True
    it = iter(args)
    for a in it:
        if a == "--task":
            task_id = next(it)
        elif a == "--rebuild":
            no_rebuild = False
    if not args or args[0] in ("smoke", "--smoke"):
        return 0 if smoke(task_id, no_rebuild=no_rebuild) else 1
    print(__doc__.split("CONTRACT")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
