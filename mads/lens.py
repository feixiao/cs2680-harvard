"""Per-task accounting: token, cost, latency, retry, and KV high-water stats.

Mirrors Mads-Lens: the dashboard view over the agent's trajectory.
"""


class TaskStats:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.prompt_tokens = 0
        self.cached_tokens = 0
        self.completion_tokens = 0
        self.cost_usd = 0.0
        self.latency_s = 0.0
        self.retries = 0
        self.status = "RUNNING"


class Lens:
    def __init__(self, n_tasks: int):
        self.tasks = [TaskStats("t%02d" % i) for i in range(n_tasks)]

    def record_request(self, task_idx: int, req) -> None:
        s = self.tasks[task_idx]
        if req.failed:
            s.retries += 1
            return
        s.prompt_tokens += req.billable
        s.cached_tokens += req.cached
        s.completion_tokens += len(req.out_tokens or [])
        s.cost_usd += req.cost
        s.latency_s += req.dt

    def set_status(self, task_idx: int, status: str) -> None:
        self.tasks[task_idx].status = status

    def summary(self, kv, makespan_s: float):
        completed = sum(1 for s in self.tasks if s.status == "DONE")
        prompt = sum(s.prompt_tokens for s in self.tasks)
        cached = sum(s.cached_tokens for s in self.tasks)
        completion = sum(s.completion_tokens for s in self.tasks)
        total = prompt + cached + completion
        cost = sum(s.cost_usd for s in self.tasks)
        retries = sum(s.retries for s in self.tasks)
        hit_rate = (cached / (cached + prompt)) if (cached + prompt) else 0.0
        return {
            "e2e_latency_s": makespan_s,
            "total_cost_usd": cost,
            "total_tokens": total,
            "prompt_tokens": prompt + cached,
            "completion_tokens": completion,
            "cache_hit_rate": hit_rate,
            "tasks_completed": completed,
            "n_tasks": len(self.tasks),
            "retries": retries,
            "peak_kv_mb": kv.peak / (1 << 20),
        }
