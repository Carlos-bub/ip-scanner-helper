from queue import Queue
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication

from ip_scanner_helper.domain.credentials import CredentialError, SnmpCredential
from ip_scanner_helper.domain.preferences import Preferences
from ip_scanner_helper.presentation.qt_controller import ScannerController


class MemoryVault:
    def __init__(self):
        self.entries = {"a" * 32: SnmpCredential("a" * 32, "Lab", "fixture-private", "Matriz")}
        self.resolutions = []

    def list_credentials(self):
        return [entry.metadata() for entry in self.entries.values()]

    def resolve(self, identifier):
        self.resolutions.append(identifier)
        if identifier not in self.entries:
            raise CredentialError("A credencial não existe mais.")
        return self.entries[identifier]

    def save_credential(self, identifier, name, community, environment=""):
        identifier = identifier or "b" * 32
        if not community and identifier in self.entries:
            community = self.entries[identifier].community
        self.entries[identifier] = SnmpCredential(identifier, name, community, environment)
        return identifier

    def delete_credential(self, identifier):
        del self.entries[identifier]


class ControllerCredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def make(self, demo=False, remembered=False):
        self.vault = MemoryVault()
        self.service = SimpleNamespace(events=Queue(), start=Mock(return_value="current"), cancel=Mock())
        self.desktop = SimpleNamespace(switch_mapper=SimpleNamespace(mapear_switch=Mock(return_value=[])))
        self.store = SimpleNamespace(save=Mock())
        prefs = Preferences(credential_id="a" * 32 if remembered else "")
        c = ScannerController(self.service, self.desktop, demo=demo, auto_discover=False, preferences=prefs,
                              preferences_store=self.store, credential_vault=self.vault)
        self.addCleanup(c.close)
        c.setTarget("192.0.2.1")
        return c

    def test_explicit_selection_captures_one_secret_and_only_reference_is_persisted(self):
        c = self.make()
        c.selectCredential("a" * 32)
        self.assertEqual(c.state["environmentName"], "Matriz")
        c.startScan("manual-unused", 2)
        options = self.service.start.call_args.args[1]
        self.assertEqual(options.community, "fixture-private")
        self.assertEqual(self.vault.resolutions, ["a" * 32])
        self.assertNotIn("fixture-private", str(c.state))
        self.assertNotIn("fixture-private", str(c.preferencesDraft()))
        c.close()
        saved = self.store.save.call_args.args[0].to_dict()
        self.assertEqual(saved["credential_id"], "a" * 32)
        self.assertNotIn("fixture-private", str(saved))

    def test_restored_reference_does_not_reconfirm_environment_automatically(self):
        c = self.make(remembered=True)
        self.assertEqual(c.state["environmentName"], "")
        c.startScan("public", 2)
        self.service.start.assert_not_called()
        c.selectCredential("a" * 32)
        c.setEnvironmentName("Outra rede")
        c.startScan("public", 2)
        self.service.start.assert_not_called()

    def test_edit_delete_during_scan_keeps_active_options_and_blocks_following_scan(self):
        c = self.make()
        c.selectCredential("a" * 32)
        c.startScan("public", 2)
        active = self.service.start.call_args.args[1]
        c.saveCredential("a" * 32, "Renamed", "replacement", "Matriz")
        self.assertEqual(active.community, "fixture-private")
        self.assertTrue(c.deleteCredential("a" * 32))
        self.assertEqual(active.community, "fixture-private")
        c._data["scanning"] = False
        c.startScan("public", 2)
        self.assertEqual(self.service.start.call_count, 1)
        self.assertEqual(c.state["credentialId"], "a" * 32)

    def test_manual_entry_is_explicit_and_never_reads_vault_secret(self):
        c = self.make()
        c.selectCredential("")
        c.startScan(" manual-community ", 2)
        self.assertEqual(self.service.start.call_args.args[1].community, "manual-community")
        self.assertFalse(self.vault.resolutions)

    def test_demo_stays_isolated_after_test_switches_demo_flag(self):
        c = self.make(demo=True)
        c.demo = False
        self.assertFalse(c.state["vaultEnabled"])
        self.assertEqual(c.saveCredential("", "Lab", "private", ""), "")
        self.assertEqual(len(self.vault.entries), 1)

    def test_mapper_uses_same_selected_credential_without_fallback(self):
        c = self.make()
        c.selectCredential("a" * 32)
        c._selected_ip = "192.0.2.1"
        c._data["selected"] = {"nome": "Lab"}
        c._async = lambda key, operation, callback: operation()
        c.mapSwitch("public")
        self.assertEqual(self.desktop.switch_mapper.mapear_switch.call_args.args[1], "fixture-private")
        c._data["switchBusy"] = False
        self.vault.delete_credential("a" * 32)
        c.mapSwitch("public")
        self.assertEqual(self.desktop.switch_mapper.mapear_switch.call_count, 1)

    def test_vault_failure_is_sanitized_before_ui_and_preferences(self):
        c = self.make()
        self.vault.save_credential = Mock(side_effect=RuntimeError("fixture-private"))
        self.assertEqual(c.saveCredential("", "Lab", "fixture-private", ""), "")
        self.assertNotIn("fixture-private", str(c.state))
