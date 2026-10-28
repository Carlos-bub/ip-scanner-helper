from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication

from ip_scanner_helper.application.history_service import HistoryService
from ip_scanner_helper.application.scan_service import ScanEvent
from ip_scanner_helper.bootstrap import create_desktop_services
from ip_scanner_helper.infrastructure.history_store import SqliteHistoryStore
from ip_scanner_helper.presentation.qt_controller import ScannerController
from tests.history_fixtures import snapshot


class HistoryControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SqliteHistoryStore(Path(self.directory.name) / "inventory.db")
        self.history = HistoryService(self.store)
        self.addCleanup(self.history.close)
        self.scan = Mock(events=Queue())
        self.scan.start.return_value = "live"
        self.controller = ScannerController(self.scan, create_desktop_services(), history_service=self.history, auto_discover=False)
        self.addCleanup(self.controller.close)
        self.wait(lambda: not self.controller.history._pending)

    def wait(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_scan_completion_is_saved_with_options_context_and_no_secret(self):
        c = self.controller
        c.setTarget("192.0.2.1-192.0.2.3")
        c.startScan("fixture-private-community", 2)
        self.scan.events.put(ScanEvent("live", "device", {"device": snapshot()["devices"][0]}))
        self.scan.events.put(ScanEvent("live", "finished", {"completed": 3, "total": 3, "errors": 0, "cancelled": False}))
        c.poll()
        self.wait(lambda: not c.history._pending)
        value = self.store.load_session("live")
        self.assertEqual(value["status"], "completed")
        self.assertEqual(value["options"]["workers"], 2)
        self.assertEqual(value["devices"][0]["nome"], "SW-A")
        self.assertNotIn("fixture-private-community", str(value))

    def test_close_records_active_scan_as_interrupted_and_preserves_observation(self):
        c = self.controller
        c.setTarget("192.0.2.1-192.0.2.3")
        c.startScan("public", 2)
        self.scan.events.put(ScanEvent("live", "device", {"device": snapshot()["devices"][0]}))
        c.poll()
        c.close()
        value = self.store.load_session("live")
        self.assertEqual(value["status"], "interrupted")
        self.assertEqual(len(value["devices"]), 1)

    def test_loading_is_offline_and_keeps_the_saved_category_and_context(self):
        c = self.controller
        value = snapshot()
        value["devices"][0]["tipo"] = "Categoria produzida externamente"
        self.store.save_session(value)
        c.history.selectSession(value["id"])
        self.wait(lambda: not c.history._pending)
        c.history.loadSelected()
        self.assertEqual(c.devices[0]["tipo"], "Categoria produzida externamente")
        self.assertEqual(c.state["viewMode"], "history")
        self.assertEqual(c._inventory_context["environment_id"], "lab-a")
        self.scan.start.assert_not_called()

    def test_reservations_and_comparison_use_selected_session(self):
        c = self.controller
        self.store.save_session(snapshot())
        second = snapshot("session-2")
        second["devices"][0]["nome"] = "SW-B"
        self.store.save_session(second)
        c.history.selectSession("session-2")
        self.wait(lambda: not c.history._pending)
        c.history.compareSelected("session-1")
        self.wait(lambda: not c.history._pending)
        self.assertEqual(c.history.state["diffRows"][0]["kind"], "name")
        c.history.saveReservation("192.0.2.2", "Impressora", "TI, Andar 1")
        self.wait(lambda: not c.history._pending)
        self.assertEqual(c.history.state["addressRows"][1]["state"], "Reservado manualmente")

    def test_individual_failed_target_is_persisted_as_inconclusive(self):
        c = self.controller
        c.setTarget("192.0.2.1-192.0.2.3")
        c.startScan("public", 2)
        self.scan.events.put(ScanEvent("live", "error", {"ip": "192.0.2.2", "message": "Erro simulado"}))
        self.scan.events.put(ScanEvent("live", "finished", {"completed": 3, "total": 3, "errors": 1, "cancelled": False}))
        c.poll()
        self.wait(lambda: not c.history._pending)
        value = self.store.load_session("live")
        self.assertEqual(value["status"], "failed")
        self.assertEqual(value["incomplete_targets"][0]["outcome"], "error")
        self.assertEqual(value["coverage"]["limited_targets"], 0)
