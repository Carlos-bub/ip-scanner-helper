"""Small, explicitly typed Windows IP Helper adapter. No DLL load at import."""

import ctypes
from functools import lru_cache
from ipaddress import IPv4Address
import os
import socket
import struct


class EchoReplyHeader(ctypes.Structure):
    # Read only the fixed-width prefix. Data/options pointer layouts differ
    # between ICMP_ECHO_REPLY and ICMP_ECHO_REPLY32 and are not dereferenced.
    _fields_ = [("address", ctypes.c_uint32), ("status", ctypes.c_uint32),
                ("round_trip_ms", ctypes.c_uint32), ("data_size", ctypes.c_uint16),
                ("reserved", ctypes.c_uint16)]


@lru_cache(maxsize=1)
def _icmp_api():
    if os.name != "nt":
        raise OSError("Windows ICMP API is unavailable")
    api = ctypes.WinDLL("iphlpapi.dll", use_last_error=True)
    api.IcmpCreateFile.argtypes = []
    api.IcmpCreateFile.restype = ctypes.c_void_p
    api.IcmpCloseHandle.argtypes = [ctypes.c_void_p]
    api.IcmpCloseHandle.restype = ctypes.c_int32
    api.IcmpSendEcho.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                                ctypes.c_uint16, ctypes.c_void_p, ctypes.c_void_p,
                                ctypes.c_uint32, ctypes.c_uint32]
    api.IcmpSendEcho.restype = ctypes.c_uint32
    return api


def ping_ipv4(ip, timeout_ms=500):
    """Return the native RTT, keeping sub-ms values as a bound, never a fake RTT.

    A timeout or unsuccessful ICMP status returns absence of evidence. API
    unavailability raises OSError so the caller can use its bounded CLI fallback.
    """
    ip = str(IPv4Address(ip))
    if not 1 <= timeout_ms <= 30000:
        raise ValueError("ICMP timeout must be between 1 and 30000 ms")
    destination = struct.unpack("<I", socket.inet_aton(ip))[0]
    api = _icmp_api()
    handle = api.IcmpCreateFile()
    if handle in (None, 0, ctypes.c_void_p(-1).value):
        raise OSError("Could not create an ICMP handle")
    try:
        payload = ctypes.create_string_buffer(b"IPScannerHelper")
        # Enough for either reply layout, request payload and ICMP error data.
        reply = ctypes.create_string_buffer(512)
        count = api.IcmpSendEcho(handle, destination, payload, len(payload) - 1,
                                 None, reply, len(reply), timeout_ms)
        if count:
            header = EchoReplyHeader.from_buffer(reply)
            if header.status == 0 and header.address == destination:
                return True, float(header.round_trip_ms) if header.round_trip_ms else "< 1 ms"
        return False, None
    finally:
        api.IcmpCloseHandle(handle)
