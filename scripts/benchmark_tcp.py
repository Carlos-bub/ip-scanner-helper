"""Reproducible TCP-only benchmark. All sockets/selectors are simulated.

No address is contacted. The serial reference preserves the pre-optimization
13-port algorithm. Timings measure this fixture, not real /24 scan duration.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import errno
import json
from pathlib import Path
from threading import Event, Lock
import sys
import time
import tracemalloc
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.tcp_probe import DEFAULT_TCP_PORTS, SocketBudget, scan_tcp_ports


class FixtureNetwork:
    def __init__(self, scenario, timeout):
        self.scenario, self.timeout = scenario, timeout
        self.lock = Lock()
        self.active = self.peak = self.started = 0

    def socket(self, *args):
        with self.lock:
            self.active += 1
            self.started += 1
            self.peak = max(self.peak, self.active)
        return FixtureSocket(self)

    def selector(self):
        return FixtureSelector()

    def outcome(self, ip, port):
        index = int(ip.rsplit(".", 1)[-1])
        if self.scenario == "mixed" and index % 4 == 0:
            return "open" if port in (80, 443) else "refused"
        return "filtered"


class FixtureSocket:
    def __init__(self, network):
        self.network = network
        self.blocking, self.closed = True, False
        self.timeout = network.timeout

    def setblocking(self, blocking):
        self.blocking = blocking

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect_ex(self, address):
        self.outcome = self.network.outcome(*address)
        if self.blocking:
            if self.outcome == "filtered":
                time.sleep(self.timeout)
            return 0 if self.outcome == "open" else errno.ECONNREFUSED
        return errno.EINPROGRESS

    def getsockopt(self, *args):
        return 0 if self.outcome == "open" else errno.ECONNREFUSED

    def close(self):
        if self.closed:
            raise AssertionError("Double close")
        self.closed = True
        with self.network.lock:
            self.network.active -= 1


class FixtureSelector:
    def __init__(self):
        self.keys = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        assert not self.keys

    def register(self, sock, events, data):
        self.keys[sock] = SimpleNamespace(fileobj=sock, data=data)

    def unregister(self, sock):
        return self.keys.pop(sock)

    def select(self, timeout):
        ready = [(key, 2) for sock, key in self.keys.items() if sock.outcome != "filtered"]
        if not ready:
            time.sleep(timeout)
        return ready


def serial_reference(ip, network, timeout):
    results = []
    for port, name in DEFAULT_TCP_PORTS.items():
        sock = network.socket()
        try:
            sock.settimeout(timeout)
            if sock.connect_ex((ip, port)) == 0:
                results.append(f"{name}({port})")
        finally:
            sock.close()
    return results


def measure(variant, scenario, count, workers, timeout):
    network = FixtureNetwork(scenario, timeout)
    budget = SocketBudget(256)
    first = None
    lock = Lock()
    tracemalloc.start()
    started, cpu_start = time.monotonic(), time.process_time()

    def worker(index):
        nonlocal first
        ip = f"198.18.{index // 254}.{index % 254 + 1}"
        if variant == "serial_reference":
            services = serial_reference(ip, network, timeout)
        else:
            services = scan_tcp_ports(ip, timeout=timeout, budget=budget,
                                      socket_factory=network.socket, selector_factory=network.selector)
        if services:
            with lock:
                if first is None:
                    first = time.monotonic() - started
        return services

    try:
        # Bounded batches mirror the coordinator's limit instead of queuing
        # the entire inventory as thousands of futures at once.
        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for offset in range(0, count, workers * 2):
                results.extend(pool.map(worker, range(offset, min(count, offset + workers * 2))))
        wall, cpu = time.monotonic() - started, time.process_time() - cpu_start
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert network.active == budget.active == 0
    assert network.started == count * len(DEFAULT_TCP_PORTS)
    if variant != "serial_reference":
        assert network.peak <= budget.limit
    return {
        "variant": variant, "scenario": scenario, "targets": count, "workers": workers,
        "fixture_timeout_ms": timeout * 1000, "duration_s": round(wall, 6),
        "cpu_s": round(cpu, 6), "first_detected_host_s": round(first, 6) if first is not None else None,
        "python_peak_allocations_mib": round(peak / 1024**2, 3),
        "connections_started": network.started, "peak_sockets": network.peak,
        "hosts_with_tcp_response": sum(bool(ports) for ports in results),
    }, results


def cancellation_measurement():
    network, budget, cancelled = FixtureNetwork("filtered", 10), SocketBudget(256), Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(scan_tcp_ports, "198.18.0.1", timeout=10, cancel_event=cancelled,
                             budget=budget, socket_factory=network.socket, selector_factory=network.selector)
        deadline = time.monotonic() + 2
        while network.started < len(DEFAULT_TCP_PORTS) and time.monotonic() < deadline:
            time.sleep(.001)
        started = time.monotonic()
        cancelled.set()
        future.result(timeout=2)
        elapsed = time.monotonic() - started
    assert network.active == budget.active == 0
    return round(elapsed, 6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/benchmarks/tcp-first-stage.json")
    args = parser.parse_args()
    rows = []
    for scenario in ("filtered", "mixed"):
        for count in (32, 254, 1024, 4096):
            reference, old_results = measure("serial_reference", scenario, count, 32, .002)
            concurrent, new_results = measure("bounded_concurrent", scenario, count, 32, .002)
            assert old_results == new_results, "Detection coverage changed"
            rows.extend((reference, concurrent))
            print(f"{scenario:8} {count:4}: {reference['duration_s']:.3f}s -> {concurrent['duration_s']:.3f}s; same results")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "python": sys.version,
              "scope": "Simulated TCP only; no packets sent; not a full scan benchmark",
              "memory_metric": "tracemalloc peak Python allocations, not process RSS",
              "cancellation_s": cancellation_measurement(), "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
