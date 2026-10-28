from dataclasses import FrozenInstanceError
import unittest

from ip_scanner_helper.domain.preferences import Preferences, WindowPreferences


class PreferencesTests(unittest.TestCase):
    def test_appearance_roundtrip_and_unknown_themes_rejected(self):
        for theme in ("light", "dark", "system"):
            with self.subTest(theme=theme):
                self.assertEqual(Preferences.from_dict(Preferences(theme=theme).to_dict()).theme, theme)
        for theme in (None, True, 1, "cyber", [], {}):
            with self.subTest(theme=theme), self.assertRaises(ValueError):
                Preferences(theme=theme)

    def test_roundtrip_retains_hidden_widths_and_negative_monitor_position(self):
        prefs = Preferences(window=WindowPreferences(-1440, 20, 1200, 800, True),
                            column_widths=(("portas", 411.5),), workers=8, target_timeout=4.5, probe_rate_limit=25)
        restored = Preferences.from_dict(prefs.to_dict())
        self.assertEqual(restored, prefs)
        self.assertEqual(dict(restored.column_widths)["portas"], 411.5)
        self.assertNotIn("portas", restored.visible_columns)

    def test_unknown_fields_and_secrets_are_not_serialized(self):
        prefs = Preferences.from_dict({"community": "secret", "devices": [{"ip": "192.0.2.1"}], "workers": 5})
        self.assertEqual(prefs.workers, 5)
        self.assertNotIn("community", prefs.to_dict())
        self.assertNotIn("devices", prefs.to_dict())

    def test_invalid_settings_are_rejected(self):
        for patch in ({"workers": True}, {"workers": 0}, {"workers": 129}, {"workers": 3.2},
                      {"target_timeout": float("nan")}, {"target_timeout": 301},
                      {"target_timeout": 0}, {"sort_reverse": "false"}, {"mode": "outro"},
                      {"visible_columns": ["inexistente"]}, {"column_widths": {"ip": 99999}},
                      {"window": {"width": 12}}, {"last_target": "a\n"}, {"probe_rate_limit": True},
                      {"probe_rate_limit": -1}, {"probe_rate_limit": 1001}, {"probe_rate_limit": 1.5},
                      {"probe_rate_limit": "10"}, {"probe_rate_limit": float("nan")}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                Preferences.from_dict(patch)

    def test_identity_columns_and_immutable_values(self):
        columns = ["portas"]
        prefs = Preferences(visible_columns=columns)
        columns.append("mac")
        self.assertEqual(prefs.visible_columns, ("ip", "nome", "portas"))
        with self.assertRaises(FrozenInstanceError):
            prefs.workers = 5
