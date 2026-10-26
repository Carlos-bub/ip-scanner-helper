from dataclasses import FrozenInstanceError, replace
from threading import Event
from types import SimpleNamespace
import unittest

from ip_scanner_helper.application.errors import ProbeTimeout, ScanCancelled, ScanIncomplete, TargetBudgetExceeded
from ip_scanner_helper.application.scanner import ScanOptions, scan_device
from ip_scanner_helper.application.timing import DEFAULT_TIMEOUTS, ProbeContext, ScanTimeouts


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def fixture_probe(**overrides):
    defaults = {
        "obter_mac_e_presenca_windows": (None, False), "ping_measurement": (False, None),
        "scan_ports": [], "query_snmp": (None, None, None), "query_dns_ptr": None,
        "query_netbios": None, "query_pjl_printer_model": None, "query_onvif_ws_discovery": None,
        "query_http_title": (None, None), "query_sip_voip": None, "query_rdp_hostname": None,
        "query_ssh_banner": None, "query_ftp_banner": None, "query_ssl_certificate": (None, None),
        "query_ssdp_device": None,
    }
    calls = []

    def function(name, value):
        def call(ip, **kwargs):
            calls.append((name, kwargs))
            replacement = overrides.get(name, value)
            return replacement(**kwargs) if callable(replacement) else replacement
        return call

    probe = SimpleNamespace(**{name: function(name, value) for name, value in defaults.items()})
    return probe, calls


class TimingTests(unittest.TestCase):
    def test_policy_is_immutable_and_validates_finite_positive_numbers(self):
        for value in (0, -1, True, float("nan"), float("inf"), "20", 301):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ScanTimeouts(target_s=value)
        with self.assertRaises(FrozenInstanceError):
            DEFAULT_TIMEOUTS.target_s = 1
        with self.assertRaises(ValueError):
            ScanOptions(timeouts={})

    def test_monotonic_context_shrinks_timeouts_and_distinguishes_target_from_probe(self):
        clock, cancelled = Clock(), Event()
        target = ProbeContext.target(5, cancelled, clock=clock)
        probe = target.child(3)
        clock.advance(2)
        self.assertEqual(probe.timeout(8), 1)
        clock.advance(1)
        with self.assertRaises(ProbeTimeout) as error:
            probe.check()
        self.assertNotIsInstance(error.exception, TargetBudgetExceeded)
        clock.advance(2)
        with self.assertRaises(TargetBudgetExceeded):
            probe.check()
        cancelled.set()
        with self.assertRaises(ScanCancelled):
            probe.check()

    def test_late_noninterruptible_arp_preserves_presence_and_does_not_claim_tcp_was_checked(self):
        clock = Clock()

        def arp(**kwargs):
            clock.advance(2)
            return "02:00:00:00:00:01", True

        resolver, calls = fixture_probe(obter_mac_e_presenca_windows=arp)
        observations, early = [], []
        result = scan_device("192.0.2.1", ScanOptions(timeouts=ScanTimeouts(target_s=1)), Event(), {},
                             resolver=resolver, observer=observations.append, on_discovery=early.append, clock=clock)
        self.assertEqual([name for name, _ in calls], ["obter_mac_e_presenca_windows"])
        self.assertEqual(len(early), 1)
        self.assertEqual(result["mac"], "02:00:00:00:00:01")
        self.assertEqual(result["origem_mac"], "ARP atual")
        self.assertFalse(result["coleta_completa"])
        self.assertEqual(result["portas"], "Consulta TCP incompleta")
        self.assertIn("icmp", result["sondas_incompletas"])
        states = {item.probe: item.outcome for item in observations}
        self.assertEqual(states["icmp"], "budget_exhausted")
        self.assertEqual(states["tcp"], "not_run")

    def test_unconfirmed_target_exhausting_budget_is_inconclusive_even_with_arp_cache(self):
        clock = Clock()

        def arp(**kwargs):
            clock.advance(2)
            return None, False

        resolver, _ = fixture_probe(obter_mac_e_presenca_windows=arp)
        with self.assertRaises(ScanIncomplete):
            scan_device("192.0.2.1", ScanOptions(timeouts=ScanTimeouts(target_s=1)), Event(),
                        {"192.0.2.1": "00:03:93:00:00:01"}, resolver=resolver, clock=clock)

    def test_valid_snmp_name_and_category_survive_budget_exhaustion_before_dns(self):
        clock = Clock()

        def snmp(**kwargs):
            clock.advance(2)
            return "sw-lab", "Managed switch", "SNMP v2c"

        resolver, calls = fixture_probe(query_snmp=snmp)
        result = scan_device("192.0.2.1", ScanOptions(mode="Rápido", timeouts=ScanTimeouts(target_s=1)),
                             Event(), {}, resolver=resolver, clock=clock)
        self.assertEqual(result["nome"], "sw-lab")
        self.assertEqual(result["tipo"], "Switch")
        self.assertEqual(result["origem"], "SNMP v2c")
        self.assertFalse(result["coleta_completa"])
        self.assertNotIn("query_dns_ptr", [name for name, _ in calls])

    def test_partial_tcp_connect_is_evidence_even_when_batch_deadline_is_exhausted(self):
        def tcp(**kwargs):
            raise ProbeTimeout(partial=["HTTP(80)"])

        resolver, calls = fixture_probe(scan_ports=tcp)
        result = scan_device("192.0.2.1", ScanOptions(mode="Rápido"), Event(), {}, resolver=resolver)
        self.assertIn("TCP: conexão aceita", result["evidencias"])
        self.assertEqual(result["portas"], "HTTP(80)")
        self.assertFalse(result["coleta_completa"])
        self.assertIn("query_snmp", [name for name, _ in calls])

    def test_custom_timeouts_are_forwarded_and_failed_ping_still_runs_tcp_and_snmp(self):
        timing = replace(DEFAULT_TIMEOUTS, icmp=.1, tcp=.12, snmp=.2, dns_ptr=.3)
        resolver, calls = fixture_probe(query_snmp=("snmp-only", "Managed switch", "SNMP v2c"))
        result = scan_device("192.0.2.1", ScanOptions(mode="Rápido", timeouts=timing), Event(), {}, resolver=resolver)
        by_name = dict(calls)
        self.assertEqual(result["nome"], "snmp-only")
        self.assertTrue(result["coleta_completa"])
        self.assertEqual(by_name["ping_measurement"]["timeout"], .1)
        self.assertEqual(by_name["scan_ports"]["timeout"], .12)
        self.assertEqual(by_name["query_snmp"]["timeout"], .2)
        self.assertEqual(by_name["query_dns_ptr"]["timeout"], .3)

    def test_probe_timeout_allows_name_fallback_and_cancellation_discards_late_values(self):
        def dns(**kwargs):
            raise ProbeTimeout()

        resolver, _ = fixture_probe(ping_measurement=(True, 1), query_dns_ptr=dns, query_netbios="PC-LAB")
        result = scan_device("192.0.2.1", ScanOptions(mode="Rápido"), Event(), {}, resolver=resolver)
        self.assertEqual(result["nome"], "PC-LAB")
        self.assertFalse(result["coleta_completa"])
        cancelled = Event()

        def cancel(**kwargs):
            cancelled.set()
            return "late.example"

        resolver.query_dns_ptr = lambda *args, **kwargs: cancel(**kwargs)
        with self.assertRaises(ScanCancelled):
            scan_device("192.0.2.1", ScanOptions(mode="Rápido"), cancelled, {}, resolver=resolver)
