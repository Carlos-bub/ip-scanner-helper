"""Versioned local history with short-lived SQLite connections and safe copies.

This store owns only its application database. It never repairs or replaces an
unrecognised file, and never infers that another process's session was stopped.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from uuid import uuid4

from ip_scanner_helper.domain.history import sanitize_reservation, sanitize_snapshot


APPLICATION_ID = 0x49534848  # ISHH, independent of SQLite's schema version.
SCHEMA_VERSION = 2
MAX_DATABASE_BYTES = 256 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
LOCK_TIMEOUT = 3.0
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_SESSIONS_SQL = """CREATE TABLE sessions (
    id TEXT PRIMARY KEY NOT NULL,
    started_at TEXT NOT NULL,
    snapshot TEXT NOT NULL
)"""
_RESERVATIONS_SQL = """CREATE TABLE reservations (
    environment_id TEXT NOT NULL,
    ip TEXT NOT NULL,
    label TEXT NOT NULL,
    tags TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (environment_id, ip)
)"""
_INDEX_SQL = "CREATE INDEX sessions_started_idx ON sessions(started_at DESC, id DESC)"


class HistoryStoreError(RuntimeError):
    """A readable error that contains no saved inventory or credential values."""


class HistoryBusyError(HistoryStoreError):
    """An operation could not obtain exclusive access within its deadline."""


def _json(value):
    data = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    if len(data.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise HistoryStoreError("O registro excede o limite de tamanho do histórico.")
    return data


def _same_path(first, second):
    if first.resolve() == second.resolve():
        return True
    try:
        return os.path.samefile(first, second)
    except (OSError, ValueError):
        return False


def _normal_sql(value):
    return " ".join(value.split()).strip().rstrip(";").casefold()


class SqliteHistoryStore:
    """Persistence adapter; all connection objects stay on their calling thread.

    A cooperative OS file lock serialises operations across app instances. The
    database uses rollback journals, so restore can reject outstanding WAL or
    journal files instead of discarding another connection's pending work.
    """

    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        with _LOCKS_GUARD:
            self._lock = _LOCKS.setdefault(str(self.path).casefold(), threading.RLock())
        self.migration_backup = None
        self.restore_backup = None

    @contextmanager
    def _guard(self):
        if not self._lock.acquire(timeout=LOCK_TIMEOUT):
            raise HistoryBusyError("O histórico está em uso. Tente novamente.")
        handle = None
        acquired = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.path.with_name(self.path.name + ".lock").open("a+b")
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            deadline = time.monotonic() + LOCK_TIMEOUT
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise HistoryBusyError("Outra instância está usando o histórico.") from None
                    time.sleep(0.025)
            yield
        except sqlite3.Error:
            raise HistoryStoreError("O histórico está indisponível, inválido ou em uso.") from None
        finally:
            if handle is not None:
                if acquired:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()
            self._lock.release()

    def _connect(self, path=None, *, readonly=False):
        path = self.path if path is None else Path(path)
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_DATABASE_BYTES:
            raise HistoryStoreError("O arquivo de histórico está ausente ou tem tamanho inválido.")
        connection = sqlite3.connect(path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
                                     uri=True, timeout=1.0)
        try:
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=1000")
            if readonly:
                connection.execute("PRAGMA query_only=ON")
            return connection
        except BaseException:
            connection.close()
            raise

    @staticmethod
    def _schema(connection):
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if app_id != APPLICATION_ID:
            raise HistoryStoreError("Este arquivo não é um histórico do IP Scanner Helper.")
        if version not in (1, SCHEMA_VERSION):
            raise HistoryStoreError("A versão deste histórico não é compatível com o aplicativo.")
        expected = {"sessions": _SESSIONS_SQL, "sessions_started_idx": _INDEX_SQL}
        if version == SCHEMA_VERSION:
            expected["reservations"] = _RESERVATIONS_SQL
        actual = {name: sql for name, sql in connection.execute(
            "SELECT name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'")}
        if set(actual) != set(expected) or any(
                _normal_sql(actual[name] or "") != _normal_sql(sql) for name, sql in expected.items()):
            raise HistoryStoreError("A estrutura do histórico não corresponde ao esquema esperado.")
        return version

    @staticmethod
    def _snapshot(raw, row_id=None, started_at=None):
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            raise HistoryStoreError("Há um registro de histórico com tamanho inválido.")
        try:
            value = json.loads(raw)
            safe = sanitize_snapshot(value)
            if safe != value or (row_id is not None and safe["id"] != row_id) or (
                    started_at is not None and safe["started_at"] != started_at):
                raise ValueError
            return safe
        except (ValueError, TypeError, KeyError, RecursionError):
            raise HistoryStoreError("Há um registro de histórico inválido ou não reconhecido.") from None

    def _validate(self, connection, *, full=False):
        version = self._schema(connection)
        if full:
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise HistoryStoreError("A verificação de integridade do histórico falhou.")
            for row_id, started_at, raw in connection.execute("SELECT id,started_at,snapshot FROM sessions"):
                self._snapshot(raw, row_id, started_at)
            if version == SCHEMA_VERSION:
                for environment, ip, label, tags, updated in connection.execute(
                        "SELECT environment_id,ip,label,tags,updated_at FROM reservations"):
                    try:
                        value = sanitize_reservation(environment, ip, label, json.loads(tags))
                        if (value["environment_id"], value["ip"], value["label"], _json(value["tags"])) != (
                                environment, ip, label, tags):
                            raise ValueError
                        instant = datetime.fromisoformat(updated)
                        if instant.tzinfo is None:
                            raise ValueError
                    except (ValueError, TypeError, KeyError):
                        raise HistoryStoreError("Há uma reserva inválida no histórico.") from None
        return version

    @staticmethod
    @contextmanager
    def _transaction(connection):
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _temporary(parent):
        descriptor, filename = tempfile.mkstemp(prefix=".history-", suffix=".tmp", dir=parent)
        os.close(descriptor)
        return Path(filename)

    def _copy(self, source, destination):
        """SQLite's backup API includes committed WAL data and a consistent view."""
        deadline = time.monotonic() + 10.0
        def progress(status, remaining, total):
            if time.monotonic() >= deadline:
                raise HistoryBusyError("O backup não obteve uma leitura consistente a tempo.")
        output = sqlite3.connect(destination, timeout=1.0)
        try:
            source.backup(output, pages=128, progress=progress, sleep=0.025)
        finally:
            output.close()
        if destination.stat().st_size > MAX_DATABASE_BYTES:
            raise HistoryStoreError("O arquivo excede o limite de tamanho do histórico.")
        with destination.open("r+b") as handle:
            os.fsync(handle.fileno())

    def _initialize_locked(self):
        if not self.path.exists():
            # Reserve the name exclusively; an existing empty/foreign file is never adopted.
            with self.path.open("xb"):
                pass
            connection = sqlite3.connect(self.path, timeout=1.0)
            try:
                with self._transaction(connection):
                    connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    connection.execute(_SESSIONS_SQL)
                    connection.execute(_INDEX_SQL)
                    connection.execute(_RESERVATIONS_SQL)
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            except BaseException:
                connection.close()
                self.path.unlink(missing_ok=True)
                raise
            connection.close()
            return
        connection = self._connect()
        try:
            version = self._validate(connection, full=True)
            if version == 1:
                destination = self.path.with_name(f"{self.path.stem}.v1-backup-{uuid4().hex[:12]}.sqlite")
                self._backup_locked(connection, destination)
                self.migration_backup = destination
                with self._transaction(connection):
                    # Recheck after taking the write lock; another writer cannot alter schema here.
                    if self._schema(connection) != 1:
                        raise HistoryStoreError("O esquema mudou durante a migração.")
                    connection.execute(_RESERVATIONS_SQL)
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        finally:
            connection.close()

    def initialize(self):
        with self._guard():
            self._initialize_locked()

    def _current(self):
        if not self.path.exists():
            self._initialize_locked()
        connection = self._connect()
        try:
            if self._validate(connection) != SCHEMA_VERSION:
                connection.close()
                self._initialize_locked()
                connection = self._connect()
            return connection
        except BaseException:
            connection.close()
            raise

    def save_session(self, snapshot: dict):
        safe = sanitize_snapshot(snapshot)
        raw = _json(safe)
        with self._guard():
            connection = self._current()
            try:
                with self._transaction(connection):
                    connection.execute("INSERT INTO sessions(id,started_at,snapshot) VALUES(?,?,?) "
                                       "ON CONFLICT(id) DO UPDATE SET started_at=excluded.started_at,snapshot=excluded.snapshot",
                                       (safe["id"], safe["started_at"], raw))
                    pages = connection.execute("PRAGMA page_count").fetchone()[0]
                    size = connection.execute("PRAGMA page_size").fetchone()[0]
                    if pages * size > MAX_DATABASE_BYTES:
                        raise HistoryStoreError("O histórico atingiu o limite de tamanho. Faça um backup.")
            finally:
                connection.close()

    def list_sessions(self, limit=200):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Limite de sessões inválido.")
        with self._guard():
            connection = self._current()
            try:
                results = []
                for row_id, started, raw in connection.execute(
                        "SELECT id,started_at,snapshot FROM sessions ORDER BY started_at DESC,id DESC LIMIT ?", (limit,)):
                    snapshot = self._snapshot(raw, row_id, started)
                    context = snapshot["network_context"]
                    results.append({key: snapshot[key] for key in ("id", "started_at", "finished_at", "status", "coverage", "options")})
                    results[-1].update(environment_id=context.get("environment_id"),
                                       environment_label=context.get("environment_label", ""),
                                       environment_reusable=context.get("environment_reusable", False),
                                       target_expression=context.get("target_expression", ""),
                                       target_count=len(snapshot["targets"]), device_count=len(snapshot["devices"]),
                                       network_context=context)
                return results
            finally:
                connection.close()

    def load_session(self, session_id):
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 128:
            raise ValueError("Identificador de sessão inválido.")
        with self._guard():
            connection = self._current()
            try:
                row = connection.execute("SELECT started_at,snapshot FROM sessions WHERE id=?", (session_id,)).fetchone()
                return None if row is None else self._snapshot(row[1], session_id, row[0])
            finally:
                connection.close()

    def save_reservation(self, environment_id, ip, label, tags):
        safe = sanitize_reservation(environment_id, ip, label, tags)
        with self._guard():
            connection = self._current()
            try:
                with self._transaction(connection):
                    connection.execute("INSERT INTO reservations VALUES(?,?,?,?,?) ON CONFLICT(environment_id,ip) "
                                       "DO UPDATE SET label=excluded.label,tags=excluded.tags,updated_at=excluded.updated_at",
                                       (safe["environment_id"], safe["ip"], safe["label"], _json(safe["tags"]),
                                        datetime.now(timezone.utc).isoformat()))
            finally:
                connection.close()

    def list_reservations(self, environment_id):
        # Reuse the domain's exact environment validation without inventing an IP reservation.
        from ip_scanner_helper.domain.history import validate_environment_id
        environment_id = validate_environment_id(environment_id)
        with self._guard():
            connection = self._current()
            try:
                rows = []
                for ip, label, tags, updated in connection.execute(
                        "SELECT ip,label,tags,updated_at FROM reservations WHERE environment_id=? ORDER BY ip", (environment_id,)):
                    safe = sanitize_reservation(environment_id, ip, label, json.loads(tags))
                    safe["updated_at"] = updated
                    rows.append(safe)
                return rows
            finally:
                connection.close()

    def delete_reservation(self, environment_id, ip):
        safe = sanitize_reservation(environment_id, ip, "", [])
        with self._guard():
            connection = self._current()
            try:
                with self._transaction(connection):
                    connection.execute("DELETE FROM reservations WHERE environment_id=? AND ip=?",
                                       (safe["environment_id"], safe["ip"]))
            finally:
                connection.close()

    def _destination(self, path):
        destination = Path(path).expanduser().resolve()
        if _same_path(self.path, destination) or any(
                _same_path(self.path.with_name(self.path.name + suffix), destination)
                for suffix in ("-wal", "-shm", "-journal", ".lock")):
            raise HistoryStoreError("Escolha um arquivo diferente do histórico em uso.")
        if destination.exists():
            connection = self._connect(destination, readonly=True)
            try:
                self._validate(connection, full=True)
            finally:
                connection.close()
            raise FileExistsError("Escolha um novo nome para preservar o backup existente.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    def _backup_locked(self, connection, destination):
        destination = self._destination(destination)
        temporary = self._temporary(destination.parent)
        try:
            self._copy(connection, temporary)
            validation = self._connect(temporary, readonly=True)
            try:
                self._validate(validation, full=True)
            finally:
                validation.close()
            # Publish a completed file atomically, without replacing a destination
            # created after the checks above. Windows rename never overwrites;
            # POSIX hard-link creation provides the equivalent no-clobber step.
            if os.name == "nt":
                os.rename(temporary, destination)
            else:
                os.link(temporary, destination)
            return destination
        finally:
            temporary.unlink(missing_ok=True)

    def backup(self, path):
        with self._guard():
            connection = self._current()
            try:
                return self._backup_locked(connection, path)
            finally:
                connection.close()

    def restore(self, path):
        source = Path(path).expanduser().resolve()
        if _same_path(source, self.path):
            raise HistoryStoreError("Escolha um backup diferente do histórico em uso.")
        with self._guard():
            temporary = self._temporary(self.path.parent)
            try:
                original = self._connect(source, readonly=True)
                try:
                    self._validate(original, full=True)
                    self._copy(original, temporary)
                finally:
                    original.close()
                replacement = self._connect(temporary)
                try:
                    version = self._validate(replacement, full=True)
                    if version == 1:
                        with self._transaction(replacement):
                            replacement.execute(_RESERVATIONS_SQL)
                            replacement.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                    self._validate(replacement, full=True)
                finally:
                    replacement.close()
                self._initialize_locked()
                current = self._current()
                try:
                    # A noncooperating SQLite reader/writer makes restore fail conservatively.
                    current.execute("PRAGMA locking_mode=EXCLUSIVE")
                    current.execute("BEGIN EXCLUSIVE")
                    current.execute("SELECT COUNT(*) FROM sessions").fetchone()
                    current.commit()
                    if any(self.path.with_name(self.path.name + suffix).exists()
                           for suffix in ("-wal", "-shm", "-journal")):
                        raise HistoryBusyError("Feche as outras conexões do histórico antes de restaurar.")
                    destination = self.path.with_name(f"{self.path.stem}.pre-restore-{uuid4().hex[:12]}.sqlite")
                    self._backup_locked(current, destination)
                finally:
                    current.close()
                os.replace(temporary, self.path)
                self.restore_backup = destination
                return destination
            finally:
                temporary.unlink(missing_ok=True)
