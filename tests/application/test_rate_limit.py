from dataclasses import FrozenInstanceError
from threading import Barrier, Event, Thread
import time
import unittest
from unittest.mock import patch

from ip_scanner_helper.application.errors import ScanCancelled, ScanIncomplete, TargetBudgetExceeded
from ip_scanner_helper.application.rate_limit import ProbeRateLimiter
from ip_scanner_helper.application.scan_service import ScanService
from ip_scanner_helper.application.scanner import ScanOptions, scan_device
from ip_scanner_helper.application.timing import ProbeContext, ScanTimeouts
from tests.application.test_timing import Clock, fixture_probe


class ProbeRateTests(unittest.TestCase):
    def test_invalid_rates_are_rejected_at_each_entry(self):
        for value in (-1, 1001, True, False, .5, 1.0, float("nan"), float("inf"), "10", None):
            for constructor in (ProbeRateLimiter, lambda rate: ScanOptions(probe_rate_limit=rate)):
                with self.subTest(value=value, constructor=constructor), self.assertRaises(ValueError):
                    constructor(value)
        options = ScanOptions(probe_rate_limit=1000)
        with self.assertRaises(FrozenInstanceError):
            options.probe_rate_limit = 0

    def test_disabled_limit_never_waits_and_still_checks_cancellation_and_deadlines(self):
        clock, cancelled = Clock(), Event()
        limiter = ProbeRateLimiter(0, clock=clock, waiter=lambda *args: self.fail("Unexpected wait"))
        context = ProbeContext.target(1, cancelled, clock=clock)
        for _ in range(100):
            limiter.acquire(context)
        self.assertEqual(limiter.snapshot()["started"], 100)
        clock.advance(1)
        with self.assertRaises(TargetBudgetExceeded):
            limiter.acquire(context)
        cancelled.set()
        with self.assertRaises(ScanCancelled):
            limiter.acquire(context)
        self.assertEqual(limiter.snapshot()["started"], 100)

    def test_uniform_spacing_and_no_idle_credits(self):
        clock, waits = Clock(), []

        def wait(event, seconds):
            waits.append(seconds)
            clock.advance(seconds)

        limiter = ProbeRateLimiter(4, clock=clock, waiter=wait)
        context = ProbeContext.target(20, Event(), clock=clock)
        starts = []
        for _ in range(5):
            limiter.acquire(context)
            starts.append(clock())
        for actual, expected in zip(starts, (0, .25, .5, .75, 1)):
            self.assertAlmostEqual(actual, expected)
        self.assertTrue(all(0 < seconds <= .05 for seconds in waits))
        clock.advance(5)
        limiter.acquire(context)
        idle_end = clock()
        limiter.acquire(context)
        self.assertAlmostEqual(clock() - idle_end, .25)
        self.assertEqual(limiter.snapshot(), {"limit_per_second": 4, "scope": "collector_starts", "started": 7})

    def test_wait_does_not_extend_deadline_or_reserve_a_future_slot(self):
        clock = Clock()
        limiter = ProbeRateLimiter(1, clock=clock, waiter=lambda event, seconds: clock.advance(seconds))
        limiter.acquire(ProbeContext.target(2, Event(), clock=clock))
        with self.assertRaises(TargetBudgetExceeded):
            limiter.acquire(ProbeContext.target(.2, Event(), clock=clock))
        self.assertAlmostEqual(clock(), .2)
        self.assertEqual(limiter.snapshot()["started"], 1)
        clock.advance(.8)
        limiter.acquire(ProbeContext.target(2, Event(), clock=clock))
        self.assertAlmostEqual(clock(), 1)

    def test_cancel_during_wait_does_not_admit_a_collector(self):
        clock, cancelled = Clock(), Event()
        limiter = ProbeRateLimiter(1, clock=clock, waiter=lambda event, seconds: event.set())
        context = ProbeContext.target(10, cancelled, clock=clock)
        limiter.acquire(context)
        with self.assertRaises(ScanCancelled):
            limiter.acquire(context)
        self.assertEqual(limiter.snapshot()["started"], 1)

    def test_parallel_workers_share_atomic_admission(self):
        clock, cancelled, waiting = Clock(), Event(), Event()
        barrier = Barrier(8)
        errors = []

        def wait(event, seconds):
            waiting.set()
            event.wait(1)

        limiter = ProbeRateLimiter(1, clock=clock, waiter=wait)

        def run():
            try:
                barrier.wait(timeout=2)
                limiter.acquire(ProbeContext.target(10, cancelled, clock=clock))
            except ScanCancelled:
                pass
            except Exception as exc:
                errors.append(exc)

        threads = [Thread(target=run) for _ in range(8)]
        for thread in threads:
            thread.start()
        try:
            self.assertTrue(waiting.wait(2))
            self.assertEqual(limiter.snapshot()["started"], 1)
        finally:
            cancelled.set()
            for thread in threads:
                thread.join(2)
        self.assertFalse(errors)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(limiter.snapshot()["started"], 1)

    def test_wait_consumes_target_budget_and_unconfirmed_target_is_inconclusive(self):
        clock = Clock()
        limiter = ProbeRateLimiter(1, clock=clock, waiter=lambda event, seconds: clock.advance(seconds))
        resolver, calls = fixture_probe()
        with self.assertRaises(ScanIncomplete) as error:
            scan_device("192.0.2.1", ScanOptions(probe_rate_limit=1, timeouts=ScanTimeouts(target_s=.3)),
                        Event(), {}, resolver=resolver, clock=clock, rate_limiter=limiter)
        self.assertEqual([name for name, _ in calls], ["obter_mac_e_presenca_windows"])
        self.assertIn("icmp", error.exception.probes)
        self.assertAlmostEqual(clock(), .3)

    def test_presence_is_preserved_when_wait_exhausts_target(self):
        clock = Clock()
        limiter = ProbeRateLimiter(1, clock=clock, waiter=lambda event, seconds: clock.advance(seconds))
        resolver, _ = fixture_probe(obter_mac_e_presenca_windows=("02:00:00:00:00:01", True))
        result = scan_device("192.0.2.1", ScanOptions(timeouts=ScanTimeouts(target_s=.1)), Event(), {},
                             resolver=resolver, clock=clock, rate_limiter=limiter)
        self.assertFalse(result["coleta_completa"])
        self.assertEqual(result["portas"], "Consulta TCP incompleta")
        self.assertEqual(result["motivo_coleta_incompleta"], "tempo")
        self.assertIn("ARP: resposta atual", result["evidencias"])

    def test_collector_timeout_starts_after_admission_and_snmp_only_remains_discoverable(self):
        clock, starts, deadlines = Clock(), [], []
        resolver, _ = fixture_probe(query_snmp=("sw-only", "Managed switch", "SNMP v2c"))
        original = resolver.ping_measurement

        def icmp(*args, **kwargs):
            starts.append(clock())
            deadlines.append(kwargs["context"].remaining())
            return original(*args, **kwargs)

        resolver.ping_measurement = icmp
        limiter = ProbeRateLimiter(1, clock=clock, waiter=lambda event, seconds: clock.advance(seconds))
        result = scan_device("192.0.2.1", ScanOptions(mode="Rápido", probe_rate_limit=1), Event(), {},
                             resolver=resolver, clock=clock, rate_limiter=limiter)
        self.assertEqual(result["nome"], "sw-only")
        self.assertTrue(result["coleta_completa"])
        self.assertAlmostEqual(starts[0], 1)
        self.assertAlmostEqual(deadlines[0], 1.5)
        self.assertEqual(limiter.snapshot()["started"], 6)

    def test_service_shares_one_limiter_and_new_session_starts_fresh(self):
        resolver, _ = fixture_probe()
        resolver.carregar_arp_cache = lambda: {}
        instances = []
        real_acquire = ProbeRateLimiter.acquire

        def acquire(limiter, context):
            instances.append(limiter)
            return real_acquire(limiter, context)

        service = ScanService(resolver)
        with patch.object(ProbeRateLimiter, "acquire", acquire):
            for _ in range(2):
                service.start(["192.0.2.1", "192.0.2.2"], ScanOptions(workers=2))
                service.thread.join(2)
                self.assertFalse(service.running)
        self.assertEqual(len(instances), 16)
        self.assertEqual(len({id(item) for item in instances[:8]}), 1)
        self.assertIsNot(instances[0], instances[8])
        finished = [event for event in list(service.events.queue) if event.kind == "finished"]
        self.assertEqual([event.payload["metrics"]["probe_rate"]["started"] for event in finished], [8, 8])

    def test_real_service_wait_is_cancelled_promptly_without_network_calls(self):
        entered = Event()
        resolver, calls = fixture_probe()
        resolver.carregar_arp_cache = lambda: {}

        def arp(*args, **kwargs):
            entered.set()
            return None, False

        resolver.obter_mac_e_presenca_windows = arp
        service = ScanService(resolver)
        service.start(["192.0.2.1", "192.0.2.2"], ScanOptions(workers=2, probe_rate_limit=1))
        try:
            self.assertTrue(entered.wait(2))
            before = time.monotonic()
            service.cancel()
            service.thread.join(1)
            self.assertFalse(service.running)
            self.assertLess(time.monotonic() - before, 1)
        finally:
            service.cancel()
            service.thread.join(2)
        self.assertEqual(calls, [])
        finished = list(service.events.queue)[-1]
        self.assertTrue(finished.payload["cancelled"])
        self.assertEqual(finished.payload["errors"], 0)
        self.assertEqual(finished.payload["limited_targets"], 0)
