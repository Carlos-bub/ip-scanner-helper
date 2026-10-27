"""Immutable timeout policy and monotonic, cooperative operation deadlines."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
import time

from ip_scanner_helper.domain.scan_policy import DEFAULT_TIMEOUTS, ScanTimeouts
from ip_scanner_helper.application.errors import ProbeTimeout, ScanCancelled, TargetBudgetExceeded


@dataclass(frozen=True)
class ProbeContext:
    target_deadline: float
    deadline: float
    cancelled: Event
    clock: Callable[[], float] = time.monotonic

    @classmethod
    def standalone(cls, seconds, cancelled=None, *, clock=time.monotonic):
        return cls(float("inf"), clock() + seconds, cancelled if cancelled is not None else Event(), clock)

    @classmethod
    def target(cls, seconds, cancelled, *, clock=time.monotonic):
        end = clock() + seconds
        return cls(end, end, cancelled, clock)

    def child(self, seconds):
        return ProbeContext(self.target_deadline, min(self.deadline, self.clock() + seconds), self.cancelled, self.clock)

    def remaining(self):
        if self.cancelled.is_set():
            raise ScanCancelled()
        now = self.clock()
        if now >= self.target_deadline:
            raise TargetBudgetExceeded()
        if now >= self.deadline:
            raise ProbeTimeout()
        return min(self.target_deadline, self.deadline) - now

    def check(self):
        self.remaining()

    def timeout(self, maximum):
        return min(maximum, self.remaining())


def operation_context(timeout, context=None, *, factor=1, cancelled=None):
    seconds = timeout * factor + .05
    return context.child(seconds) if context is not None else ProbeContext.standalone(seconds, cancelled)
