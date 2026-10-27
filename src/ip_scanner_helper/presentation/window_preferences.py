"""Restore reachable window bounds and remember the last normal rectangle."""

from PySide6.QtCore import QObject, QRect, QTimer
from PySide6.QtGui import QGuiApplication, QWindow

from ip_scanner_helper.domain.preferences import WindowPreferences


def reachable_geometry(preferences, screens):
    """Keep a saved position on its screen; recover when a monitor disappeared."""
    screens = list(screens)
    if not screens:
        return QRect(preferences.x or 0, preferences.y or 0, preferences.width, preferences.height)
    proposed = QRect(preferences.x or 0, preferences.y or 0, preferences.width, preferences.height)
    screen = max(screens, key=lambda area: area.intersected(proposed).width() * area.intersected(proposed).height())
    if preferences.x is None or preferences.y is None or not screen.intersects(proposed):
        screen = screens[0]
        x, y = screen.x() + (screen.width() - min(preferences.width, screen.width())) // 2, screen.y() + 30
    else:
        x, y = preferences.x, preferences.y
    width = max(960, min(preferences.width, screen.width()))
    height = max(640, min(preferences.height, screen.height()))
    x = max(screen.x(), min(x, screen.right() - width + 1))
    y = max(screen.y(), min(y, screen.bottom() - height + 1))
    return QRect(x, y, width, height)


class WindowPreferencesBinding(QObject):
    def __init__(self, window, preferences):
        super().__init__(window)
        self.window = window
        self._normal = reachable_geometry(preferences, [s.availableGeometry() for s in QGuiApplication.screens()])
        self._maximized = preferences.maximized
        window.setGeometry(self._normal)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._capture)
        for signal in (window.xChanged, window.yChanged, window.widthChanged, window.heightChanged):
            signal.connect(lambda *_: self.timer.start())
        window.visibilityChanged.connect(self._visibility)
        if preferences.maximized:
            window.showMaximized()

    def _visibility(self, visibility):
        if visibility == QWindow.Visibility.Maximized:
            self._maximized = True
        elif visibility == QWindow.Visibility.Windowed:
            self._maximized = False
            self.timer.start()

    def _capture(self):
        if self.window.visibility() == QWindow.Visibility.Windowed:
            self._normal = self.window.geometry()

    def snapshot(self):
        self._capture()
        rect = self._normal
        return WindowPreferences(rect.x(), rect.y(), max(960, rect.width()), max(640, rect.height()), self._maximized)
