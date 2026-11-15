"""Deterministic simulated clock (seconds). No wall time, ever."""


class SimClock:
    def __init__(self):
        self.t = 0.0

    def advance(self, seconds: float) -> None:
        self.t += seconds

    @property
    def now(self) -> float:
        return self.t
