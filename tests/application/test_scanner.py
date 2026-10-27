from contextlib import ExitStack
from functools import partial
from threading import Event
import unittest
from unittest.mock import patch

from ip_scanner_helper.application.scanner import ScanCancelled, ScanOptions, classify_device, scan_device

from ip_scanner_helper.infrastructure.network.resolver import NetworkResolver
from ip_scanner_helper.domain.port_profiles import PortProfile
from ip_scanner_helper.application.timing import ScanTimeouts

scan_device = partial(scan_device, resolver=NetworkResolver())


class ScannerTests(unittest.TestCase):
    def test_custom_profile_reaches_tcp_and_does_not_remove_udp_snmp_presence(self):
        profile = PortProfile.from_text("custom-lab", "Lab", "8088 Minha aplicação")
        self.mocks["query_snmp"].return_value = ("sw-lab", "Managed switch", "SNMP v2c")
        options = ScanOptions(mode="Rápido", port_profile=profile, timeouts=ScanTimeouts(tcp=.7, snmp=.8, dns_ptr=1.2))
        device = scan_device("192.0.2.8", options, Event(), {})
        self.assertEqual(self.mocks["scan_ports"].call_args.kwargs["ports"], {8088: "Minha aplicação"})
        self.assertEqual(self.mocks["scan_ports"].call_args.kwargs["timeout"], .7)
        self.assertEqual(self.mocks["query_snmp"].call_args.kwargs["timeout"], .8)
        self.assertEqual(self.mocks["query_dns_ptr"].call_args.kwargs["timeout"], 1.2)
        self.assertEqual(device["tipo"], "Switch")
        self.assertEqual(device["portas_previstas_tcp"], [8088])
        self.assertIn("do perfil", device["portas"])

    def test_custom_description_does_not_trigger_http_or_confirm_category(self):
        self.mocks["scan_ports"].return_value = ["Câmera(8088)"]
        profile = PortProfile.from_text("custom-lab", "Lab", "8088 Câmera")
        with patch.object(NetworkResolver, "query_http_title") as http, \
             patch.object(NetworkResolver, "query_sip_voip", return_value=None), \
             patch.object(NetworkResolver, "query_ssdp_device", return_value=None):
            device = scan_device("192.0.2.8", ScanOptions(port_profile=profile), Event(), {})
        http.assert_not_called()
        self.assertEqual(device["tipo"], "Dispositivo não identificado")

    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        defaults = {"obter_mac_e_presenca_windows": (None, False), "ping_measurement": (False, None),
                    "scan_ports": [], "query_snmp": (None, None, None), "query_dns_ptr": None,
                    "query_netbios": None}
        self.mocks = {name: stack.enter_context(patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver." + name, return_value=value))
                      for name, value in defaults.items()}
        self.options = ScanOptions(mode="Rápido")

    def test_stale_arp_cache_does_not_prove_presence(self):
        device = scan_device("192.0.2.8", self.options, Event(), {"192.0.2.8": "00:03:93:00:00:01"})
        self.assertIsNone(device)
        self.mocks["ping_measurement"].assert_called_once()

    def test_udp_snmp_only_device_is_found(self):
        self.mocks["query_snmp"].return_value = ("sw-lab", "Managed switch", "SNMP v2c")
        device = scan_device("192.0.2.8", self.options, Event(), {})
        self.assertEqual(device["tipo"], "Switch")
        self.assertEqual(device["latencia"], "Não medida")
        self.assertIsNone(device["latencia_ms"])

    def test_ping_rtt_is_used_instead_of_wall_clock(self):
        self.mocks["ping_measurement"].return_value = (True, 3.5)
        device = scan_device("192.0.2.8", self.options, Event(), {})
        self.assertEqual(device["latencia_ms"], 3.5)
        self.assertEqual(device["latencia"], "3.5 ms")

    def test_submillisecond_ping_is_preserved_as_bound(self):
        self.mocks["ping_measurement"].return_value = (True, "< 1 ms")
        device = scan_device("192.0.2.8", self.options, Event(), {})
        self.assertEqual(device["latencia"], "< 1 ms")
        self.assertIsNone(device["latencia_ms"])

    def test_cached_mac_is_marked_as_unconfirmed(self):
        self.mocks["ping_measurement"].return_value = (True, 2)
        device = scan_device("192.0.2.8", self.options, Event(), {"192.0.2.8": "00:03:93:00:00:01"})
        self.assertIn("não reconfirmado", device["origem_mac"])
        self.assertEqual(device["tipo"], "Dispositivo não identificado")

    def test_dns_name_has_priority_over_web_title(self):
        self.mocks["ping_measurement"].return_value = (True, 1)
        self.mocks["query_dns_ptr"].return_value = "pc-lab.example"
        self.mocks["scan_ports"].return_value = ["HTTP(80)"]
        with patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_onvif_ws_discovery", return_value=None), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_http_title", return_value=("Login", 80)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_sip_voip", return_value=None), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_ssdp_device", return_value=None):
            device = scan_device("192.0.2.8", ScanOptions(), Event(), {})
        self.assertEqual(device["nome"], "pc-lab.example")
        self.assertEqual(device["origem"], "DNS reverso (PTR)")

    def test_rdp_does_not_prove_active_directory(self):
        kind, confidence, _ = classify_device(None, {3389, 445})
        self.assertNotIn("AD", kind)
        self.assertEqual(confidence, "Baixa")

    def test_cancellation_prevents_network_work(self):
        event = Event()
        event.set()
        with self.assertRaises(ScanCancelled):
            scan_device("192.0.2.8", self.options, event, {})
        self.mocks["obter_mac_e_presenca_windows"].assert_not_called()

    def test_options_validate_worker_count(self):
        for count in (0, -1, 129):
            with self.assertRaises(ValueError):
                ScanOptions(workers=count)
