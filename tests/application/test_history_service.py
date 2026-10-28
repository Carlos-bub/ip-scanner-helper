from queue import Empty
from threading import Event, get_ident
from unittest.mock import Mock
import unittest

from ip_scanner_helper.application.history_service import HistoryService, HistoryBusyError, HistoryClosedError
from tests.history_fixtures import snapshot


class HistoryServiceTests(unittest.TestCase):
    def test_worker_thread_serializes_defensive_snapshots_and_drains(self):
        stored = []
        store = Mock()
        store.save_session.side_effect = lambda value: stored.append((value, get_ident()))
        service = HistoryService(store)
        self.addCleanup(service.close)
        service.submit("initialize")
        value = snapshot()
        service.submit("save_session", value)
        value["devices"][0]["nome"] = "mutated"
        self.assertTrue(service.close())
        self.assertEqual(stored[0][0]["devices"][0]["nome"], "SW-A")
        self.assertNotEqual(stored[0][1], get_ident())
        with self.assertRaises(HistoryClosedError): service.submit("initialize")

    def test_full_queue_is_explicit_and_queued_cancel_gets_an_event(self):
        entered, release = Event(), Event()
        store = Mock()
        def initialize(): entered.set(); release.wait(3)
        store.initialize.side_effect = initialize
        service = HistoryService(store, queue_size=1)
        self.addCleanup(service.close)
        try:
            service.submit("initialize")
            self.assertTrue(entered.wait(2))
            token = service.submit("list_sessions")
            with self.assertRaises(HistoryBusyError): service.submit("list_sessions")
            self.assertTrue(service.cancel(token))
        finally: release.set()
        self.assertTrue(service.close())
        events = [service.events.get_nowait(), service.events.get_nowait()]
        self.assertIn("cancelada", next(item[3] for item in events if item[0] == token))

    def test_storage_exception_does_not_leak_secrets(self):
        store = Mock()
        store.initialize.side_effect = RuntimeError("synthetic-secret")
        service = HistoryService(store)
        self.addCleanup(service.close)
        with self.assertLogs("ip_scanner_helper.application.history_service", level="ERROR") as logs:
            service.submit("initialize")
            self.assertTrue(service.close())
        self.assertNotIn("synthetic-secret", str(logs.output))
        self.assertNotIn("synthetic-secret", str(service.events.get_nowait()))

    def test_shutdown_tail_keeps_terminal_state_when_the_normal_queue_is_full(self):
        entered, release = Event(), Event()
        stored = []
        store = Mock()
        def initialize(): entered.set(); release.wait(3)
        store.initialize.side_effect = initialize
        store.save_session.side_effect = lambda value: stored.append(value["status"])
        service = HistoryService(store, queue_size=1)
        self.addCleanup(service.close)
        try:
            service.submit("initialize")
            self.assertTrue(entered.wait(2))
            service.submit("save_session", snapshot(status="running", finished_at=None))
            self.assertFalse(service.close(timeout=0, final_snapshots=[snapshot()]))
        finally:
            release.set()
        self.assertTrue(service.close())
        self.assertEqual(stored, ["running", "completed"])
