"""No network: controlled sockets exercise deadlines, errors and global capacity."""

from concurrent.futures import ThreadPoolExecutor
import errno
from types import SimpleNamespace
from threading import Event, Lock
import time
import unittest

from ip_scanner_helper.infrastructure.network.tcp_probe import scan_tcp_ports, SocketBudget
from ip_scanner_helper.application.timing import ProbeContext
from ip_scanner_helper.application.errors import ProbeTimeout


class FakeSocket:
    def __init__(self, network):
        self.network, self.closed = network, False
        self.port = None

    def setblocking(self, blocking):
        assert not blocking

    def connect_ex(self, address):
        self.port = address[1]
        self.address = address
        self.started = time.monotonic()
        self.network.entered.set()
        value = self.network.results.get(self.port, errno.EINPROGRESS)
        if isinstance(value, Exception):
            raise value
        return value

    def getsockopt(self, *args):
        return self.network.errors.get(self.port, 0)

    def close(self):
        assert not self.closed, "Socket closed twice"
        self.closed = True


class FakeSelector:
    def __init__(self, network):
        self.network = network
        self.keys = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        assert not self.keys, "Registered sockets leaked"

    def register(self, sock, events, data):
        self.keys[sock] = SimpleNamespace(fileobj=sock, data=data)

    def unregister(self, sock):
        return self.keys.pop(sock)

    def select(self, timeout):
        if self.network.selector_error:
            raise OSError("Simulated selector failure")
        ready = [(key, 2) for sock, key in self.keys.items()
                 if sock.port in self.network.ready]
        if not ready:
            time.sleep(timeout)
        return ready


class FakeNetwork:
    def __init__(self, results=None, ready=(), errors=None, selector_error=False):
        self.results, self.ready, self.errors = results or {}, set(ready), errors or {}
        self.selector_error = selector_error
        self.sockets, self.entered = [], Event()
        self._lock = Lock()

    def socket(self, *args):
        result = FakeSocket(self)
        with self._lock:
            self.sockets.append(result)
        return result

    def selector(self):
        return FakeSelector(self)


class TcpProbeTests(unittest.TestCase):
    def test_batch_deadline_closes_pending_connections_and_retains_open_ports(self):
        network = FakeNetwork(results={80: 0})
        budget = SocketBudget(4)
        with self.assertRaises(ProbeTimeout) as error:
            self.run_probe(network, timeout=.2, budget=budget, context=ProbeContext.standalone(.025))
        self.assertEqual(error.exception.partial, ["HTTP(80)"])
        self.assertTrue(all(sock.closed for sock in network.sockets))
        self.assertEqual(budget.active, 0)

    def run_probe(self, network, ports=None, **kwargs):
        return scan_tcp_ports("192.0.2.1", {80: "HTTP", 443: "HTTPS", 22: "SSH"} if ports is None else ports,
                              socket_factory=network.socket, selector_factory=network.selector, **kwargs)

    def test_open_refused_and_timed_out_connections_keep_profile_order(self):
        network = FakeNetwork(results={80: 0}, ready={443}, errors={443: errno.ECONNREFUSED})
        budget = SocketBudget(4)
        self.assertEqual(self.run_probe(network, timeout=.002, budget=budget), ["HTTP(80)"])
        self.assertTrue(all(sock.closed for sock in network.sockets))
        self.assertEqual(budget.active, 0)
        self.assertEqual(budget.started, 3)

    def test_windows_pending_code_is_checked_with_so_error(self):
        network = FakeNetwork(results={80: 10035, 443: 10036, 22: 10037}, ready={22, 80, 443})
        self.assertEqual(self.run_probe(network), ["HTTP(80)", "HTTPS(443)", "SSH(22)"])

    def test_connect_failure_and_selector_failure_release_slots(self):
        for network in (FakeNetwork(results={80: OSError("connect failed")}, ready={22, 443}),
                        FakeNetwork(selector_error=True)):
            budget = SocketBudget(3)
            try:
                self.run_probe(network, timeout=.002, budget=budget)
            except OSError:
                self.assertTrue(network.selector_error)
            self.assertEqual(budget.active, 0)
            self.assertTrue(all(sock.closed for sock in network.sockets))

    def test_no_socket_when_already_cancelled(self):
        cancelled = Event()
        cancelled.set()
        network = FakeNetwork()
        self.assertEqual(self.run_probe(network, cancel_event=cancelled), [])
        self.assertFalse(network.sockets)

    def test_global_limit_does_not_skip_ports_under_contention(self):
        network, budget = FakeNetwork(), SocketBudget(3)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.run_probe(network, timeout=.002, budget=budget), range(8)))
        self.assertEqual(results, [[]] * 8)
        self.assertEqual(len(network.sockets), 24)
        self.assertLessEqual(budget.peak, 3)
        self.assertEqual(budget.active, 0)

    def test_cancellation_interrupts_select_and_capacity_wait(self):
        for limit in (1, 4):
            network, cancelled, budget = FakeNetwork(), Event(), SocketBudget(limit)
            held = limit == 1
            if held:
                budget.acquire()
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.run_probe, network, timeout=10, budget=budget, cancel_event=cancelled)
                if not held:
                    self.assertTrue(network.entered.wait(1))
                cancelled.set()
                self.assertEqual(future.result(timeout=1), [])
            if held:
                budget.release()
            self.assertEqual(budget.active, 0)
            self.assertTrue(all(sock.closed for sock in network.sockets))

    def test_socket_creation_error_and_empty_profile_do_not_leak_capacity(self):
        budget = SocketBudget(1)
        def fail(*args):
            raise OSError("No socket resources")
        self.assertEqual(scan_tcp_ports("192.0.2.1", {80: "HTTP"}, budget=budget, socket_factory=fail), [])
        self.assertEqual(scan_tcp_ports("192.0.2.1", {}, budget=budget), [])
        self.assertEqual(budget.active, 0)


if __name__ == "__main__":
    unittest.main()
