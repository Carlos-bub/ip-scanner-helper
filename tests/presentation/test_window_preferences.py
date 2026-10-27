import unittest

from PySide6.QtCore import QRect

from ip_scanner_helper.domain.preferences import WindowPreferences
from ip_scanner_helper.presentation.window_preferences import reachable_geometry


class WindowGeometryTests(unittest.TestCase):
    def test_removed_monitor_recovers_window_on_primary_screen(self):
        screen = QRect(0, 0, 1920, 1040)
        rect = reachable_geometry(WindowPreferences(4500, 10, 1440, 900), [screen])
        self.assertTrue(screen.contains(rect))

    def test_negative_coordinates_are_retained_on_existing_monitor(self):
        left = QRect(-1920, 0, 1920, 1080)
        rect = reachable_geometry(WindowPreferences(-1800, 30, 1440, 900), [QRect(0, 0, 1920, 1080), left])
        self.assertEqual(rect, QRect(-1800, 30, 1440, 900))

    def test_oversized_window_is_clamped_to_work_area(self):
        screen = QRect(0, 0, 1280, 720)
        rect = reachable_geometry(WindowPreferences(200, 100, 4000, 2000), [screen])
        self.assertEqual(rect, screen)
