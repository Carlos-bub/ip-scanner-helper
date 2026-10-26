import ctypes as C
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ip_scanner_helper.infrastructure.network.interfaces import discover_interfaces
from ip_scanner_helper.infrastructure.network.windows_adapters import (AdapterAddress, GatewayAddress, SockaddrIPv4,
                                   SocketAddress, UnicastAddress, _parse_adapters, get_ipv4_adapters)


class AdapterFixture:
    """Keep every pointed-to object alive throughout a ctypes traversal."""

    def __init__(self):
        self.objects = []

    def sockaddr(self, ip):
        address = SockaddrIPv4()
        address.family = 2
        address.ip[:] = bytes(map(int, ip.split(".")))
        self.objects.append(address)
        return SocketAddress(C.addressof(address), C.sizeof(address))

    def adapter(self, name="Ethernet", addresses=(("192.0.2.10", 27),), gateway="192.0.2.1", state=1):
        adapter = AdapterAddress()
        adapter.length, adapter.oper_status = C.sizeof(adapter), state
        adapter.friendly_name, adapter.adapter_name = name, b"{fixture-adapter}"
        adapter.interface_type = 6
        previous = None
        for ip, prefix in reversed(addresses):
            item = UnicastAddress()
            item.length, item.dad_state = C.sizeof(item), 4
            item.socket, item.prefix_length = self.sockaddr(ip), prefix
            if previous is not None:
                item.next = C.pointer(previous)
            previous = item
            self.objects.append(item)
        if previous is not None:
            adapter.unicast = C.pointer(previous)
        if gateway:
            item = GatewayAddress()
            item.length, item.socket = C.sizeof(item), self.sockaddr(gateway)
            adapter.gateway = C.pointer(item)
            self.objects.append(item)
        self.objects.append(adapter)
        return adapter


class NativeAdapterTests(unittest.TestCase):
    def test_real_prefix_multiple_addresses_and_missing_gateway(self):
        fixture = AdapterFixture()
        first = fixture.adapter(addresses=(("192.0.2.10", 27), ("192.0.2.70", 26)))
        second = fixture.adapter(name="VPN", addresses=(("198.51.100.2", 32),), gateway=None)
        first.next = C.pointer(second)
        records = _parse_adapters(C.pointer(first))
        self.assertEqual([record["prefix"] for record in records], [27, 26, 32])
        self.assertEqual(records[0]["gateway"], "192.0.2.1")
        self.assertIsNone(records[-1]["gateway"])
        self.assertEqual(records[-1]["adapter_id"], "{fixture-adapter}")

    def test_down_loopback_invalid_prefix_and_duplicate_address_are_not_selected(self):
        for kwargs in ({"state": 2}, {"addresses": (("127.0.0.1", 8),)},
                       {"addresses": (("192.0.2.1", 255),)}):
            fixture = AdapterFixture()
            self.assertEqual(_parse_adapters(C.pointer(fixture.adapter(**kwargs))), [])
        fixture = AdapterFixture()
        adapter = fixture.adapter()
        adapter.unicast.contents.dad_state = 2
        self.assertEqual(_parse_adapters(C.pointer(adapter)), [])

    def test_short_structure_and_cycle_fail_instead_of_looping(self):
        fixture = AdapterFixture()
        adapter = fixture.adapter()
        adapter.length = 8
        with self.assertRaises(OSError):
            _parse_adapters(C.pointer(adapter))
        adapter.length = C.sizeof(adapter)
        adapter.next = C.pointer(adapter)
        with self.assertRaises(OSError):
            _parse_adapters(C.pointer(adapter))

    def test_buffer_resize_and_no_data(self):
        calls = []
        def read(family, flags, reserved, buffer, size_pointer):
            calls.append(len(buffer))
            if len(calls) == 1:
                C.cast(size_pointer, C.POINTER(C.c_uint32)).contents.value = 24000
                return 111
            return 232
        api = SimpleNamespace(GetAdaptersAddresses=read)
        with patch("ip_scanner_helper.infrastructure.network.windows_adapters._adapter_api", return_value=api):
            self.assertEqual(get_ipv4_adapters(), [])
        self.assertEqual(calls, [15000, 24000])

    def test_api_failure_and_unbounded_buffer_are_rejected(self):
        api = SimpleNamespace(GetAdaptersAddresses=Mock(return_value=5))
        with patch("ip_scanner_helper.infrastructure.network.windows_adapters._adapter_api", return_value=api), self.assertRaises(OSError):
            get_ipv4_adapters()
        def too_large(family, flags, reserved, buffer, size_pointer):
            C.cast(size_pointer, C.POINTER(C.c_uint32)).contents.value = 2**31
            return 111
        api.GetAdaptersAddresses = too_large
        with patch("ip_scanner_helper.infrastructure.network.windows_adapters._adapter_api", return_value=api), self.assertRaises(OSError):
            get_ipv4_adapters()

    def test_normal_discovery_does_not_start_powershell(self):
        data = [{"name": "Ethernet", "address": "192.0.2.10", "prefix": 27,
                 "gateway": "192.0.2.1", "adapter_id": "fixture"}]
        with patch("ip_scanner_helper.infrastructure.network.interfaces.os.name", "nt"), \
             patch("ip_scanner_helper.infrastructure.network.interfaces.get_ipv4_adapters", return_value=data), \
             patch("ip_scanner_helper.infrastructure.network.interfaces.subprocess.run") as run:
            interfaces = discover_interfaces()
            self.assertEqual(interfaces[0].network, "192.0.2.0/27")
            self.assertEqual(interfaces[0].adapter_id, "fixture")
            run.assert_not_called()

    def test_empty_native_result_is_valid_and_does_not_trigger_fallback(self):
        with patch("ip_scanner_helper.infrastructure.network.interfaces.os.name", "nt"), \
             patch("ip_scanner_helper.infrastructure.network.interfaces.get_ipv4_adapters", return_value=[]), \
             patch("ip_scanner_helper.infrastructure.network.interfaces._discover_interfaces_powershell") as fallback:
            self.assertEqual(discover_interfaces(), [])
            fallback.assert_not_called()

    def test_native_failure_uses_compatibility_fallback(self):
        with patch("ip_scanner_helper.infrastructure.network.interfaces.os.name", "nt"), \
             patch("ip_scanner_helper.infrastructure.network.interfaces.get_ipv4_adapters", side_effect=OSError("unavailable")), \
             patch("ip_scanner_helper.infrastructure.network.interfaces._discover_interfaces_powershell", return_value=[]) as fallback, \
             self.assertLogs("ip_scanner_helper.infrastructure.network.interfaces", level="WARNING"):
            self.assertEqual(discover_interfaces(), [])
            fallback.assert_called_once()
