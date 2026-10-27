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
        self.assertEqual(payload["schema_version"], 1)
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
