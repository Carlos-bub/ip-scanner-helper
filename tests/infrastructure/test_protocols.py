from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from ip_scanner_helper.infrastructure.network.certificates import certificate_name
from ip_scanner_helper.infrastructure.network.resolver import NetworkResolver
from ip_scanner_helper.infrastructure.network.snmp import encode_oid, encode_tlv
from ip_scanner_helper.infrastructure.network.switch_port_mapper import SwitchPortMapper, WalkResult


def name(value):
    pair = encode_tlv(0x30, encode_tlv(6, encode_oid("2.5.4.3")) + encode_tlv(0x0C, value.encode()))
    return encode_tlv(0x30, encode_tlv(0x31, pair))


class ProtocolTests(unittest.TestCase):
    def test_certificate_subject_is_not_confused_with_issuer(self):
        tlv = encode_tlv
        body = (tlv(0xA0, tlv(2, b"\2")) + tlv(2, b"\1") + tlv(0x30, b"")
                + name("Issuer CA") + tlv(0x30, b"") + name("host-lab-" + "X" * 140)
                + tlv(0x30, b""))
        certificate = tlv(0x30, tlv(0x30, body) + tlv(0x30, b"") + tlv(3, b"\0"))
        self.assertEqual(certificate_name(certificate), "host-lab-" + "X" * 140)

    def test_invalid_certificate_returns_no_name(self):
        self.assertIsNone(certificate_name(b"broken"))

    def test_onvif_request_has_valid_namespaces(self):
        data = b'<d:ProbeMatches xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"><d:Scopes>onvif://www.onvif.org/name/Cam%20Lab onvif://www.onvif.org/hardware/LAB-1</d:Scopes></d:ProbeMatches>'
        with patch.object(NetworkResolver, "_udp_exchange", return_value=data) as exchange:
            result = NetworkResolver.query_onvif_ws_discovery("192.0.2.1")
        self.assertEqual(result, "Câmera ONVIF: Cam Lab · LAB-1")
        ET.fromstring(exchange.call_args.args[2])

    def test_ping_parses_reported_rtt_and_ignores_unreachable(self):
        for output, code, expected in (
            (b"Reply from 192.0.2.1: bytes=32 time=12ms TTL=64", 0, (True, 12)),
            (b"Resposta de 192.0.2.1: bytes=32 tempo<1ms TTL=64", 0, (True, "< 1 ms")),
            (b"Reply from 192.0.2.254: Destination host unreachable.", 0, (False, None)),
        ):
            with self.subTest(output=output), patch("ip_scanner_helper.infrastructure.network.resolver.subprocess.run", return_value=SimpleNamespace(stdout=output, returncode=code)):
                self.assertEqual(NetworkResolver.ping_measurement_cli("192.0.2.1"), expected)

    def test_dns_cli_is_bounded_and_bilingual(self):
        for label in ("Name", "Nome"):
            result = SimpleNamespace(stdout=f"{label}: lab.example\nAddress: 192.0.2.1".encode(), returncode=0)
            with patch("ip_scanner_helper.infrastructure.network.resolver.subprocess.run", return_value=result) as run:
                self.assertEqual(NetworkResolver.query_dns_ptr_cli("192.0.2.1"), "lab.example")
                self.assertLessEqual(run.call_args.kwargs["timeout"], 2.5)

    def test_mapper_preserves_more_than_sixty_interfaces(self):
        def walk(ip, community, root, timeout, max_reps):
            result = WalkResult()
            if root == "1.3.6.1.2.1.31.1.1.1.1":
                result.update({f"{root}.{i}": f"Gi1/0/{i}".encode() for i in range(1, 81)})
            elif root == "1.3.6.1.2.1.2.2.1.8":
                result.update({f"{root}.{i}": 1 for i in range(1, 81)})
            return result
        with patch("ip_scanner_helper.infrastructure.network.switch_port_mapper.testar_snmp_comunidade", return_value=True), \
             patch("ip_scanner_helper.infrastructure.network.switch_port_mapper.snmp_walk_tree", side_effect=walk):
            ports = SwitchPortMapper.mapear_switch("192.0.2.1")
        self.assertEqual(len(ports), 80)

    def test_mapper_partial_collection_is_reported(self):
        def walk(ip, community, root, timeout, max_reps):
            result = WalkResult()
            result.partial = True
            if root == "1.3.6.1.2.1.31.1.1.1.1":
                result[root + ".1"] = b"Gi1"
            return result
        with patch("ip_scanner_helper.infrastructure.network.switch_port_mapper.testar_snmp_comunidade", return_value=True), \
             patch("ip_scanner_helper.infrastructure.network.switch_port_mapper.snmp_walk_tree", side_effect=walk):
            ports = SwitchPortMapper.mapear_switch("192.0.2.1")
        self.assertTrue(ports[0]["coleta_parcial"])
