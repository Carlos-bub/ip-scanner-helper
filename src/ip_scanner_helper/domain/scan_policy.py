"""Immutable collection time policy, independent of adapters and UI."""

from dataclasses import dataclass, fields
import math


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


PROBE_TIMEOUT_DEFAULTS = tuple((field.name, getattr(DEFAULT_TIMEOUTS, field.name))
                               for field in fields(ScanTimeouts) if field.name != "target_s")
