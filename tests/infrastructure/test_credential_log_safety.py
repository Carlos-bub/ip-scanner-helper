from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ip_scanner_helper.application.scan_service import ScanService
from ip_scanner_helper.application.scanner import ScanOptions
from ip_scanner_helper.infrastructure.network.resolver import NetworkResolver
from ip_scanner_helper.infrastructure.network.snmp import SnmpError
from ip_scanner_helper.infrastructure.network.switch_port_mapper import snmp_walk_tree


class CredentialLogSafetyTests(unittest.TestCase):
    def test_snmp_error_text_is_not_recorded_in_debug_logs(self):
        secret = "synthetic-private-community"
        with patch("ip_scanner_helper.infrastructure.network.resolver.query", side_effect=SnmpError(secret)), \
             self.assertLogs("ip_scanner_helper.infrastructure.network.resolver", level="DEBUG") as logs:
            self.assertEqual(NetworkResolver.query_snmp("192.0.2.1", secret), (None, None, None))
        self.assertNotIn(secret, str(logs.output))

    def test_switch_walk_reason_and_logs_exclude_exception_secret(self):
        secret = "synthetic-private-community"
        with patch("ip_scanner_helper.infrastructure.network.switch_port_mapper.query", side_effect=SnmpError(secret)), \
             self.assertLogs("ip_scanner_helper.infrastructure.network.switch_port_mapper", level="DEBUG") as logs:
            result = snmp_walk_tree("192.0.2.1", secret, "1.3.6.1.2.1.2")
        self.assertTrue(result.partial)
        self.assertNotIn(secret, result.reason)
        self.assertNotIn(secret, str(logs.output))

    def test_worker_exception_is_sanitized_in_logs_and_error_events(self):
        secret = "synthetic-private-community"
        def worker(*args):
            raise RuntimeError(secret)
        service = ScanService(SimpleNamespace(carregar_arp_cache=lambda: {}), worker=worker)
        with self.assertLogs("ip_scanner_helper.application.scan_service", level="ERROR") as logs:
            service.start(["192.0.2.1"], ScanOptions(community=secret))
            service.thread.join(2)
        self.assertFalse(service.running)
        self.assertNotIn(secret, str(logs.output))
        while not service.events.empty():
            self.assertNotIn(secret, str(service.events.get_nowait()))
