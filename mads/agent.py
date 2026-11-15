"""Workload driver: runs all tasks through engine + agents on a shared clock.

``concurrency`` is how many tasks advance at once; each task issues at most
one model request at a time, and all in-flight requests from a round are
batched by the engine (prefill FIFO, then continuous-batching decode). The
round barrier is a max, not a sum: retry backoffs and tool I/O of
different agents overlap on the shared clock (independent I/O), so a round
costs the slowest agent's wait, not the sum of everyone's.
"""

from .agent_loop import Agent, AgentConfig, DONE, FAILED
from .lens import Lens
from .scheduler import ServingEngine
from .simclock import SimClock


def run_workload(tasks, config=None):
    config = config if config is not None else AgentConfig()
    clock = SimClock()
    lens = Lens(len(tasks))
    engine = ServingEngine(
        clock=clock,
        prefix_reuse=config.prefix_reuse,
        speculative=config.speculative,
        error_rate=config.error_rate,
        resident=config.resident,
        tp_size=config.tp_size,
    )
    agents = [Agent(t, i, engine, config, lens, clock) for i, t in enumerate(tasks)]
    active = []
    for _ in range(1_000_000):
        if all(a.state in (DONE, FAILED) for a in agents):
            break
        while len(active) < config.concurrency:
            nxt = next((a for a in agents if a.state == "INIT"), None)
            if nxt is None:
                break
            active.append(nxt)
            nxt.submit()
        pending = [a for a in active if a.state == "AWAIT_MODEL"]
        if pending:
            engine.run_batch([a.request for a in pending])
            for a in pending:
                a.receive()
            # Retry backoffs of different agents overlap.
            w = max((a.wait for a in pending), default=0.0)
            if w:
                clock.advance(w)
            for a in pending:
                a.finish_wait()
        running = [a for a in active if a.state == "RUN_TOOLS"]
        if running:
            # Tool I/O of different agents overlaps: the shared clock
            # advances once by the round maximum, then all agents
            # record their results.
            barrier = max(a.tool_dt() for a in running)
            if barrier:
                clock.advance(barrier)
            for a in running:
                a.run_tools()
        active = [a for a in active if a.state not in (DONE, FAILED)]
    else:
        raise RuntimeError("run_workload did not terminate")
    return lens.summary(engine.kv, clock.now), lens
