from dataclasses import replace
from queue import Queue
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication

from ip_scanner_helper.application.scan_service import ScanEvent
from ip_scanner_helper.domain.interfaces import LocalInterface
from ip_scanner_helper.domain.preferences import Preferences
from ip_scanner_helper.presentation.qt_controller import ScannerController


class DesktopPreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def controller(self, preferences=None, demo=False):
        service = SimpleNamespace(events=Queue(), start=Mock(return_value="session"), cancel=Mock())
        store = SimpleNamespace(save=Mock(), read_only=False, message="")
        desktop = SimpleNamespace(render_map=Mock(return_value="map"))
        c = ScannerController(service, desktop, demo=demo, auto_discover=False,
                              preferences=preferences, preferences_store=store)
        self.addCleanup(c.close)
        return c, service, store

    def test_all_basic_preferences_restore_and_survive_hidden_columns(self):
        prefs = replace(Preferences(), visible_columns=("ip", "nome", "portas"),
                        column_widths=(("mac", 233),), sort_key="nome", sort_reverse=True,
                        last_target="192.0.2.0/29", mode="Rápido", workers=6, target_timeout=9)
        c, _, store = self.controller(prefs)
        self.assertEqual(c.state["target"], prefs.last_target)
        self.assertEqual(c.state["mode"], "Rápido")
        self.assertEqual(c.state["workers"], 6)
        self.assertTrue(c.state["sortReverse"])
        c.setColumn("mac", True)
        self.assertEqual(next(item[2] for item in c.table.columns if item[0] == "mac"), 233)
        c.resizeColumn(0, 201)
        c.close()
        saved = store.save.call_args.args[0]
        self.assertEqual(dict(saved.column_widths)["ip"], 201)
        self.assertEqual(saved.sort_key, "nome")

    def test_preferences_during_scan_only_change_next_scan_and_no_secrets_are_saved(self):
        c, service, store = self.controller()
        c.setTarget("192.0.2.1")
        c.setEnvironmentName("Matriz")
        c.startScan("private community", 4, 6)
        captured = service.start.call_args.args[1]
        self.assertTrue(c.applyPreferences({"workers": 8, "mode": "Rápido", "target_timeout": 40}))
        self.assertEqual(captured.workers, 4)
        self.assertEqual(captured.mode, "Completo")
        self.assertEqual(captured.timeouts.target_s, 6)
        self.assertEqual(captured.network_context.environment_label, "Matriz")
        self.assertEqual(c.state["workers"], 8)
        saved = store.save.call_args.args[0].to_dict()
        self.assertNotIn("private community", str(saved))
        self.assertNotIn("Matriz", str(saved))
        self.assertEqual(saved["workers"], 8)

    def test_invalid_preferences_do_not_partially_apply(self):
        c, _, store = self.controller()
        self.assertFalse(c.applyPreferences({"workers": 0, "mode": "Rápido"}))
        self.assertEqual(c.state["mode"], "Completo")
        self.assertEqual(c.state["workers"], 32)
        store.save.assert_not_called()

    def test_qml_integral_numbers_are_normalized_without_accepting_fractions(self):
        c, _, _ = self.controller()
        self.assertTrue(c.applyPreferences({"workers": 12.0}))
        self.assertEqual(c.state["workers"], 12)
        self.assertFalse(c.applyPreferences({"workers": 12.5}))
        self.assertEqual(c.state["workers"], 12)

    def test_demo_cannot_write_even_when_later_toggled_by_smoke_test(self):
        c, _, store = self.controller(demo=True)
        c.demo = False
        c.setColumn("portas", True)
        c.applyPreferences({"workers": 5})
        c.close()
        store.save.assert_not_called()

    def test_remembered_adapter_restores_without_overwriting_manual_target(self):
        prefs = replace(Preferences(), interface_id="adapter-2", interface_name="Old name", last_target="192.0.2.1")
        c, _, _ = self.controller(prefs)
        interfaces = [LocalInterface("Ethernet", "10.0.0.2", 24, "10.0.0.1", "adapter-1"),
                      LocalInterface("Renamed", "10.1.0.2", 24, "10.1.0.1", "adapter-2")]
        c._received_interfaces(interfaces, None)
        self.assertEqual(c.state["interfaceIndex"], 1)
        self.assertEqual(c.state["target"], "192.0.2.1")
        c._received_interfaces(interfaces[:1], None)
        self.assertEqual(c.state["interfaceIndex"], -1)
        self.assertIsNone(c._gateway)

    def test_changing_interface_after_collection_keeps_inventory_gateway_and_context(self):
        c, service, _ = self.controller()
        interfaces = [LocalInterface("One", "192.0.2.2", 29, "192.0.2.1", "one"),
                      LocalInterface("Two", "198.51.100.2", 29, "198.51.100.1", "two")]
        c._received_interfaces(interfaces, None)
        c.startScan("public", 2)
        snapshot = c.state["networkContext"]
        service.events.put(ScanEvent("session", "finished", {"completed": 6, "total": 6, "errors": 0, "cancelled": False}))
        c.poll()
        c.selectInterface(1)
        self.assertEqual(c.state["networkContext"], snapshot)
        self.assertEqual(c._inventory_gateway, "192.0.2.1")
        self.assertEqual(c._gateway, "198.51.100.1")

    def test_manual_target_does_not_inherit_arbitrary_first_adapter(self):
        c, service, _ = self.controller()
        c.setTarget("192.0.2.1")
        c._received_interfaces([LocalInterface("One", "10.0.0.2", 24, "10.0.0.1")], None)
        self.assertEqual(c.state["interfaceIndex"], -1)
        c.startScan("public", 2)
        self.assertIsNone(service.start.call_args.args[1].network_context.interface_address)

    def test_write_failure_reports_problem_without_breaking_collection(self):
        c, _, store = self.controller()
        store.save.side_effect = OSError("simulado")
        self.assertFalse(c.applyPreferences({"workers": 8}))
        self.assertIn("salvar", c.state["preferencesError"])
        c.setTarget("192.0.2.1")
        c.startScan("public", 2)
        self.assertTrue(c.state["scanning"])
