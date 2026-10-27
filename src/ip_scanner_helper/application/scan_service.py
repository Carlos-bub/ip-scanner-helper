"""Bounded scheduling, isolated scan sessions and observable worker failures."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from dataclasses import dataclass, field
import logging
import time
from queue import Queue
from threading import Event, Thread
from uuid import uuid4

from ip_scanner_helper.application.ports import NetworkProbe
from ip_scanner_helper.application.scanner import ScanCancelled, ScanOptions, scan_device
from ip_scanner_helper.application.observations import ScanMetrics
from ip_scanner_helper.application.errors import ScanIncomplete
from ip_scanner_helper.application.rate_limit import ProbeRateLimiter
from ip_scanner_helper.domain.network_context import NetworkContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanEvent:
    session_id: str
    kind: str
    payload: dict = field(default_factory=dict)


class ScanService:
    def __init__(self, resolver: NetworkProbe, worker=scan_device):
        self.resolver = resolver
        self.events = Queue()
        self.worker = worker
        self.thread = None
        self.cancelled = Event()
        self.session_id = None
        self.cancel_requested_at = None
        self._context = None

    @property
    def context(self):
        return deepcopy(self._context)

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, targets, options: ScanOptions):
        if self.running:
            raise RuntimeError("Aguarde o encerramento da varredura anterior.")
        targets = tuple(targets)
        if not targets:
            raise ValueError("A varredura precisa de pelo menos um endereço.")
        session_id = uuid4().hex
        context = (options.network_context or NetworkContext()).snapshot(session_id, targets)
        self.cancelled = Event()
        self.cancel_requested_at = None
        self.session_id = session_id
        self._context = context
        self.thread = Thread(target=self._run, args=(self.session_id, targets, options, self.cancelled, context),
                             name="scan-coordinator", daemon=True)
        self.thread.start()
        return self.session_id

    def cancel(self):
        if not self.cancelled.is_set():
            self.cancel_requested_at = time.monotonic()
        self.cancelled.set()

    def _run(self, session, targets, options, cancelled, context):
        completed = errors = limited = 0
        pending = {}
        metrics = ScanMetrics()
        limiter = ProbeRateLimiter(options.probe_rate_limit)

        def emit(kind, **payload):
            self.events.put(ScanEvent(session, kind, payload))

        def discovery(record):
            if not cancelled.is_set():
                metrics.found()
                emit("device", device=record)

        def incomplete(ip, reason, probes):
            nonlocal limited
            limited += 1
            emit("incomplete", ip=ip, reason=reason, probes=dict(probes))

        def run_worker(ip, arp):
            if self.worker is scan_device:
                return self.worker(ip, options, cancelled, arp,
                                   resolver=self.resolver,
                                   observer=metrics.observe if options.probe_metrics else None,
                                   on_discovery=discovery, rate_limiter=limiter)
            return self.worker(ip, options, cancelled, arp)

        try:
            arp = self.resolver.carregar_arp_cache()
            remaining = iter(targets)
            with ThreadPoolExecutor(max_workers=options.workers, thread_name_prefix="network") as pool:
                exhausted = False
                while pending or not exhausted:
                    while not exhausted and not cancelled.is_set() and len(pending) < options.workers * 2:
                        ip = next(remaining, None)
                        if ip is None:
                            exhausted = True
                            break
                        pending[pool.submit(run_worker, ip, arp)] = ip
                    if cancelled.is_set():
                        exhausted = True
                        for future in pending:
                            future.cancel()
                    if not pending:
                        break
                    done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                    progress_changed = False
                    for future in done:
                        ip = pending.pop(future)
                        if future.cancelled():
                            continue
                        try:
                            result = future.result()
                            if not cancelled.is_set():
                                completed += 1
                                if result:
                                    metrics.found()
                                    emit("device", device=result)
                                    if result.get("motivo_coleta_incompleta") == "tempo":
                                        incomplete(ip, result["status"], result["sondas_incompletas"])
                        except ScanCancelled:
                            continue
                        except ScanIncomplete as exc:
                            if cancelled.is_set():
                                continue
                            completed += 1
                            incomplete(ip, exc.reason, exc.probes)
                        except Exception as exc:
                            completed += 1
                            errors += 1
                            logger.error("Falha ao analisar o endereço %s (%s)", ip, type(exc).__name__)
                            emit("error", ip=ip, message="Falha ao analisar endereço; consulte o log.")
                        progress_changed = True
                    if progress_changed:
                        emit("progress", completed=completed, total=len(targets), errors=errors, limited_targets=limited)
        except Exception as exc:
            errors += 1
            logger.error("Falha no coordenador de varredura (%s)", type(exc).__name__)
            emit("error", message="Falha na varredura; consulte o log.")
        finally:
            emit("finished", completed=completed, total=len(targets), errors=errors,
                 cancelled=cancelled.is_set(), limited_targets=limited, network_context=deepcopy(context), metrics={**metrics.snapshot(self.cancel_requested_at),
                                                       "probe_metrics_enabled": options.probe_metrics,
                                                       "probe_rate": limiter.snapshot()})
