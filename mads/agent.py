"""Workload driver: an event-driven agent runtime on a shared clock.

Each admitted agent owns at most one in-flight model request. When a request
completes, the agent decides immediately (record the result, bookkeep tools,
or schedule a retry after backoff) and its follow-up request becomes ready
after that delay — tool I/O and backoffs run concurrently with other
agents' GPU work on the same clock, not as a round barrier. The engine
continuously batches all ready requests (prefill FIFO, continuous-batching
decode, week-14 request scheduling). ``concurrency`` caps how many tasks
advance in parallel.
"""

from .agent_loop import Agent, AgentConfig, AWAIT_MODEL, DONE, FAILED, INIT
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
    in_flight = [0]
    pending = []
    seq = [0]
    burst = [0]  # admissions paced within the current same-time burst
    burst_t = [None]

    def admit_next():
        """Admit waiting tasks while slots are free (up to ``concurrency``).

        Tasks arriving at the same instant form a burst; with
        ``admission_stagger`` > 0 the burst is paced ``delta`` apart in
        arrival order. Phase-locked cohorts (identical start, similar
        step lengths) otherwise queue behind each other's serial prefills
        and keep each other's decode batches window-mixed; pacing breaks
        the lockstep so the GPU stays packed with disjoint phases."""
        delta = config.admission_stagger
        while in_flight[0] < config.concurrency:
            nxt = next((a for a in agents if a.state == INIT), None)
            if nxt is None:
                break
            if (
                delta <= 0.0
                or burst_t[0] is None
                or clock.now - burst_t[0] > 2.0 * delta
            ):
                burst[0] = 0
                burst_t[0] = clock.now
            in_flight[0] += 1
            seq[0] += 1
            nxt.submit()
            pending.append((clock.now + delta * burst[0], seq[0], nxt))
            burst[0] += 1

    def on_complete(r):
        a = r.agent
        a.receive()
        if a.state in (DONE, FAILED):
            in_flight[0] -= 1
            admit_next()
            return []
        if a.state == AWAIT_MODEL:
            # Transient failure: retry the same step after the backoff.
            seq[0] += 1
            return [(a.wait, a, seq[0])]
        td = a.tool_dt()  # tool I/O runs concurrently with GPU work
        a.run_tools()
        if a.state == AWAIT_MODEL:
            seq[0] += 1
            return [(td, a, seq[0])]
        in_flight[0] -= 1
        admit_next()
        return []

    admit_next()
    engine.run_events(pending, on_complete)
    return lens.summary(engine.kv, clock.now), lens
