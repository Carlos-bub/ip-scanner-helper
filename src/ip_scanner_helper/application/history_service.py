"""Bounded, serialized history work, isolated from the UI and scan workers."""

from copy import deepcopy
import logging
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from uuid import uuid4

from ip_scanner_helper.application.history_ports import HistoryStore
from ip_scanner_helper.domain.history import sanitize_reservation, sanitize_snapshot, validate_environment_id


class HistoryBusyError(RuntimeError):
    """The caller must retry or report an unsaved change; nothing was accepted."""


class HistoryClosedError(RuntimeError):
    """No new work is accepted after orderly shutdown starts."""


class HistoryActionError(ValueError):
    """The requested command or its arguments are invalid."""


_ACTIONS = frozenset(("initialize", "save_session", "list_sessions", "load_session", "list_reservations",
                      "save_reservation", "delete_reservation", "backup", "restore"))
logger = logging.getLogger(__name__)


class HistoryService:
    """One worker owns all store access; accepted commands always get an event.

    ``submit`` never waits for storage. A full queue is a visible rejection and
    leaves retry policy to the caller. ``close`` drains accepted commands; a
    false result means the worker is still finishing and may be joined again.
    """

    def __init__(self, store: HistoryStore, queue_size=32):
        if isinstance(queue_size, bool) or not isinstance(queue_size, int) or not 1 <= queue_size <= 256:
            raise ValueError("Tamanho da fila de histórico inválido.")
        self.store = store
        self.events = Queue()
        self._commands = Queue(maxsize=queue_size)
        self._lock = Lock()
        self._closing = Event()
        self._pending = set()
        self._cancelled = set()
        self._active = None
        self._initialized = False
        self._final_snapshots = {}
        self.thread = Thread(target=self._run, name="history-storage", daemon=False)
        self.thread.start()

    @property
    def running(self):
        return self.thread.is_alive()

    def submit(self, action, *args):
        if not isinstance(action, str) or action not in _ACTIONS:
            raise HistoryActionError("Operação de histórico inválida.")
        try:
            arguments = deepcopy(args)
        except Exception:
            raise HistoryActionError("Dados inválidos para o histórico.") from None
        token = uuid4().hex
        with self._lock:
            if self._closing.is_set():
                raise HistoryClosedError("O histórico está encerrando.")
            try:
                self._commands.put_nowait((token, action, arguments))
            except Full:
                raise HistoryBusyError("Histórico ocupado; a alteração não foi enfileirada.") from None
            self._pending.add(token)
        return token

    def cancel(self, token):
        """Cancel queued work only; active transactions finish atomically."""
        with self._lock:
            if token not in self._pending or token == self._active:
                return False
            self._cancelled.add(token)
            return True

    def close(self, timeout=5, *, final_snapshots=()):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 <= timeout <= 300:
            raise ValueError("Prazo de encerramento do histórico inválido.")
        with self._lock:
            if not isinstance(final_snapshots, (list, tuple)) or len(final_snapshots) > 16:
                raise ValueError("Quantidade de gravações finais inválida.")
            for snapshot in final_snapshots:
                self._final_snapshots[snapshot["id"]] = deepcopy(snapshot)
            self._closing.set()
        self.thread.join(timeout)
        return not self.running

    def _dispatch(self, action, args):
        if action == "initialize":
            if args:
                raise ValueError("Argumentos inválidos.")
            result = self.store.initialize()
            self._initialized = True
            return result
        if not self._initialized:
            raise RuntimeError("Histórico ainda não inicializado.")
        if action == "save_session":
            if len(args) != 1:
                raise ValueError("Argumentos inválidos.")
            return self.store.save_session(sanitize_snapshot(args[0]))
        if action == "save_reservation":
            reservation = sanitize_reservation(*args)
            return self.store.save_reservation(reservation["environment_id"], reservation["ip"], reservation["label"], reservation["tags"])
        if action in ("list_reservations", "delete_reservation"):
            if not args:
                raise ValueError("Argumentos inválidos.")
            validate_environment_id(args[0])
        return getattr(self.store, action)(*args)

    def _run(self):
        while True:
            try:
                token, action, args = self._commands.get(timeout=.05)
            except Empty:
                if self._closing.is_set():
                    with self._lock:
                        if not self._final_snapshots:
                            return
                        identifier = next(iter(self._final_snapshots))
                        snapshot = self._final_snapshots.pop(identifier)
                    # A bounded shutdown tail follows all accepted queue entries,
                    # preserving the newest terminal state even if the queue was full.
                    token, action, args = uuid4().hex, "save_session", (snapshot,)
                    from_queue = False
                else:
                    continue
            else:
                from_queue = True
            with self._lock:
                cancelled = token in self._cancelled
                self._active = token
            result = None
            error = "Operação de histórico cancelada antes de iniciar." if cancelled else None
            try:
                if not cancelled:
                    result = deepcopy(self._dispatch(action, args))
            except Exception:
                # Raw storage/validation exceptions may contain paths or data.
                error = "Não foi possível concluir a operação de histórico."
                logger.error("Falha na operação de histórico: %s", action)
            finally:
                with self._lock:
                    self._pending.discard(token)
                    self._cancelled.discard(token)
                    self._active = None
                self.events.put((token, action, result, error))
                if from_queue:
                    self._commands.task_done()
