"""Desktop presentation contracts; all data and service events are local."""

from pathlib import Path
from queue import Queue
import tempfile
import unittest

from PySide6.QtCore import QCoreApplication, QModelIndex, Qt

from core.interfaces import LocalInterface
from core.scan_service import ScanEvent
from ui.qt_controller import ScannerController


class FakeService:
    def __init__(self):
        self.events = Queue()
        self.cancelled = False
        self.options = None

    def start(self, targets, options):
        self.targets, self.options = list(targets), options
        return "current"

    def cancel(self):
        self.cancelled = True


class QtControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.service = FakeService()
        self.controller = ScannerController(demo=True, service=self.service)
        self.addCleanup(self.controller.close)

    def live(self):
        self.controller.demo = False
        self.controller._data["demo"] = False
        return self.controller

    def test_demo_does_not_discover_interfaces_or_start_workers(self):
        c = self.controller
        c.refreshInterfaces()
        c.startScan("public", 32)
        self.assertFalse(c._jobs)
        self.assertIsNone(self.service.options)
        self.assertEqual(c.table.rowCount(), 6)
        self.assertFalse(c.state["detailsOpen"])

    def test_single_selection_keeps_details_closed_and_tracks_ip_through_sort(self):
        c = self.controller
        c.selectRow(1)
        self.assertEqual(c.state["selectedIp"], "192.0.2.10")
        self.assertFalse(c.state["detailsOpen"])
        c.openDetails()
        c.sortColumn(0)
        self.assertTrue(c.state["detailsOpen"])
        self.assertEqual(c.state["selected"]["ip"], "192.0.2.10")
        c.closeDetails()
        self.assertFalse(c.state["detailsOpen"])

    def test_filter_hiding_selection_closes_details(self):
        c = self.controller
        c.selectRow(1)
        c.openDetails()
        c.search("443")
        self.assertEqual(c.table.rowCount(), 2)
        self.assertEqual(c.state["selectedIp"], "")
        self.assertFalse(c.state["detailsOpen"])

    def test_quality_and_category_compose_and_keep_inventory_metrics(self):
        c = self.controller
        c.quality("Sem nome")
        self.assertEqual(c.table.rowCount(), 1)
        self.assertEqual(c.table.records[0]["ip"], "192.0.2.14")
        c.category("Infraestrutura")
        self.assertEqual(c.table.rowCount(), 0)
        self.assertEqual(c.state["deviceCount"], 6)

    def test_required_columns_survive_configuration_and_roles_match_ip(self):
        c = self.controller
        c.setColumn("ip", False)
        c.setColumn("nome", False)
        c.setColumn("portas", True)
        self.assertEqual(c.table.columns[0][0], "ip")
        self.assertEqual(c.table.columns[1][0], "nome")
        index = c.table.index(0, 0)
        self.assertEqual(c.table.data(index), "192.0.2.2")
        self.assertEqual(c.table.data(index, c.table.IpRole), "192.0.2.2")
        self.assertEqual(c.table.data(index, c.table.KeyRole), "ip")
        self.assertIsNone(c.table.data(QModelIndex()))
        self.assertEqual(c.table.headerData(0, Qt.Horizontal), "Endereço IP")

    def test_invalid_target_keeps_previous_inventory_and_shows_notice(self):
        c = self.live()
        notices = []
        c.notice.connect(lambda title, text: notices.append(text))
        c.setTarget("192.168.0.0/8")
        c.startScan("public", 32)
        self.assertIsNone(self.service.options)
        self.assertEqual(c.table.rowCount(), 6)
        self.assertEqual(len(notices), 1)

    def test_scan_options_are_captured_and_results_from_old_sessions_discarded(self):
        c = self.live()
        sample = dict(c.devices[0])
        c.setTarget("192.0.2.1-192.0.2.2")
        c.setMode("Rápido")
        c.startScan(" custom ", 8)
        self.assertEqual(self.service.options.community, "custom")
        self.assertEqual(self.service.options.workers, 8)
        self.assertEqual(self.service.options.mode, "Rápido")
        c.setTarget("192.0.2.99")
        self.assertEqual(c.state["target"], "192.0.2.1-192.0.2.2")
        self.service.events.put(ScanEvent("old", "device", {"device": dict(sample, ip="192.0.2.99")}))
        self.service.events.put(ScanEvent("current", "device", {"device": sample}))
        c.poll()
        self.assertEqual([d["ip"] for d in c.devices], [sample["ip"]])

    def test_interrupted_scan_keeps_real_progress_and_errors(self):
        c = self.live()
        c.startScan("public", 4)
        c.stopScan()
        self.assertTrue(self.service.cancelled)
        self.assertTrue(c.state["stopping"])
        self.service.events.put(ScanEvent("current", "error", {"ip": "192.0.2.2", "message": "Falha simulada"}))
        self.service.events.put(ScanEvent("current", "finished", {"completed": 2, "total": 10, "errors": 1, "cancelled": True}))
        c.poll()
        self.assertFalse(c.state["scanning"])
        self.assertEqual(c.state["progress"], .2)
        self.assertEqual(c.state["errorCount"], 1)
        self.assertEqual(c.state["status"], "Interrompida")
        self.assertIn("Falha simulada", c.state["errorsText"])

    def test_interface_discovery_does_not_overwrite_manually_entered_target(self):
        c = self.live()
        c.setTarget("192.0.2.0/29")
        interface = LocalInterface("Ethernet", "10.0.0.2", 24, "10.0.0.1")
        c._received_interfaces([interface], None)
        self.assertEqual(c.state["target"], "192.0.2.0/29")
        c.selectInterface(0)
        self.assertEqual(c.state["target"], "10.0.0.0/24")

    def test_keyboard_selection_stays_in_bounds(self):
        c = self.controller
        self.assertEqual(c.moveSelection(-1), 0)
        for _ in range(10):
            c.moveSelection(1)
        self.assertEqual(c.state["selectedIp"], "192.0.2.14")
        self.assertFalse(c.state["detailsOpen"])

    def test_stale_auxiliary_completion_is_ignored(self):
        c = self.controller
        applied = []
        c._jobs["switch"] = "new"
        c._completions.put(("switch", "old", lambda *args: applied.append(args), [], None))
        c.poll()
        self.assertFalse(applied)

    def test_switch_collection_keeps_evidence_without_claiming_direct_link(self):
        c = self.live()
        c._data["switchIp"] = "192.0.2.2"
        host = c.devices[1]
        c._received_switch([{"nome": "Gi1/0/1", "status": "Link UP", "macs": [host["mac"]],
                             "hosts": [host], "coleta_parcial": True}], None)
        observation = host["switch_observations"][0]
        self.assertFalse(observation["direct_link_confirmed"])
        self.assertEqual(observation["port"], "Gi1/0/1")
        self.assertIn("parcial", c.state["switchStatus"])
        self.assertEqual(c.state["switchRows"][0]["ip"], host["ip"])

    def test_exports_work_from_filtered_view_and_keep_full_inventory(self):
        c = self.controller
        c.search("IMPRESSORA")
        with tempfile.TemporaryDirectory() as directory:
            for kind in ("csv", "json", "html"):
                path = Path(directory) / f"inventory.{kind}"
                c.export_to(path, kind)
                content = path.read_text(encoding="utf-8-sig")
                self.assertIn("192.0.2.2", content)
                self.assertIn("192.0.2.14", content)
                self.assertNotIn("__GRAPH_DATA__", content)


if __name__ == "__main__":
    unittest.main()
