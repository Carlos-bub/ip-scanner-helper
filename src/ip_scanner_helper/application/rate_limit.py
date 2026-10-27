"""Session-wide collector admission with bounded, cancellable waiting."""

from threading import Lock
import time

from ip_scanner_helper.domain.scan_policy import validate_probe_rate


class ProbeRateLimiter:
    """Space admissions evenly, without accumulating idle credits or reservations.

    This limits collector invocations, not packets, TCP ports within a batch,
    protocol retries, or operations outside the inventory scan.
    """

    def __init__(self, starts_per_second=0, *, clock=time.monotonic, waiter=None):
        self.limit = validate_probe_rate(starts_per_second)
        self._interval = 1 / self.limit if self.limit else 0
        self._clock = clock
        self._waiter = waiter or (lambda event, seconds: event.wait(seconds))
        self._lock = Lock()
        self._next_start = None
        self._started = 0

    def acquire(self, context):
        while True:
            context.check()
            with self._lock:
                context.check()
                now = self._clock()
                if not self.limit or self._next_start is None or now >= self._next_start:
                    self._next_start = now + self._interval
                    self._started += 1
                    return
                delay = min(self._next_start - now, .05, context.remaining())
            # No lock is held during the wait. Cancellation wakes it immediately;
            # periodic checks also respect the original target deadline.
            self._waiter(context.cancelled, delay)

    def snapshot(self):
        with self._lock:
            return {"limit_per_second": self.limit, "scope": "collector_starts", "started": self._started}
