from queue import Empty
from threading import Event
import unittest
from unittest.mock import patch

from core.scan_service import ScanService
from core.scanner import ScanOptions, ScanCancelled


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.cache = patch("core.scan_service.NetworkResolver.carregar_arp_cache", return_value={})
        self.cache.start()
        self.addCleanup(self.cache.stop)

    def finish(self, service):
        service.thread.join(timeout=3)
        self.assertFalse(service.running, "A tarefa não encerrou no prazo do teste")
        events = []
        while True:
            try:
                events.append(service.events.get_nowait())
            except Empty:
                return events

    def test_worker_exception_becomes_visible_error(self):
        def fail(*args):
            raise RuntimeError("erro simulado")
        service = ScanService(worker=fail)
        with self.assertLogs("core.scan_service", level="ERROR"):
            service.start(["192.0.2.1"], ScanOptions(workers=1))
            events = self.finish(service)
        self.assertEqual([e.kind for e in events], ["error", "progress", "finished"])
        self.assertEqual(events[-1].payload["errors"], 1)

    def test_cancellation_discards_late_result_and_blocks_overlap(self):
        entered, release = Event(), Event()
        def worker(ip, options, cancelled, cache):
            entered.set()
            release.wait(2)
            return {"ip": ip}
        service = ScanService(worker=worker)
        service.start(["192.0.2.1", "192.0.2.2"], ScanOptions(workers=1))
        self.assertTrue(entered.wait(1))
        try:
            service.cancel()
            with self.assertRaises(RuntimeError):
                service.start(["192.0.2.3"], ScanOptions())
        finally:
            release.set()
        events = self.finish(service)
        self.assertFalse(any(e.kind == "device" for e in events))
        self.assertTrue(events[-1].payload["cancelled"])
        self.assertLess(events[-1].payload["completed"], 2)

    def test_new_scan_gets_new_session(self):
        service = ScanService(worker=lambda ip, *args: {"ip": ip})
        first = service.start(["192.0.2.1"], ScanOptions(workers=1))
        first_events = self.finish(service)
        second = service.start(["192.0.2.2"], ScanOptions(workers=1))
        second_events = self.finish(service)
        self.assertNotEqual(first, second)
        self.assertTrue(all(e.session_id == first for e in first_events))
        self.assertTrue(all(e.session_id == second for e in second_events))

    def test_cooperative_cancel_is_not_error(self):
        def worker(*args):
            raise ScanCancelled()
        service = ScanService(worker=worker)
        service.start(["192.0.2.1"], ScanOptions(workers=1))
        events = self.finish(service)
        self.assertEqual(events[-1].payload["errors"], 0)
