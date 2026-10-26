"""Bounded nonblocking TCP connects, with cancellation and per-connect deadlines."""

import errno
import selectors
import socket
from threading import BoundedSemaphore, Lock
import time

DEFAULT_TCP_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 53: "DNS", 80: "HTTP", 443: "HTTPS",
    445: "SMB", 5060: "SIP-VoIP", 515: "LPD-Print", 3389: "RDP",
    8080: "HTTP-Alt", 8443: "HTTPS-Alt", 9100: "RAW-Print",
}


class SocketBudget:
    """One process-wide cap, shared by all host workers (not a packet limiter)."""

    def __init__(self, limit=256):
        if limit < 1:
            raise ValueError("Socket limit must be positive")
        self.limit = limit
        self._slots = BoundedSemaphore(limit)
        self._lock = Lock()
        self.active = self.peak = self.started = 0

    def acquire(self):
        if not self._slots.acquire(blocking=False):
            return False
        with self._lock:
            self.active += 1
            self.started += 1
            self.peak = max(self.peak, self.active)
        return True

    def release(self):
        with self._lock:
            self.active -= 1
        self._slots.release()


SOCKET_BUDGET = SocketBudget()
_PENDING = {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY, errno.EINTR,
            10035, 10036, 10037}  # Winsock codes are not POSIX errno values.


def scan_tcp_ports(ip, ports=None, timeout=.2, cancel_event=None, *, budget=None,
                   socket_factory=None, selector_factory=None):
    """Keep the full port profile; waiting for capacity does not expire a probe.

    Each connect gets its timeout after admission. At most 13 connects per host
    are pending; every path releases both the socket and its global slot.
    """
    if timeout <= 0:
        raise ValueError("TCP timeout must be positive")
    ports = DEFAULT_TCP_PORTS if ports is None else ports
    budget = SOCKET_BUDGET if budget is None else budget
    socket_factory = socket.socket if socket_factory is None else socket_factory
    selector_factory = selectors.DefaultSelector if selector_factory is None else selector_factory
    remaining = iter(ports)
    next_port = next(remaining, None)
    pending, opened = {}, set()

    def cancelled():
        return cancel_event is not None and cancel_event.is_set()

    with selector_factory() as selector:
        def retire(sock):
            try:
                selector.unregister(sock)
            except (KeyError, OSError, ValueError):
                pass
            finally:
                pending.pop(sock, None)
                try:
                    sock.close()
                finally:
                    budget.release()

        try:
            while next_port is not None or pending:
                if cancelled():
                    break
                while next_port is not None and len(pending) < 13 and not cancelled():
                    # Read a port only after a slot exists, so none is skipped.
                    if not budget.acquire():
                        break
                    port = next_port
                    next_port = next(remaining, None)
                    sock = None
                    admitted = False
                    try:
                        sock = socket_factory(socket.AF_INET, socket.SOCK_STREAM)
                        sock.setblocking(False)
                        result = sock.connect_ex((ip, port))
                        if result == 0:
                            opened.add(port)
                        elif result in _PENDING:
                            selector.register(sock, selectors.EVENT_WRITE, port)
                            pending[sock] = time.monotonic() + timeout
                            admitted = True
                    except OSError:
                        # A failed connect is not evidence of an open service.
                        pass
                    finally:
                        if not admitted:
                            try:
                                if sock is not None:
                                    sock.close()
                            finally:
                                budget.release()
                if pending:
                    delay = max(0, min(.025, min(pending.values()) - time.monotonic()))
                    for key, _ in selector.select(delay):
                        if cancelled():
                            break
                        try:
                            if key.fileobj.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0:
                                opened.add(key.data)
                        except OSError:
                            pass
                        finally:
                            retire(key.fileobj)
                    now = time.monotonic()
                    for sock, deadline in list(pending.items()):
                        if now >= deadline:
                            retire(sock)
                elif next_port is not None and not cancelled():
                    if cancel_event is not None:
                        cancel_event.wait(.01)
                    else:
                        time.sleep(.01)
        finally:
            for sock in list(pending):
                retire(sock)
    return [f"{service}({port})" for port, service in ports.items() if port in opened]
