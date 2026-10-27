from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ip_scanner_helper.domain.preferences import Preferences
from ip_scanner_helper.infrastructure.preferences import JsonPreferencesStore, MAX_SETTINGS_BYTES


class PreferencesStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "user" / "settings.json"
        self.store = JsonPreferencesStore(self.path)

    def write(self, content):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content, encoding="utf-8")

    def test_constructor_and_missing_load_perform_no_writes(self):
        self.assertFalse(self.path.parent.exists())
        self.assertEqual(self.store.load(), Preferences())
        self.assertFalse(self.path.parent.exists())

    def test_two_instances_restore_only_allowed_preferences(self):
        expected = replace(Preferences(), workers=7, last_target="192.0.2.0/29", interface_name="Conexão")
        self.store.save(expected)
        self.assertEqual(JsonPreferencesStore(self.path).load(), expected)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 4)
        self.assertEqual(set(payload["preferences"]), set(expected.to_dict()))
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_corruption_is_preserved_before_replacement(self):
        for invalid in ("{bad", '[1]', '{"schema_version":true}',
                        '{"schema_version":1,"preferences":{"workers":999}}', "x" * (MAX_SETTINGS_BYTES + 1)):
            with self.subTest(length=len(invalid)):
                self.write(invalid)
                self.assertEqual(self.store.load(), Preferences())
                backup = self.store.recovered_path
                self.assertIsNotNone(backup)
                self.assertEqual(backup.read_text(encoding="utf-8"), invalid)
                self.store.save(Preferences())
                self.assertTrue(backup.exists())

    def test_future_schema_is_preserved_even_when_changed_after_loading(self):
        self.store.save(Preferences())
        self.store.load()
        content = '{"schema_version":42,"preferences":{"future":"value"}}'
        self.write(content)
        with self.assertRaises(PermissionError):
            self.store.save(Preferences())
        self.assertTrue(self.store.read_only)
        self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_failed_atomic_replace_preserves_last_good_file_and_removes_temporary(self):
        self.store.save(Preferences())
        original = self.path.read_bytes()
        with patch("ip_scanner_helper.infrastructure.preferences.os.replace", side_effect=OSError("simulado")):
            with self.assertRaises(OSError):
                self.store.save(replace(Preferences(), workers=9))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_read_error_does_not_overwrite(self):
        self.store.save(Preferences())
        with patch.object(self.store, "_read", side_effect=PermissionError("simulado")):
            self.assertEqual(self.store.load(), Preferences())
            with self.assertRaises(PermissionError):
                self.store.save(Preferences())
        self.assertTrue(self.path.exists())

    def test_schema_one_is_backed_up_exactly_before_migration(self):
        original = '{"schema_version":1,"preferences":{"workers":9,"last_target":"192.0.2.1"}}'
        self.write(original)
        preferences = self.store.load()
        self.assertEqual(preferences.workers, 9)
        self.assertEqual(preferences.port_profile_id, "standard")
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)
        self.store.save(preferences)
        backup = self.store.migration_backup
        self.assertEqual(backup.read_text(encoding="utf-8"), original)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["schema_version"], 4)
        self.assertEqual(JsonPreferencesStore(self.path).load(), preferences)
        self.store.save(preferences)
        self.assertEqual(len(list(self.path.parent.glob("settings.v1-backup-*.json"))), 1)

    def test_migration_backup_failure_preserves_original_schema_one(self):
        original = '{"schema_version":1,"preferences":{"workers":9}}'
        self.write(original)
        preferences = self.store.load()
        real_open = Path.open
        def fail_backup(path, *args, **kwargs):
            if ".v1-backup-" in path.name:
                raise PermissionError("simulado")
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "open", fail_backup):
            with self.assertRaises(OSError):
                self.store.save(preferences)
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_schema_two_migration_keeps_profiles_and_only_persists_credential_reference(self):
        original = '{"schema_version":2,"preferences":{"workers":8,"port_profile_id":"cctv","probe_timeouts":{"snmp":1.2}}}'
        self.write(original)
        preferences = self.store.load()
        self.assertEqual(preferences.port_profile_id, "cctv")
        self.assertEqual(dict(preferences.probe_timeouts)["snmp"], 1.2)
        self.store.save(replace(preferences, credential_id="a" * 32))
        self.assertEqual(self.store.migration_backup.read_text(encoding="utf-8"), original)
        self.assertIn(".v2-backup-", self.store.migration_backup.name)
        self.assertEqual(self.store.load().credential_id, "a" * 32)

    def test_schema_three_migration_preserves_vault_reference_and_defaults_to_unlimited(self):
        original = json.dumps({"schema_version": 3, "preferences": {
            "credential_id": "b" * 32, "port_profile_id": "cctv", "probe_timeouts": {"snmp": 1.5}, "workers": 8}})
        self.write(original)
        preferences = self.store.load()
        self.assertEqual(preferences.probe_rate_limit, 0)
        self.store.save(replace(preferences, probe_rate_limit=40))
        self.assertEqual(self.store.migration_backup.read_text(encoding="utf-8"), original)
        self.assertIn(".v3-backup-", self.store.migration_backup.name)
        restored = JsonPreferencesStore(self.path).load()
        self.assertEqual(restored.probe_rate_limit, 40)
        self.assertEqual(restored.credential_id, "b" * 32)
        self.assertEqual(restored.port_profile_id, "cctv")
        self.assertEqual(dict(restored.probe_timeouts)["snmp"], 1.5)
        self.store.save(restored)
        self.assertEqual(len(list(self.path.parent.glob("settings.v3-backup-*.json"))), 1)

    def test_schema_three_backup_failure_preserves_original_and_no_new_file(self):
        original = '{"schema_version":3,"preferences":{"workers":8}}'
        self.write(original)
        preferences = self.store.load()
        real_open = Path.open

        def fail_backup(path, *args, **kwargs):
            if ".v3-backup-" in path.name:
                raise PermissionError("simulado")
            return real_open(path, *args, **kwargs)

        with patch.object(Path, "open", fail_backup):
            with self.assertRaises(OSError):
                self.store.save(replace(preferences, probe_rate_limit=40))
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)
