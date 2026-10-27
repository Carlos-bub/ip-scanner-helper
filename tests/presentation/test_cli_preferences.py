import unittest
from unittest.mock import patch

from ip_scanner_helper.cli import main


class CliPreferencesTests(unittest.TestCase):
    def invoke(self, arguments):
        with patch("ip_scanner_helper.cli.configure_logging"), \
             patch("ip_scanner_helper.cli.create_scan_service"), \
             patch("ip_scanner_helper.cli.create_desktop_services"), \
             patch("ip_scanner_helper.cli.create_preferences_store") as factory, \
             patch("ip_scanner_helper.presentation.qt_app.run", return_value=0) as run:
            self.assertEqual(main(arguments), 0)
            return factory, run

    def test_demo_and_self_check_do_not_construct_personal_preferences_store(self):
        for flag in ("--demo", "--self-check"):
            with self.subTest(flag=flag):
                factory, run = self.invoke([flag])
                factory.assert_not_called()
                self.assertIsNone(run.call_args.kwargs["preferences_store"])

    def test_regular_app_receives_store_from_composition_root(self):
        factory, run = self.invoke([])
        factory.assert_called_once_with()
        self.assertIs(run.call_args.kwargs["preferences_store"], factory.return_value)
