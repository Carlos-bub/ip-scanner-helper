import ctypes as C
from concurrent.futures import ThreadPoolExecutor
import gc
from threading import BoundedSemaphore, Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ip_scanner_helper.application.errors import ProbeTimeout, ScanCancelled
from ip_scanner_helper.application.timing import ProbeContext
from ip_scanner_helper.infrastructure.network import windows_dns as dns
from ip_scanner_helper.infrastructure.network.resolver import NetworkResolver


class DnsFixture:
    def __init__(self, mode="sync", status=0, name="host-lab.example."):
        self.mode, self.status, self.name = mode, status, name
        self.started, self.requests, self.records = Event(), [], []
        self.api = SimpleNamespace(DnsQueryEx=Mock(side_effect=self.query),
                                   DnsCancelQuery=Mock(return_value=0), DnsFree=Mock())

    def query(self, request, result, cancel):
        request = C.cast(request, C.POINTER(dns.DnsQueryRequest)).contents
        address = C.addressof(C.cast(result, C.POINTER(dns.DnsQueryResult)).contents)
        self.requests.append((request.name, request.type, request.options, request.context, address))
        if self.mode in ("sync", "immediate"):
            self.complete(len(self.requests) - 1, callback=self.mode == "immediate")
        self.started.set()
        return self.status if self.mode == "sync" else dns.DNS_REQUEST_PENDING

    def complete(self, index=0, *, callback=True, status=None):
        query, kind, options, token, address = self.requests[index]
        if token not in dns._pending:
            return
        result = dns.DnsQueryResult.from_address(address)
        result.status = self.status if status is None else status
        if not result.status and self.name:
            record = dns.DnsRecordPrefix()
            record.type, record.flags, record.data_length = 12, 1, C.sizeof(C.c_void_p)
            record.name, record.ptr_name = query, self.name
            self.records.append(record)
            result.records = C.pointer(record)
        if callback:
            dns._completion(token, C.cast(address, C.POINTER(dns.DnsQueryResult)))

    def cleanup(self):
        for index in range(len(self.requests)):
            self.complete(index, status=995)


class NativeDnsTests(unittest.TestCase):
    def fixture(self, **kwargs):
        fixture = DnsFixture(**kwargs)
        self.addCleanup(fixture.cleanup)
        self.patch = patch.object(dns, "_dns_api", return_value=fixture.api)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        return fixture

    def test_x64_layout_and_sync_ptr_free_records_once(self):
        fixture = self.fixture()
        self.assertEqual(dns.query_ptr("192.0.2.1"), "host-lab.example")
        self.assertEqual(fixture.requests[0][:2], ("1.2.0.192.in-addr.arpa", 12))
        fixture.api.DnsFree.assert_called_once()
        fixture.api.DnsCancelQuery.assert_not_called()
        self.assertEqual(dns.pending_query_count(), 0)
        self.assertEqual(C.sizeof(dns.DnsQueryCancel), 32)
        if C.sizeof(C.c_void_p) == 8:
            self.assertEqual(C.sizeof(dns.DnsQueryRequest), 64)
            self.assertEqual(dns.DnsQueryRequest.options.offset, 24)
            self.assertEqual(C.sizeof(dns.DnsQueryResult), 32)
            self.assertEqual(dns.DnsRecordPrefix.ptr_name.offset, 32)

    def test_callback_before_query_returns_is_not_freed_twice(self):
        fixture = self.fixture(mode="immediate")
        self.assertEqual(dns.query_ptr("192.0.2.1"), "host-lab.example")
        token, address = fixture.requests[0][3:]
        dns._completion(token, C.cast(address, C.POINTER(dns.DnsQueryResult)))
        fixture.api.DnsFree.assert_called_once()
        self.assertEqual(dns.pending_query_count(), 0)

    def test_nxdomain_is_a_valid_empty_result_and_api_failure_propagates(self):
        fixture = self.fixture(status=9003)
        self.assertIsNone(dns.query_ptr("192.0.2.1"))
        fixture.api.DnsFree.assert_not_called()
        fixture.status = 87
        with self.assertRaises(OSError):
            dns.query_ptr("192.0.2.1")
        self.assertEqual(dns.pending_query_count(), 0)

    def test_timeout_requests_cancel_but_keeps_native_storage_until_late_callback(self):
        fixture = self.fixture(mode="pending")
        with self.assertRaises(ProbeTimeout):
            dns.query_ptr("192.0.2.1", timeout=.02)
        fixture.api.DnsCancelQuery.assert_called_once()
        self.assertEqual(dns.pending_query_count(), 1)
        gc.collect()
        fixture.complete()
        fixture.api.DnsFree.assert_called_once()
        self.assertEqual(dns.pending_query_count(), 0)

    def test_user_cancel_releases_worker_before_late_completion_and_suppresses_result(self):
        fixture = self.fixture(mode="pending")
        cancelled = Event()
        context = ProbeContext.standalone(2, cancelled)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(dns.query_ptr, "192.0.2.1", context=context)
            self.assertTrue(fixture.started.wait(1))
            cancelled.set()
            with self.assertRaises(ScanCancelled):
                future.result(timeout=1)
        fixture.api.DnsCancelQuery.assert_called_once()
        self.assertEqual(dns.pending_query_count(), 1)
        fixture.complete(status=995)
        self.assertEqual(dns.pending_query_count(), 0)

    def test_pending_admission_is_bounded_even_if_os_delays_cancel_callback(self):
        fixture = self.fixture(mode="pending")
        with patch.object(dns, "_slots", BoundedSemaphore(1)):
            try:
                for _ in range(2):
                    with self.assertRaises(ProbeTimeout):
                        dns.query_ptr("192.0.2.1", timeout=.02)
                self.assertEqual(fixture.api.DnsQueryEx.call_count, 1)
                self.assertEqual(dns.pending_query_count(), 1)
            finally:
                fixture.cleanup()
        self.assertEqual(dns.pending_query_count(), 0)

    def test_invalid_and_numeric_names_are_not_reported_as_hostnames(self):
        fixture = self.fixture()
        for name in ("", "192.0.2.1", "bad\nname", "name with space", "x" * 254):
            fixture.name = name
            with self.subTest(name=name):
                self.assertIsNone(dns.query_ptr("192.0.2.1"))
        self.assertEqual(dns.pending_query_count(), 0)

    def test_cache_only_validation_never_uses_wire_queries(self):
        fixture = self.fixture()
        dns.query_ptr("127.0.0.1", cache_only=True)
        self.assertTrue(fixture.requests[0][2] & 0x10)

    def test_native_empty_answer_and_timeout_do_not_launch_nslookup(self):
        with patch("ip_scanner_helper.infrastructure.network.resolver.os.name", "nt"), \
             patch("ip_scanner_helper.infrastructure.network.resolver.query_ptr", return_value=None) as native, \
             patch.object(NetworkResolver, "query_dns_ptr_cli") as cli:
            self.assertIsNone(NetworkResolver.query_dns_ptr("192.0.2.1"))
            cli.assert_not_called()
            native.side_effect = ProbeTimeout()
            with self.assertRaises(ProbeTimeout):
                NetworkResolver.query_dns_ptr("192.0.2.1")
            cli.assert_not_called()
            native.side_effect = OSError("Unavailable")
            NetworkResolver.query_dns_ptr("192.0.2.1")
            cli.assert_called_once()
