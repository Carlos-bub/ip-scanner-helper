"""IPv4 adapters from GetAdaptersAddresses. All native memory stays in this call."""

import ctypes as C
from functools import lru_cache
from ipaddress import IPv4Address
import os
import socket

U32, U64 = C.c_uint32, C.c_uint64


class SocketAddress(C.Structure):
    _fields_ = [("address", C.c_void_p), ("length", C.c_int32)]


class SockaddrIPv4(C.Structure):
    _fields_ = [("family", C.c_uint16), ("port", C.c_uint16),
                ("ip", C.c_ubyte * 4), ("padding", C.c_ubyte * 8)]


class UnicastAddress(C.Structure):
    pass


UnicastAddress._fields_ = [
    ("length", U32), ("flags", U32), ("next", C.POINTER(UnicastAddress)),
    ("socket", SocketAddress), ("prefix_origin", C.c_int32), ("suffix_origin", C.c_int32),
    ("dad_state", C.c_int32), ("valid_lifetime", U32), ("preferred_lifetime", U32),
    ("lease_lifetime", U32), ("prefix_length", C.c_uint8),
]


class GatewayAddress(C.Structure):
    pass


GatewayAddress._fields_ = [
    ("length", U32), ("reserved", U32), ("next", C.POINTER(GatewayAddress)),
    ("socket", SocketAddress),
]


class AdapterAddress(C.Structure):
    pass


# Prefix of IP_ADAPTER_ADDRESSES_LH through FirstGatewayAddress. A native
# structure can be longer; its Length is checked before reading these fields.
AdapterAddress._fields_ = [
    ("length", U32), ("index", U32), ("next", C.POINTER(AdapterAddress)),
    ("adapter_name", C.c_char_p), ("unicast", C.POINTER(UnicastAddress)),
    ("anycast", C.c_void_p), ("multicast", C.c_void_p), ("dns_servers", C.c_void_p),
    ("dns_suffix", C.c_wchar_p), ("description", C.c_wchar_p), ("friendly_name", C.c_wchar_p),
    ("physical_address", C.c_ubyte * 8), ("physical_length", U32), ("flags", U32),
    ("mtu", U32), ("interface_type", U32), ("oper_status", C.c_int32), ("ipv6_index", U32),
    ("zone_indices", U32 * 16), ("first_prefix", C.c_void_p),
    ("transmit_speed", U64), ("receive_speed", U64), ("wins", C.c_void_p),
    ("gateway", C.POINTER(GatewayAddress)),
]


@lru_cache(maxsize=1)
def _adapter_api():
    if os.name != "nt":
        raise OSError("Windows adapter API is unavailable")
    api = C.WinDLL("iphlpapi.dll", use_last_error=True)
    api.GetAdaptersAddresses.argtypes = [U32, U32, C.c_void_p, C.c_void_p, C.POINTER(U32)]
    api.GetAdaptersAddresses.restype = U32
    return api


def _chain(pointer, minimum_length):
    seen = set()
    while pointer:
        address = C.addressof(pointer.contents)
        if address in seen or len(seen) >= 4096:
            raise OSError("Invalid adapter address chain")
        seen.add(address)
        item = pointer.contents
        if item.length < minimum_length:
            raise OSError("Unsupported Windows adapter structure")
        yield item
        pointer = item.next


def _ipv4(address):
    if not address.address or address.length < C.sizeof(SockaddrIPv4):
        return None
    value = C.cast(address.address, C.POINTER(SockaddrIPv4)).contents
    if value.family != socket.AF_INET:
        return None
    ip = IPv4Address(bytes(value.ip))
    return None if ip.is_unspecified or ip.is_loopback or ip.is_multicast else str(ip)


def _parse_adapters(pointer):
    records = []
    adapter_size = AdapterAddress.gateway.offset + C.sizeof(C.c_void_p)
    unicast_size = UnicastAddress.prefix_length.offset + 1
    for adapter in _chain(pointer, adapter_size):
        if adapter.oper_status != 1 or adapter.interface_type == 24:  # Up / software loopback
            continue
        gateways = [_ipv4(item.socket) for item in _chain(adapter.gateway, C.sizeof(GatewayAddress))]
        gateway = next((ip for ip in gateways if ip), None)
        identifier = (adapter.adapter_name or b"").decode("utf-8", errors="replace")
        name = adapter.friendly_name or adapter.description or identifier
        for unicast in _chain(adapter.unicast, unicast_size):
            address = _ipv4(unicast.socket)
            # Keep preferred/deprecated addresses; ignore duplicate/tentative ones.
            if address and unicast.prefix_length <= 32 and unicast.dad_state in (3, 4):
                records.append({"name": name, "address": address, "prefix": unicast.prefix_length,
                                "gateway": gateway, "adapter_id": identifier})
    return records


def get_ipv4_adapters():
    api = _adapter_api()
    size = U32(15000)
    for _ in range(3):
        if not 0 < size.value <= 16 * 1024 * 1024:
            raise OSError("Invalid Windows adapter buffer size")
        buffer = C.create_string_buffer(size.value)
        # Skip irrelevant address lists and include gateways. Read-only; no probes.
        status = api.GetAdaptersAddresses(socket.AF_INET, 0x008E, None, buffer, C.byref(size))
        if status == 111:  # ERROR_BUFFER_OVERFLOW, e.g. adapters changed during enumeration
            continue
        if status == 232:  # ERROR_NO_DATA
            return []
        if status != 0:
            raise OSError(status, "GetAdaptersAddresses failed")
        return _parse_adapters(C.cast(buffer, C.POINTER(AdapterAddress)))
    raise OSError("Adapter configuration kept changing during enumeration")
