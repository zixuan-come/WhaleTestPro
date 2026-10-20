"""Deterministic monotonic clock for synthetic Locust control tests."""
class Clock:
    def __init__(self):
        self.seconds = 0.0

    def advance(self, seconds):
        self.seconds += seconds


def install_clock(monkeypatch, perf):
    clock = Clock()
    monkeypatch.setattr(perf, 'monotonic', lambda: clock.seconds)
    monkeypatch.setattr(perf.time, 'sleep', clock.advance)
    return clock
