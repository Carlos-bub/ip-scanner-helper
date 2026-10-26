from queue import Empty
from threading import Event
import unittest
from unittest.mock import patch

from ip_scanner_helper.bootstrap import create_scan_service
from ip_scanner_helper.application.scanner import ScanOptions, ScanCancelled
from ip_scanner_helper.application.errors import ScanIncomplete, TargetBudgetExceeded


class ServiceTests(unittest.TestCase):
    def test_late_inconclusive_completion_after_user_cancel_is_discarded(self):
        entered, release = Event(), Event()

        def worker(*args):
            entered.set()
            release.wait(2)
            raise ScanIncomplete("Limite por IP", {"dns_ptr": "tempo"})

        service = create_scan_service(worker=worker)
        service.start(["192.0.2.1"], ScanOptions(workers=1))
        try:
            self.assertTrue(entered.wait(1))
            service.cancel()
        finally:
            release.set()
        events = self.finish(service)
        self.assertFalse(any(event.kind == "incomplete" for event in events))
        self.assertEqual(events[-1].payload["completed"], 0)
        self.assertEqual(events[-1].payload["limited_targets"], 0)

    def test_target_budget_without_presence_is_inconclusive_and_not_an_error(self):
        with patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.obter_mac_e_presenca_windows",
                   side_effect=TargetBudgetExceeded()):
            service = create_scan_service()
            service.start(["192.0.2.1"], ScanOptions(workers=1))
            events = self.finish(service)
        self.assertFalse(any(event.kind == "device" for event in events))
        self.assertEqual(events[-1].payload["completed"], 1)
        self.assertEqual(events[-1].payload["errors"], 0)
        self.assertEqual(events[-1].payload["limited_targets"], 1)
        self.assertEqual(next(event for event in events if event.kind == "incomplete").payload["ip"], "192.0.2.1")

    def test_partial_presence_is_retained_and_budget_is_reported_without_error(self):
        with patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.obter_mac_e_presenca_windows", return_value=(None, True)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.ping_measurement", side_effect=TargetBudgetExceeded()):
            service = create_scan_service()
            service.start(["192.0.2.1"], ScanOptions(workers=1))
            events = self.finish(service)
        devices = [event.payload["device"] for event in events if event.kind == "device"]
        self.assertEqual(len(devices), 2)
        self.assertFalse(devices[-1]["coleta_completa"])
        self.assertEqual(devices[-1]["motivo_coleta_incompleta"], "tempo")
        self.assertEqual(events[-1].payload["errors"], 0)
        self.assertEqual(events[-1].payload["limited_targets"], 1)

    def setUp(self):
        self.cache = patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.carregar_arp_cache", return_value={})
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
        service = create_scan_service(worker=fail)
        with self.assertLogs("ip_scanner_helper.application.scan_service", level="ERROR"):
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
        service = create_scan_service(worker=worker)
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
        service = create_scan_service(worker=lambda ip, *args: {"ip": ip})
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
        service = create_scan_service(worker=worker)
        service.start(["192.0.2.1"], ScanOptions(workers=1))
        events = self.finish(service)
        self.assertEqual(events[-1].payload["errors"], 0)

    def test_presence_is_published_before_slow_dns_and_completion_is_not_premature(self):
        entered, release = Event(), Event()
        def dns(*args, **kwargs):
            entered.set()
            release.wait(2)
            return "host.example"
        with patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.obter_mac_e_presenca_windows", return_value=("02:00:00:00:00:01", True)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.ping_measurement", return_value=(False, None)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.scan_ports", return_value=[]), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_snmp", return_value=(None, None, None)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_dns_ptr", side_effect=dns):
            service = create_scan_service()
            service.start(["192.0.2.1"], ScanOptions(workers=1, mode="Rápido", probe_metrics=True))
            try:
                self.assertTrue(entered.wait(1))
                early = service.events.get(timeout=1)
                self.assertEqual(early.kind, "device")
                self.assertFalse(early.payload["device"]["coleta_completa"])
                self.assertTrue(service.running)
                self.assertTrue(service.events.empty())
            finally:
                release.set()
            events = self.finish(service)
        final = next(event.payload["device"] for event in events if event.kind == "device")
        self.assertTrue(final["coleta_completa"])
        self.assertEqual(final["nome"], "host.example")
        self.assertEqual(events[-1].payload["completed"], 1)
        self.assertEqual(events[-1].payload["metrics"]["probes"]["arp"]["result"], 1)
        self.assertEqual(events[-1].payload["metrics"]["probes"]["snmp"]["no_result"], 1)

    def test_cancel_after_early_result_keeps_that_observation_but_discards_late_enrichment(self):
        entered, release = Event(), Event()
        def dns(*args, **kwargs):
            entered.set()
            release.wait(2)
            return "late.example"
        with patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.obter_mac_e_presenca_windows", return_value=(None, False)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.ping_measurement", return_value=(True, 1)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.scan_ports", return_value=[]), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_snmp", return_value=(None, None, None)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_dns_ptr", side_effect=dns):
            service = create_scan_service()
            service.start(["192.0.2.1"], ScanOptions(workers=1, mode="Rápido", probe_metrics=True))
            try:
                self.assertTrue(entered.wait(1))
                early = service.events.get(timeout=1)
                self.assertFalse(early.payload["device"]["coleta_completa"])
                service.cancel()
            finally:
                release.set()
            events = self.finish(service)
        self.assertFalse(any(event.kind == "device" for event in events))
        self.assertTrue(events[-1].payload["cancelled"])
        self.assertEqual(events[-1].payload["errors"], 0)
        self.assertEqual(events[-1].payload["metrics"]["probes"]["dns_ptr"]["cancelled"], 1)
