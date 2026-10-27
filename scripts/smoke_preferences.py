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
            if result is None:
                pending = [window.contentItem()]
                while pending:
                    candidate = pending.pop()
                    if candidate.objectName() == name:
                        result = candidate
                        break
                    pending.extend(candidate.childItems())
            assert result is not None, name
            return result

        def click(name):
            button = item(name)
            point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, pos=point)
            QTest.qWait(120)

        def edit(name, text):
            click(name)
            QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
            for character in text:
                QTest.keyClick(window, Qt.Key(ord(character.upper())))
            QTest.qWait(80)

        def screenshot(name):
            if capture:
                path = Path(__file__).resolve().parents[1] / "docs" / name
                assert window.grabWindow().save(str(path))

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
            click("preferencesTab1")
            click("profileNew")
            item("profileName").setProperty("text", "Aplicações")
            item("profilePorts").setProperty("text", "8088 Minha aplicação\n9000 Serviço interno")
            screenshot("desktop-port-profiles.png")
            click("preferencesTab2")
            edit("timeout_tcp", "0")
            assert item("timeout_tcp").property("text") == "0", "O campo de tempo não recebeu a edição"
            click("preferencesSave")
            assert item("preferencesDialog").property("visible"), "Tempo inválido foi aceito"
            assert controller.state["workers"] == 12, "Rascunho inválido foi aplicado parcialmente"
            edit("timeout_tcp", "0.75")
            edit("timeout_snmp", "1.25")
            screenshot("desktop-probe-timeouts.png")
            click("preferencesSave")
            assert not item("preferencesDialog").property("visible"), controller.state["preferencesError"]
            assert controller.state["scanning"]
            assert captured.workers == 12, "Preferência alterou a sessão ativa"
            assert captured.port_profile.id == "standard"
            assert captured.timeouts.tcp == .2
            assert controller.state["workers"] == 16
            prefs = controller.preferences_snapshot()
            assert prefs.port_profile.tcp_mapping() == {8088: "Minha aplicação", 9000: "Serviço interno"}
            assert dict(prefs.probe_timeouts)["tcp"] == .75
            assert dict(prefs.probe_timeouts)["snmp"] == 1.25
            # Removing a saved custom profile is still a draft until Save.
            click("preferencesButton")
            click("preferencesTab1")
            assert item("profileName").property("text") == "Aplicações"
            click("profileDuplicate")
            assert item("profileName").property("text") == "Aplicações cópia"
            click("profileRemove")
            click("preferencesCancel")
            assert controller.preferences_snapshot().port_profile_id == prefs.port_profile_id
            click("preferencesButton")
            click("preferencesTab1")
            click("profileRemove")
            click("preferencesCancel")
            assert controller.preferences_snapshot().port_profile_id == prefs.port_profile_id
            click("preferencesButton")
            click("preferencesTab2")
            click("resetProbeTimeouts")
            assert item("timeout_tcp").property("text") == "0.2"
            click("preferencesCancel")
            assert dict(controller.preferences_snapshot().probe_timeouts)["tcp"] == .75
            window.resize(960, 640)
            QTest.qWait(150)
            click("preferencesButton")
            for tab in range(3):
                click(f"preferencesTab{tab}")
                save = item("preferencesSave")
                edge = save.mapToScene(QPointF(save.width(), save.height()))
                assert edge.x() <= window.width() and edge.y() <= window.height(), "Rodapé fora da janela compacta"
            click("preferencesCancel")
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
            assert restored.port_profile_id == prefs.port_profile_id
            assert dict(restored.probe_timeouts)["tcp"] == .75
            assert restored.window.maximized
            assert dict(restored.column_widths)["ip"] == resized
            assert "fixture-secret" not in store.path.read_text(encoding="utf-8")
            assert not engine.qml_warnings, "\n".join(engine.qml_warnings)
        finally:
            controller.close()
            window.close()
            shiboken6.delete(engine)
    print("Preferências OK: perfis TCP, duplicar/remover/cancelar, tempos por sonda, validação atômica, sessão ativa, janela compacta e maximizada; sem sondas de rede.")


if __name__ == "__main__":
    main("--capture" in sys.argv)
