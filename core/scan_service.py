"""Bounded scheduling, isolated scan sessions and observable worker failures."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
import logging
from queue import Queue
from threading import Event, Thread
from uuid import uuid4

from core.resolver import NetworkResolver
from core.scanner import ScanCancelled, ScanOptions, scan_device

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanEvent:
    session_id: str
    kind: str
    payload: dict = field(default_factory=dict)


class ScanService:
    def __init__(self, worker=scan_device):
        self.events = Queue()
        self.worker = worker
        self.thread = None
        self.cancelled = Event()
        self.session_id = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, targets, options: ScanOptions):
        if self.running:
            raise RuntimeError("Aguarde o encerramento da varredura anterior.")
        targets = tuple(targets)
        if not targets:
            raise ValueError("A varredura precisa de pelo menos um endereço.")
        self.cancelled = Event()
        self.session_id = uuid4().hex
        self.thread = Thread(target=self._run, args=(self.session_id, targets, options, self.cancelled),
                             name="scan-coordinator", daemon=True)
        self.thread.start()
        return self.session_id

    def cancel(self):
        self.cancelled.set()

    def _run(self, session, targets, options, cancelled):
        completed = errors = 0
        pending = {}

        def emit(kind, **payload):
            self.events.put(ScanEvent(session, kind, payload))

        try:
            arp = NetworkResolver.carregar_arp_cache()
            remaining = iter(targets)
            with ThreadPoolExecutor(max_workers=options.workers, thread_name_prefix="network") as pool:
                exhausted = False
                while pending or not exhausted:
                    while not exhausted and not cancelled.is_set() and len(pending) < options.workers * 2:
                        ip = next(remaining, None)
                        if ip is None:
                            exhausted = True
                            break
                        pending[pool.submit(self.worker, ip, options, cancelled, arp)] = ip
                    if cancelled.is_set():
                        exhausted = True
                        for future in pending:
                            future.cancel()
                    if not pending:
                        break
                    done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                    for future in done:
                        ip = pending.pop(future)
                        if future.cancelled():
                            continue
                        try:
                            result = future.result()
                            if not cancelled.is_set():
                                completed += 1
                                if result:
                                    emit("device", device=result)
                        except ScanCancelled:
                            continue
                        except Exception:
                            completed += 1
                            errors += 1
                            logger.exception("Falha ao analisar o endereço %s", ip)
                            emit("error", ip=ip, message="Falha ao analisar endereço; consulte o log.")
                        emit("progress", completed=completed, total=len(targets), errors=errors)
        except Exception:
            errors += 1
            logger.exception("Falha no coordenador de varredura")
            emit("error", message="Falha na varredura; consulte o log.")
        finally:
            emit("finished", completed=completed, total=len(targets), errors=errors,
                 cancelled=cancelled.is_set())
