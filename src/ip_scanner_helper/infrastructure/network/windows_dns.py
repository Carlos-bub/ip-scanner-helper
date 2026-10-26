"""Asynchronous Windows PTR queries with bounded admission and safe late cleanup."""

import ctypes as C
from functools import lru_cache
from ipaddress import IPv4Address
import logging
import os
from threading import BoundedSemaphore, Event, Lock, RLock

from ip_scanner_helper.application.errors import ProbeTimeout, ScanCancelled
from ip_scanner_helper.application.timing import DEFAULT_TIMEOUTS, operation_context

logger = logging.getLogger(__name__)
DNS_REQUEST_PENDING = 9506
DNS_TYPE_PTR = 12
MAX_PENDING_QUERIES = 64


class DnsRecordPrefix(C.Structure):
    """Only read the fixed header and the PTR pointer of DNS_RECORDW."""


DnsRecordPrefix._fields_ = [
    ("next", C.POINTER(DnsRecordPrefix)), ("name", C.c_wchar_p),
    ("type", C.c_uint16), ("data_length", C.c_uint16),
    ("flags", C.c_uint32), ("ttl", C.c_uint32), ("reserved", C.c_uint32),
    ("ptr_name", C.c_wchar_p),
]


class DnsQueryResult(C.Structure):
    _fields_ = [("version", C.c_uint32), ("status", C.c_int32),
                ("options", C.c_uint64), ("records", C.POINTER(DnsRecordPrefix)),
                ("reserved", C.c_void_p)]


CompletionRoutine = getattr(C, "WINFUNCTYPE", C.CFUNCTYPE)(None, C.c_void_p, C.POINTER(DnsQueryResult))


class DnsQueryRequest(C.Structure):
    _fields_ = [("version", C.c_uint32), ("name", C.c_wchar_p), ("type", C.c_uint16),
                ("options", C.c_uint64), ("servers", C.c_void_p), ("interface_index", C.c_uint32),
                ("callback", CompletionRoutine), ("context", C.c_void_p)]


class DnsQueryCancel(C.Structure):
    _fields_ = [("reserved", C.c_byte * 32)]


@lru_cache(maxsize=1)
def _dns_api():
    if os.name != "nt":
        raise OSError("Windows DNS API is unavailable")
    api = C.WinDLL("dnsapi.dll", use_last_error=True)
    api.DnsQueryEx.argtypes = [C.POINTER(DnsQueryRequest), C.POINTER(DnsQueryResult), C.POINTER(DnsQueryCancel)]
    api.DnsQueryEx.restype = C.c_int32
    api.DnsCancelQuery.argtypes = [C.POINTER(DnsQueryCancel)]
    api.DnsCancelQuery.restype = C.c_int32
    # DnsRecordListFree is a header macro for the exported DnsFree function.
    api.DnsFree.argtypes = [C.c_void_p, C.c_int32]
    api.DnsFree.restype = None
    return api


def _extract_ptr(records):
    visited = set()
    for _ in range(256):
        if not records:
            return None
        address = C.addressof(records.contents)
        if address in visited:
            raise OSError("Invalid native DNS record chain")
        visited.add(address)
        record = records.contents
        if (record.type == DNS_TYPE_PTR and record.flags & 3 == 1
                and record.data_length >= C.sizeof(C.c_void_p) and record.ptr_name):
            name = record.ptr_name.rstrip(".")
            if name and len(name) <= 253 and not any(char.isspace() or ord(char) < 32 for char in name):
                try:
                    IPv4Address(name)
                except ValueError:
                    return name
        records = record.next
    raise OSError("Native DNS record chain is too long")


_pending = {}
_pending_lock = Lock()
_slots = BoundedSemaphore(MAX_PENDING_QUERIES)


def pending_query_count():
    with _pending_lock:
        return len(_pending)


class _Query:
    def __init__(self, api, reverse_name, options):
        self.api, self.lock, self.done = api, RLock(), Event()
        self.name, self.error, self.finished = None, None, False
        self.result, self.cancel = DnsQueryResult(), DnsQueryCancel()
        self.result.version = 1
        self.query_name = C.create_unicode_buffer(reverse_name)
        self.request = DnsQueryRequest()
        self.request.version, self.request.type = 1, DNS_TYPE_PTR
        self.request.name = C.cast(self.query_name, C.c_wchar_p)
        self.request.options = options
        self.request.callback, self.request.context = _completion, id(self)

    def finish(self, result):
        with self.lock:
            if self.finished:
                return
            try:
                if result.contents.status == 0:
                    self.name = _extract_ptr(result.contents.records)
                elif result.contents.status in (50, 87, 120, 127):
                    self.error = OSError("Native DNS API is unavailable or rejected the request")
            except Exception:
                self.error = OSError("Could not read native DNS results")
            finally:
                try:
                    if result.contents.records:
                        self.api.DnsFree(C.cast(result.contents.records, C.c_void_p), 1)
                        result.contents.records = C.POINTER(DnsRecordPrefix)()
                finally:
                    self.finished = True
                    with _pending_lock:
                        _pending.pop(id(self), None)
                    _slots.release()
                    self.done.set()

    def request_cancel(self):
        # A callback may run before, during or after cancellation. The handle
        # stays alive under the same lock until DnsCancelQuery has returned.
        with self.lock:
            if not self.finished:
                self.api.DnsCancelQuery(C.byref(self.cancel))


@CompletionRoutine
def _completion(token, result):
    with _pending_lock:
        state = _pending.get(token)
    if state is not None:
        try:
            state.finish(result)
        except Exception:
            # Exceptions must never cross the native callback boundary.
            logger.exception("Falha ao liberar resultado DNS nativo")


def query_ptr(ip, timeout=DEFAULT_TIMEOUTS.dns_ptr, *, context=None, cache_only=False):
    """Use PTR, not an unbounded gethostbyaddr call or a worker thread per query.

    Cancelled/timed-out queries remain pinned until their native callback. The
    registry and admission cap also bound memory if the OS delays that callback.
    cache_only is used by local API validation and never emits network queries.
    """
    reverse_name = IPv4Address(ip).reverse_pointer
    context = operation_context(timeout, context).child(timeout)
    api = _dns_api()
    while not _slots.acquire(blocking=False):
        context.cancelled.wait(context.timeout(.025))
    try:
        context.check()
        # Fully qualified name, no NetBIOS or multicast name queries.
        state = _Query(api, reverse_name, 0x1880 | (0x10 if cache_only else 0))
    except BaseException:
        _slots.release()
        raise
    with _pending_lock:
        _pending[id(state)] = state
    try:
        status = api.DnsQueryEx(C.byref(state.request), C.byref(state.result), C.byref(state.cancel))
    except BaseException:
        state.finish(C.pointer(state.result))
        raise
    if status != DNS_REQUEST_PENDING:
        if status:
            state.result.status = status
        state.finish(C.pointer(state.result))
    try:
        while not state.done.is_set():
            state.done.wait(context.timeout(.025))
        context.check()
    except (ProbeTimeout, ScanCancelled):
        state.request_cancel()
        raise
    if state.error:
        raise state.error
    return state.name
