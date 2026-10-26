import io
import socket
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError
from urllib.request import Request

from ip_scanner_helper.application.errors import ProbeTimeout, TargetBudgetExceeded
from ip_scanner_helper.application.timing import ProbeContext
from ip_scanner_helper.infrastructure.network.resolver import NetworkResolver, _ScopedRedirect
from ip_scanner_helper.infrastructure.network.tcp_probe import SocketBudget, scan_tcp_ports


class ProbeDeadlineTests(unittest.TestCase):
    def context(self, seconds=1):
        self.now = 0.0
        return ProbeContext.target(seconds, Event(), clock=lambda: self.now)

    def test_snmp_keeps_a_valid_first_field_when_the_next_request_exhausts_target_budget(self):
        context = self.context()

        def query(ip, oid, community, version, timeout, **kwargs):
            self.now += .6
            if self.now > 1:
                raise socket.timeout()
            return [(oid, 4, b"sw-lab")]

        with patch("ip_scanner_helper.infrastructure.network.resolver.query", side_effect=query) as query_mock:
            with self.assertRaises(TargetBudgetExceeded) as error:
                NetworkResolver.query_snmp("192.0.2.1", context=context)
        self.assertEqual(error.exception.partial, ("sw-lab", None, "SNMP v2c"))
        self.assertEqual(query_mock.call_count, 2)

    def test_snmp_v1_last_attempt_still_detects_a_host_after_three_failed_requests(self):
        context = self.context(5)
        calls = []

        def query(ip, oid, community, version, timeout, **kwargs):
            calls.append((version, oid))
            self.now += .35
            if len(calls) < 4:
                raise socket.timeout()
            return [(oid, 4, b"Managed switch")]

        with patch("ip_scanner_helper.infrastructure.network.resolver.query", side_effect=query):
            result = NetworkResolver.query_snmp("192.0.2.1", context=context)
        self.assertEqual(result, (None, "Managed switch", "SNMP v1"))
        self.assertEqual(len(calls), 4)

    def test_http_body_cannot_extend_target_budget_by_sending_small_chunks(self):
        context = self.context()
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers = {}

        def read(size):
            self.now += .4
            return b"x" * size

        response.read1.side_effect = read
        opener = Mock(open=Mock(return_value=response))
        with patch("ip_scanner_helper.infrastructure.network.resolver.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(TargetBudgetExceeded):
                NetworkResolver.query_http_title("192.0.2.1", ports=(80,), context=context)
        self.assertEqual(response.read1.call_count, 3)
        self.assertAlmostEqual(response.fp.raw._sock.settimeout.call_args.args[0], .2)
        response.__exit__.assert_called_once()

    def test_http_authentication_response_is_closed_even_when_its_name_is_used(self):
        stream = io.BytesIO(b"Authentication required")
        error = HTTPError("http://192.0.2.1", 401, "Unauthorized", {"WWW-Authenticate": 'Basic realm="LabPhone"'}, stream)
        opener = Mock(open=Mock(side_effect=error))
        with patch("ip_scanner_helper.infrastructure.network.resolver.urllib.request.build_opener", return_value=opener):
            self.assertEqual(NetworkResolver.query_http_title("192.0.2.1", ports=(80,)), ("LabPhone", 80))
        self.assertTrue(stream.closed)

    def test_redirects_remain_on_scanned_ip_and_ports_and_do_not_drain_response_body(self):
        context = self.context()
        handler = _ScopedRedirect("192.0.2.1", (80, 443), .6, context)
        handler.parent = Mock()
        request = Request("http://192.0.2.1/")
        request.timeout = .6
        for target in ("http://external.example/", "http://192.0.2.2/", "ftp://192.0.2.1/",
                       "http://192.0.2.1:8888/", "http://user:password@192.0.2.1/"):
            self.assertIsNone(handler.redirect_request(request, None, 302, "Found", {}, target))
        stream = Mock()
        self.now = .8
        handler.http_error_302(request, stream, 302, "Found", {"Location": "/login"})
        stream.read.assert_not_called()
        stream.close.assert_called_once()
        self.assertAlmostEqual(handler.parent.open.call_args.kwargs["timeout"], .2)
        for _ in range(2):
            self.assertIsNotNone(handler.redirect_request(request, None, 302, "Found", {}, "https://192.0.2.1/"))
        self.assertIsNone(handler.redirect_request(request, None, 302, "Found", {}, "http://192.0.2.1/"))

    def test_tcp_capacity_wait_is_bounded_and_a_slot_is_not_leaked(self):
        context = ProbeContext.standalone(.025)
        budget = SocketBudget(1)
        self.assertTrue(budget.acquire())
        try:
            with self.assertRaises(ProbeTimeout) as error:
                scan_tcp_ports("192.0.2.1", ports={80: "HTTP"}, budget=budget, context=context,
                               socket_factory=Mock(side_effect=AssertionError("No capacity")))
            self.assertEqual(error.exception.partial, [])
            self.assertEqual(budget.active, 1)
        finally:
            budget.release()
        self.assertEqual(budget.active, 0)

    def test_dns_fallback_uses_remaining_deadline_after_native_api_failure(self):
        context = self.context()

        def native(*args, **kwargs):
            self.now = .8
            raise OSError("Unavailable")

        answer = SimpleNamespace(stdout=b"Name: lab.example\nAddress: 192.0.2.1", returncode=0)
        with patch("ip_scanner_helper.infrastructure.network.resolver.os.name", "nt"), \
             patch("ip_scanner_helper.infrastructure.network.resolver.query_ptr", side_effect=native), \
             patch("ip_scanner_helper.infrastructure.network.resolver.subprocess.run", return_value=answer) as run:
            self.assertEqual(NetworkResolver.query_dns_ptr("192.0.2.1", context=context), "lab.example")
        self.assertAlmostEqual(run.call_args.kwargs["timeout"], .2)
