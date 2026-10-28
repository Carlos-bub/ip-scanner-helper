import unittest
from unittest.mock import MagicMock, patch

from ip_scanner_helper.infrastructure.network import snmp
from ip_scanner_helper.infrastructure.network.resolver import NetworkResolver
from ip_scanner_helper.infrastructure.network.switch_port_mapper import parse_snmp_response, snmp_walk_tree


def response_packet(value=b"switch-lab", oid="1.3.6.1.2.1.1.5.0", request_id=101, error=0, tag=4):
    tlv = snmp.encode_tlv
    binding = tlv(0x30, tlv(6, snmp.encode_oid(oid)) + tlv(tag, value))
    rid = request_id.to_bytes(4, "big")
    pdu = tlv(0xA2, tlv(2, rid) + tlv(2, bytes([error])) + tlv(2, b"\0") + tlv(0x30, binding))
    return tlv(0x30, tlv(2, b"\1") + tlv(4, b"public") + pdu)


class SnmpTests(unittest.TestCase):
    def test_bulk_request_encodes_non_repeaters_and_max_repetitions(self):
        packet = snmp.Reader(snmp.build_request("1.3.6.1.2.1.2", bulk_repetitions=25))
        message = snmp.Reader(packet.read(0x30)[1])
        message.read(2)
        message.read(4)
        pdu = snmp.Reader(message.read(0xA5)[1])
        self.assertEqual(int.from_bytes(pdu.read(2)[1], "big"), 101)
        self.assertEqual(pdu.read(2)[1], b"\0")
        self.assertEqual(pdu.read(2)[1], b"\x19")
        binding = snmp.Reader(snmp.Reader(pdu.read(0x30)[1]).read(0x30)[1])
        self.assertEqual(snmp.decode_oid(binding.read(6)[1]), "1.3.6.1.2.1.2")
        for kwargs in ({"bulk_repetitions": True}, {"bulk_repetitions": 0}, {"bulk_repetitions": 51},
                       {"bulk_repetitions": 12, "version": 0}, {"bulk_repetitions": 12, "next_oid": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(snmp.SnmpError):
                snmp.build_request("1.3.6.1.2.1.2", **kwargs)

    def test_short_and_long_ber_responses(self):
        for size in (0, 20, 127, 128, 140, 255, 256, 500):
            with self.subTest(size=size):
                expected = b"X" * size
                oid, tag, value = parse_snmp_response(response_packet(expected))
                self.assertEqual((oid, tag, value), ("1.3.6.1.2.1.1.5.0", 4, expected))

    def test_oid_round_trip_including_large_second_arc(self):
        for oid in ("1.3.6.1.2.1", "2.999.0.128.16384", "0.39.1", "2.4294967295.4294967295"):
            self.assertEqual(snmp.decode_oid(snmp.encode_oid(oid)), oid)

    def test_oversized_oid_is_a_protocol_error_without_unbounded_integer_conversion(self):
        for raw in (b"\x2b" + b"\xff" * 2100 + b"\x7f", b"\x2b" + b"\x01" * 128,
                    b"\x2b\x90\x80\x80\x80\x00"):
            with self.subTest(size=len(raw)), self.assertRaises(snmp.SnmpError):
                snmp.decode_oid(raw)
        for oid in ("1.3.4294967296", "1.3." + ".".join("1" for _ in range(128))):
            with self.assertRaises(snmp.SnmpError):
                snmp.encode_oid(oid)

    def test_invalid_oid(self):
        for oid in ("1", "3.2.1", "1.40.1", "1.3.-1"):
            with self.subTest(oid=oid), self.assertRaises(ValueError):
                snmp.encode_oid(oid)

    def test_rejects_truncated_packets(self):
        packet = response_packet(b"X" * 140)
        for cut in range(len(packet)):
            with self.subTest(cut=cut), self.assertRaises(snmp.SnmpError):
                snmp.parse_response(packet[:cut])

    def test_rejects_indefinite_length_and_agent_error(self):
        for packet in (b"\x30\x80", response_packet(error=2)):
            with self.assertRaises(snmp.SnmpError):
                snmp.parse_response(packet)

    def test_decodes_signed_integer(self):
        self.assertEqual(snmp.parse_response(response_packet(b"\xff", tag=2)).values[0][2], -1)

    def test_query_validates_request_id_and_closes_socket(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.recv.return_value = response_packet(request_id=555)
        with patch("ip_scanner_helper.infrastructure.network.snmp.secrets.randbelow", return_value=101), patch("ip_scanner_helper.infrastructure.network.snmp.socket.socket", return_value=sock):
            with self.assertRaises(snmp.SnmpError):
                snmp.query("192.0.2.1", "1.3.6.1.2.1.1.5.0")
        sock.__exit__.assert_called_once()
        sock.connect.assert_called_once_with(("192.0.2.1", 161))

    def test_name_timeout_does_not_discard_description(self):
        values = [("1.3.6.1.2.1.1.1.0", 4, b"Managed switch " + b"X" * 140)]
        with patch("ip_scanner_helper.infrastructure.network.resolver.query", side_effect=[TimeoutError(), values]) as query:
            name, description, source = NetworkResolver.query_snmp("192.0.2.1", "custom")
        self.assertIsNone(name)
        self.assertEqual(len(description), 155)
        self.assertEqual(source, "SNMP v2c")
        self.assertTrue(all(call.args[2] == "custom" for call in query.call_args_list))

    def test_walk_uses_numeric_subtree_boundary(self):
        with patch("ip_scanner_helper.infrastructure.network.switch_port_mapper.query", return_value=[("1.3.6.1.2.1.20.1", 2, 1)]):
            result = snmp_walk_tree("192.0.2.1", "public", "1.3.6.1.2.1.2")
        self.assertEqual(result, {})
        self.assertFalse(result.partial)

    def test_walk_repeated_oid_and_limit_are_partial(self):
        with patch("ip_scanner_helper.infrastructure.network.switch_port_mapper.query", return_value=[("1.3.6.1.2.1.2.1", 2, 1)]):
            repeated = snmp_walk_tree("192.0.2.1", "public", "1.3.6.1.2.1.2")
            limited = snmp_walk_tree("192.0.2.1", "public", "1.3.6.1.2.1.2", max_reps=1)
        self.assertTrue(repeated.partial)
        self.assertTrue(limited.partial)


if __name__ == "__main__":
    unittest.main()
