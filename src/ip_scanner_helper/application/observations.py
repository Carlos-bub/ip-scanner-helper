"""Probe outcomes and aggregate timings; no credentials or response payloads."""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
import time

from ip_scanner_helper.application.errors import ProbeTimeout, ScanCancelled, TargetBudgetExceeded

PROBES = ("arp", "icmp", "tcp", "snmp", "dns_ptr", "netbios", "pjl", "onvif",
          "http", "sip", "rdp", "ssh", "ftp", "tls", "ssdp")
OUTCOMES = ("result", "no_result", "error", "cancelled", "timeout", "budget_exhausted", "not_run")


@dataclass(frozen=True)
class ProbeObservation:
    probe: str
    outcome: str
    started_at: str | None
    duration_s: float


def _responded(name, value):
    if name == "arp":
        return bool(value[1])
    if name in ("icmp", "http", "tls"):
        return bool(value[0])
    if name == "snmp":
        return any(value[:2])
    return bool(value)


class ProbeRecorder:
    def __init__(self, cancelled, observer=None):
        self.cancelled, self.observer = cancelled, observer
        self.attempted = set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.observer:
            for name in PROBES:
                if name not in self.attempted:
                    self.observer(ProbeObservation(name, "not_run", None, 0.0))

    def call(self, name, function, *args, **kwargs):
        if self.observer is None:
            if self.cancelled.is_set():
                raise ScanCancelled()
            value = function(*args, **kwargs)
            if self.cancelled.is_set():
                raise ScanCancelled()
            return value
        self.attempted.add(name)
        started = time.monotonic()
        stamp = datetime.now(timezone.utc).isoformat() if self.observer else None
        outcome = "error"
        try:
            if self.cancelled.is_set():
                raise ScanCancelled()
            value = function(*args, **kwargs)
            if self.cancelled.is_set():
                raise ScanCancelled()
            # Legacy collectors collapse timeout, refusal and some handled
            # failures into None/empty values. Do not invent a packet outcome.
            outcome = "result" if _responded(name, value) else "no_result"
            return value
        except ScanCancelled:
            outcome = "cancelled"
            raise
        except TargetBudgetExceeded:
            outcome = "budget_exhausted"
            raise
        except ProbeTimeout:
            outcome = "timeout"
            raise
        finally:
            if self.observer:
                self.observer(ProbeObservation(name, outcome, stamp, time.monotonic() - started))


class ScanMetrics:
    def __init__(self):
        self.started = time.monotonic()
        self.cpu_started = time.process_time()
        self.first_result_s = None
        self._lock = Lock()
        self._probes = {}

    def observe(self, observation):
        with self._lock:
            item = self._probes.setdefault(observation.probe,
                                          {**dict.fromkeys(OUTCOMES, 0), "duration_s": 0.0})
            item[observation.outcome] += 1
            item["duration_s"] += observation.duration_s

    def found(self):
        with self._lock:
            if self.first_result_s is None:
                self.first_result_s = time.monotonic() - self.started

    def snapshot(self, cancel_requested_at=None):
        with self._lock:
            now = time.monotonic()
            return {"duration_s": now - self.started,
                    "cpu_process_s": time.process_time() - self.cpu_started,
                    "first_result_s": self.first_result_s,
                    "cancel_to_finish_s": now - cancel_requested_at if cancel_requested_at is not None else None,
                    "probes": {key: dict(value) for key, value in self._probes.items()}}
