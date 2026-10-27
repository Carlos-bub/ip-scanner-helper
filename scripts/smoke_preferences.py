"""Exercise preferences, window state and session isolation with local fixtures."""

from dataclasses import replace
from pathlib import Path
from queue import Queue
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import shiboken6

from ip_scanner_helper.bootstrap import create_desktop_services
from ip_scanner_helper.domain.preferences import Preferences, WindowPreferences
from ip_scanner_helper.infrastructure.preferences import JsonPreferencesStore
from ip_scanner_helper.presentation.qt_app import create_window
from ip_scanner_helper.presentation.qt_controller import ScannerController
from ip_scanner_helper.presentation.window_preferences import WindowPreferencesBinding


def main(capture=False):
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        store = JsonPreferencesStore(Path(directory) / "settings.json")
        initial = replace(Preferences(), workers=5, mode="Rápido", target_timeout=8.5,
                          last_target="192.0.2.1", column_widths=(("ip", 205),),
                          window=WindowPreferences(width=1180, height=780))
        store.save(initial)
        service = SimpleNamespace(events=Queue(), start=Mock(return_value="fixture"), cancel=Mock())
        controller = ScannerController(service, create_desktop_services(), auto_discover=False,
                                       preferences=store.load(), preferences_store=store)
        engine, window = create_window(controller)
        geometry = WindowPreferencesBinding(window, initial.window)
        controller.window_preferences = geometry.snapshot

        def item(name):
            result = window.findChild(QObject, name)
            assert result is not None, name
            return result

        def click(name):
            button = item(name)
            point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, pos=point)
            QTest.qWait(120)

        try:
            QTest.qWait(300)
            assert item("workersField").property("text") == "5"
            assert item("targetTimeoutField").property("text") == "8.5"
            assert item("modeBox").property("currentText") == "Rápido"
            table = item("inventoryTable")
            empty = item("inventoryEmptyState")
            center = empty.mapToScene(QPointF(empty.width() / 2, empty.height() / 2))
            expected = table.mapToScene(QPointF(table.width() / 2, table.height() / 2))
            assert abs(center.x() - expected.x()) < 2 and abs(center.y() - expected.y()) < 2
            # Resize through the actual header grip, then rebuild the visible
            # columns. The width belongs to the IP column, not its index.
            header = item("tableHeader")
            point = header.mapToScene(QPointF(203, header.height() / 2)).toPoint()
            QTest.mousePress(window, Qt.LeftButton, pos=point)
            QTest.mouseMove(window, point + QPoint(70, 0), delay=40)
            QTest.mouseRelease(window, Qt.LeftButton, pos=point + QPoint(70, 0))
            QTest.qWait(150)
            resized = controller.table.widths["ip"]
            assert resized > 250, f"Arrastar não redimensionou a coluna: {resized}"
            controller.setColumn("portas", True)
            controller.setColumn("portas", False)
            assert controller.columnWidth(0) == resized
            click("preferencesButton")
            assert item("preferencesDialog").property("visible")
            if capture:
                target = Path(__file__).resolve().parents[1] / "docs" / "desktop-preferences.png"
                assert window.grabWindow().save(str(target))
            item("preferenceWorkers").setProperty("text", "9")
            click("preferencesCancel")
            assert controller.state["workers"] == 5, "Cancelar aplicou o rascunho"
            click("preferencesButton")
            item("preferenceWorkers").setProperty("text", "0")
            click("preferencesSave")
            assert item("preferencesDialog").property("visible"), "Valor inválido foi aceito"
            assert controller.state["workers"] == 5
            item("preferenceWorkers").setProperty("text", "12")
            item("preferenceTimeout").setProperty("text", "7.5")
            click("preferencesSave")
            assert not item("preferencesDialog").property("visible"), controller.state["preferencesError"]
            assert item("workersField").property("text") == "12"
            assert item("targetTimeoutField").property("text") == "7.5"
            controller.startScan("fixture-secret", 12, 7.5)
            captured = service.start.call_args.args[1]
            click("preferencesButton")
            item("preferenceWorkers").setProperty("text", "16")
            click("preferencesSave")
            assert controller.state["scanning"]
            assert captured.workers == 12, "Preferência alterou a sessão ativa"
            assert controller.state["workers"] == 16
            window.resize(1180, 780)
            QTest.qWait(250)
            normal = geometry.snapshot()
            window.showMaximized()
            QTest.qWait(250)
            maximized = geometry.snapshot()
            assert maximized.maximized
            assert (maximized.width, maximized.height) == (normal.width, normal.height)
            controller.close()
            restored = JsonPreferencesStore(store.path).load()
            assert restored.workers == 16
            assert restored.window.maximized
            assert dict(restored.column_widths)["ip"] == resized
            assert "fixture-secret" not in store.path.read_text(encoding="utf-8")
            assert not engine.qml_warnings, "\n".join(engine.qml_warnings)
        finally:
            controller.close()
            window.close()
            shiboken6.delete(engine)
    print("Preferências OK: restauração, cancelar, validação, salvar, sessão ativa e janela maximizada; sem sondas de rede.")


if __name__ == "__main__":
    main("--capture" in sys.argv)
