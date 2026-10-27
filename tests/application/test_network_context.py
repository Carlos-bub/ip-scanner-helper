from types import SimpleNamespace
import unittest

from ip_scanner_helper.application.scan_service import ScanService
from ip_scanner_helper.application.scanner import ScanOptions
from ip_scanner_helper.domain.network_context import NetworkContext


class SessionContextTests(unittest.TestCase):
    def test_context_is_defensively_copied_and_finished_retains_snapshot(self):
        service = ScanService(SimpleNamespace(carregar_arp_cache=lambda: {}), worker=lambda *args: None)
        options = ScanOptions(network_context=NetworkContext.for_scan("192.0.2.1"))
        session = service.start(["192.0.2.1"], options)
        service.thread.join(2)
        self.assertFalse(service.running)
        external = service.context
        external["interface"]["name"] = "changed"
        self.assertIsNone(service.context["interface"]["name"])
        events = []
        while not service.events.empty():
            events.append(service.events.get_nowait())
        finished = events[-1]
        self.assertEqual(finished.kind, "finished")
        self.assertEqual(finished.payload["network_context"]["comparison_scope"], f"session:{session}")
        finished.payload["network_context"]["interface"]["name"] = "changed"
        self.assertIsNone(service.context["interface"]["name"])

    def test_mismatched_context_fails_before_starting_worker(self):
        service = ScanService(SimpleNamespace(), worker=lambda *args: self.fail("Worker must not start"))
        with self.assertRaises(ValueError):
            service.start(["192.0.2.2"], ScanOptions(network_context=NetworkContext.for_scan("192.0.2.1")))
        self.assertFalse(service.running)
