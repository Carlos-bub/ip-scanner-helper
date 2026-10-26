"""Immutable timeout policy and monotonic, cooperative operation deadlines."""

from collections.abc import Callable
from dataclasses import dataclass, fields
import math
from threading import Event
import time

from ip_scanner_helper.application.errors import ProbeTimeout, ScanCancelled, TargetBudgetExceeded


@dataclass(frozen=True)
class ScanTimeouts:
    target_s: float = 20.0
    icmp: float = .5
    tcp: float = .2
    tcp_batch: float = 2.0
    snmp: float = .35
    dns_ptr: float = 2.5
    netbios: float = .4
    pjl: float = .35
    onvif: float = .5
    http: float = .6
    sip: float = .35
    rdp: float = .8
    ssh: float = .35
    ftp: float = .35
    tls: float = .6
    ssdp: float = .35

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if (isinstance(value, bool) or not isinstance(value, (float, int))
                    or not math.isfinite(value) or not 0 < value <= 300):
                raise ValueError("Os limites de tempo devem ser números maiores que 0 e até 300 segundos.")

    def budget(self, probe, ports=()):
        """Allow existing retries/I/O steps, but bound each composite operation."""
        if probe == "arp":
            return self.target_s  # SendARP has no timeout/cancellation argument.
        if probe == "tcp":
            return self.tcp_batch
        if probe == "icmp":
            return self.icmp + 1.0  # Includes process startup only if fallback is needed.
        factor = {"snmp": 4, "rdp": 4, "pjl": 3, "ssh": 2, "ftp": 2,
                  "http": max(1, len(ports)) * 2, "tls": max(1, len(ports)) * 2}.get(probe, 1)
        return getattr(self, probe) * factor + .05


DEFAULT_TIMEOUTS = ScanTimeouts()


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
