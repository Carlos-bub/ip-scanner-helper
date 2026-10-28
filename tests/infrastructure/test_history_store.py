from pathlib import Path
from contextlib import closing
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ip_scanner_helper.domain.history import sanitize_snapshot
from ip_scanner_helper.infrastructure.history_store import SqliteHistoryStore, HistoryStoreError, APPLICATION_ID, SCHEMA_VERSION
from tests.history_fixtures import snapshot


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "inventory.db"
        self.store = SqliteHistoryStore(self.path)

    def test_construction_is_lazy_and_data_survives_new_instance(self):
        self.assertFalse(self.path.exists())
        self.store.initialize()
        self.store.save_session(snapshot())
        reopened = SqliteHistoryStore(self.path)
        reopened.initialize()
        self.assertEqual(reopened.load_session("session-1"), sanitize_snapshot(snapshot()))
        self.assertEqual(reopened.list_sessions()[0]["device_count"], 1)

    def test_upsert_and_reservations_do_not_mix_sessions_or_environments(self):
        self.store.initialize()
        self.store.save_reservation("lab-a", "192.0.2.2", "Printer", ["TI"])
        self.store.save_session(snapshot())
        self.store.save_session(snapshot(devices=[]))
        self.assertEqual(len(self.store.list_sessions()), 1)
        self.assertEqual(len(self.store.list_reservations("lab-a")), 1)
        self.assertFalse(self.store.list_reservations("lab-b"))
        self.store.delete_reservation("lab-b", "192.0.2.2")
        self.assertEqual(len(self.store.list_reservations("lab-a")), 1)

    def test_backup_restore_preserves_previous_database_and_reservations(self):
        self.store.initialize()
        self.store.save_session(snapshot())
        self.store.save_reservation("lab-a", "192.0.2.2", "Printer", [])
        backup = Path(self.directory.name) / "backup.sqlite"
        self.store.backup(backup)
        self.store.save_session(snapshot("session-2"))
        self.store.delete_reservation("lab-a", "192.0.2.2")
        previous = self.store.restore(backup)
        self.assertTrue(previous.is_file())
        self.assertIsNone(self.store.load_session("session-2"))
        self.assertEqual(len(self.store.list_reservations("lab-a")), 1)
        self.assertIsNotNone(SqliteHistoryStore(previous).load_session("session-2"))

    def test_failed_restore_leaves_original_and_source_untouched(self):
        self.store.initialize()
        self.store.save_session(snapshot())
        broken = Path(self.directory.name) / "foreign.db"
        broken.write_bytes(b"foreign data")
        before = self.path.read_bytes()
        with self.assertRaises(HistoryStoreError): self.store.restore(broken)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(broken.read_bytes(), b"foreign data")
        self.assertIsNotNone(self.store.load_session("session-1"))

    def test_restore_replace_failure_keeps_original(self):
        self.store.initialize()
        self.store.save_session(snapshot())
        backup = Path(self.directory.name) / "backup.sqlite"
        self.store.backup(backup)
        self.store.save_session(snapshot("session-2"))
        with patch("ip_scanner_helper.infrastructure.history_store.os.replace", side_effect=OSError("fixture")):
            with self.assertRaises(OSError): self.store.restore(backup)
        self.assertIsNotNone(self.store.load_session("session-2"))

    def test_migration_creates_backup_before_version_one_is_changed(self):
        self.store.initialize()
        self.store.save_session(snapshot())
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("DROP TABLE reservations")
            conn.execute("PRAGMA user_version=1")
        self.store.initialize()
        self.assertTrue(self.store.migration_backup.is_file())
        with closing(sqlite3.connect(self.store.migration_backup)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertIsNotNone(self.store.load_session("session-1"))

    def test_foreign_future_and_empty_databases_are_preserved(self):
        for variant in ("foreign", "future", "empty"):
            path = Path(self.directory.name) / (variant + ".db")
            if variant == "empty": path.touch()
            else:
                with closing(sqlite3.connect(path)) as conn, conn:
                    conn.execute("CREATE TABLE foreign_table(x)")
                    if variant == "future":
                        conn.execute(f"PRAGMA application_id={APPLICATION_ID}")
                        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
            before = path.read_bytes()
            with self.subTest(variant=variant), self.assertRaises(HistoryStoreError): SqliteHistoryStore(path).initialize()
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_save_cannot_damage_committed_session_or_reservation(self):
        self.store.initialize()
        self.store.save_session(snapshot())
        self.store.save_reservation("lab-a", "192.0.2.2", "Printer", [])
        with self.assertRaises(ValueError): self.store.save_session(snapshot(devices=[{"ip": "not-an-ip"}]))
        self.assertIsNotNone(self.store.load_session("session-1"))
        self.assertEqual(len(self.store.list_reservations("lab-a")), 1)

    def test_backup_cannot_overwrite_current_or_existing_files(self):
        self.store.initialize()
        with self.assertRaises(HistoryStoreError): self.store.backup(self.path)
        backup = Path(self.directory.name) / "backup.sqlite"
        self.store.backup(backup)
        with self.assertRaises(FileExistsError): self.store.backup(backup)

    def test_running_session_is_not_rewritten_as_another_process_interrupted(self):
        self.store.initialize()
        self.store.save_session(snapshot(status="running", finished_at=None))
        SqliteHistoryStore(self.path).initialize()
        self.assertEqual(self.store.load_session("session-1")["status"], "running")

    def test_restore_refuses_another_open_sqlite_transaction(self):
        self.store.initialize()
        self.store.save_session(snapshot())
        backup = Path(self.directory.name) / "backup.sqlite"
        self.store.backup(backup)
        with closing(sqlite3.connect(self.path)) as other:
            other.execute("BEGIN IMMEDIATE")
            try:
                with self.assertRaises(HistoryStoreError): self.store.restore(backup)
            finally:
                other.rollback()
        self.assertIsNotNone(self.store.load_session("session-1"))
