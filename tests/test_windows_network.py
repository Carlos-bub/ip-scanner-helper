import ctypes
import struct
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core.resolver import NetworkResolver
from core.windows_network import EchoReplyHeader, ping_ipv4


class NativeIcmpTests(unittest.TestCase):
    def api(self, rtt=7, status=0, count=1, address="192.0.2.1"):
        def send(handle, destination, payload, size, options, reply, capacity, timeout):
            header = EchoReplyHeader.from_buffer(reply)
            header.address = struct.unpack("<I", socket.inet_aton(address))[0]
            header.status, header.round_trip_ms = status, rtt
            return count
        return SimpleNamespace(IcmpCreateFile=Mock(return_value=0x12345678ABCDEF),
                               IcmpSendEcho=Mock(side_effect=send), IcmpCloseHandle=Mock())

    def test_native_rtt_and_submillisecond_value_use_reply_not_wall_clock(self):
        for rtt, expected in ((7, 7.0), (0, "< 1 ms")):
            api = self.api(rtt=rtt)
            with patch("core.windows_network._icmp_api", return_value=api):
                self.assertEqual(ping_ipv4("192.0.2.1"), (True, expected))
            self.assertEqual(api.IcmpSendEcho.call_args.args[0], 0x12345678ABCDEF)
            self.assertEqual(api.IcmpSendEcho.call_args.args[-1], 500)
            api.IcmpCloseHandle.assert_called_once_with(0x12345678ABCDEF)

    def test_timeout_unreachable_and_different_reply_source_do_not_prove_presence(self):
        for kwargs in ({"count": 0}, {"status": 11003}, {"address": "192.0.2.254"}):
            api = self.api(**kwargs)
            with patch("core.windows_network._icmp_api", return_value=api):
                self.assertEqual(ping_ipv4("192.0.2.1"), (False, None))
            api.IcmpCloseHandle.assert_called_once()

    def test_invalid_handle_and_exception_do_not_leak(self):
        api = self.api()
        api.IcmpCreateFile.return_value = ctypes.c_void_p(-1).value
        with patch("core.windows_network._icmp_api", return_value=api), self.assertRaises(OSError):
            ping_ipv4("192.0.2.1")
        api.IcmpCloseHandle.assert_not_called()
        api = self.api()
        api.IcmpSendEcho.side_effect = OSError("Native failure")
        with patch("core.windows_network._icmp_api", return_value=api), self.assertRaises(OSError):
            ping_ipv4("192.0.2.1")
        api.IcmpCloseHandle.assert_called_once()

    def test_cli_fallback_only_when_native_api_unavailable(self):
        with patch("core.resolver.os.name", "nt"), \
             patch("core.resolver.ping_ipv4", return_value=(False, None)) as native, \
             patch.object(NetworkResolver, "ping_measurement_cli", return_value=(True, 8)) as cli:
            self.assertEqual(NetworkResolver.ping_measurement("192.0.2.1"), (False, None))
            cli.assert_not_called()
            native.side_effect = OSError("Unavailable")
            self.assertEqual(NetworkResolver.ping_measurement("192.0.2.1"), (True, 8))
            cli.assert_called_once()


if __name__ == "__main__":
    unittest.main()
