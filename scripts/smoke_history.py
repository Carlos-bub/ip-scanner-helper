"""Exercise history with a real temporary SQLite database and rendered Qt UI."""
from pathlib import Path
from queue import Queue
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QPointF, Qt, QMetaObject
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
import shiboken6

from ip_scanner_helper.application.history_service import HistoryService
from ip_scanner_helper.bootstrap import create_desktop_services
from ip_scanner_helper.infrastructure.history_store import SqliteHistoryStore
from ip_scanner_helper.presentation.qt_app import create_window
from ip_scanner_helper.presentation.qt_controller import ScannerController
from tests.history_fixtures import snapshot


def main(capture=False):
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as directory:
        store = SqliteHistoryStore(Path(directory) / "inventory.db")
        store.initialize()
        store.save_session(snapshot())
        second = snapshot("session-2", started_at="2026-10-28T12:05:00+00:00", finished_at="2026-10-28T12:05:02+00:00")
        second["devices"][0]["nome"] = "SW-Atualizado"
        second["devices"].append({"ip": "192.0.2.2", "nome": "PC-Laboratório", "tipo": "Estação", "coleta_completa": True})
        store.save_session(second)
        history = HistoryService(store)
        network = Mock(events=Queue())
        controller = ScannerController(network, create_desktop_services(), history_service=history, auto_discover=False)
        engine, window = create_window(controller)

        def wait(predicate, timeout=6):
            deadline = time.monotonic() + timeout
            while not predicate() and time.monotonic() < deadline:
                QTest.qWait(25)
            assert predicate(), controller.history.state

        def item(name):
            found = window.findChild(QObject, name)
            if found is not None:
                return found
            pending = [window.contentItem()]
            while pending:
                candidate = pending.pop()
                if candidate.objectName() == name:
                    return candidate
                pending.extend(candidate.childItems())
            raise AssertionError(name)

        def click(name):
            control = item(name)
            assert control.isVisible() and control.isEnabled(), name
            point = control.mapToScene(QPointF(control.width() / 2, control.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, pos=point)
            QTest.qWait(100)

        def idle():
            return not controller.history.state["busy"] and not controller.history._pending

        try:
            window.resize(1180, 780)
            QTest.qWait(200)
            wait(idle)
            click("openHistory")
            wait(lambda: idle() and len(controller.history.state["sessions"]) == 2)
            click("historySession:session-2")
            wait(lambda: idle() and controller.history.state["selectedId"] == "session-2")
            ids = controller.history.state["compareIds"]
            item("historyBaseline").setProperty("currentIndex", ids.index("session-1"))
            click("historyCompare")
            wait(lambda: idle() and len(controller.history.state["diffRows"]) == 2)
            assert {row["kind"] for row in controller.history.state["diffRows"]} == {"name", "new"}
            if capture:
                assert window.grabWindow().save(str(ROOT / "docs/desktop-history.png"))
            click("historyAddresses")
            wait(lambda: idle() and len(controller.history.state["addressRows"]) == 3)
            click("historyHeatmapMode")
            assert item("historyHeatmap").isVisible()
            assert item("historyHeatmap").property("count") == 3
            tile = item("historyAddressTile:192.0.2.1")
            assert tile.isVisible() and tile.width() > 40 and tile.height() > 30
            grid = item("historyHeatmap")
            assert grid.width() > 300 and grid.height() > 60, (grid.width(), grid.height())
            QTest.qWait(80)  # Wait for the first rendered frame of the new cells.
            assert {row["stateCode"] for row in controller.history.state["addressRows"]} == {"observed", "no_response"}
            if capture:
                assert window.grabWindow().save(str(ROOT / "docs/desktop-ipam-heatmap.png"))
            click("historyListMode")
            item("historyReservationIp").setProperty("text", "192.0.2.3")
            item("historyReservationLabel").setProperty("text", "Reserva de teste")
            item("historyReservationTags").setProperty("text", "TI, Laboratório")
            click("historyReservationSave")
            wait(lambda: idle() and controller.history.state["addressRows"][2]["reserved"])
            backup = Path(directory) / "backup.sqlite"
            with patch("ip_scanner_helper.presentation.history_controller.QFileDialog.getSaveFileName", return_value=(str(backup), "")):
                click("historyBackup")
                wait(lambda: idle() and backup.is_file())
            QMetaObject.invokeMethod(item("messageDialog"), "close")
            QTest.qWait(100)
            store.save_session(snapshot("session-3"))
            with patch("ip_scanner_helper.presentation.history_controller.QFileDialog.getOpenFileName", return_value=(str(backup), "")), \
                 patch("ip_scanner_helper.presentation.history_controller.QMessageBox.question", return_value=QMessageBox.Yes):
                click("historyRestore")
                wait(lambda: idle() and len(controller.history.state["sessions"]) == 2, timeout=25)
            assert store.load_session("session-3") is None
            QMetaObject.invokeMethod(item("messageDialog"), "close")
            QTest.qWait(100)
            assert store.restore_backup.is_file()
            assert len(store.list_reservations("lab-a")) == 1
            click("historySession:session-2")
            wait(idle)
            window.resize(960, 640)
            QTest.qWait(150)
            for name in ("historyClose", "historyLoad", "historyBackup", "historyRestore"):
                control = item(name)
                start = control.mapToScene(QPointF(0, 0))
                end = control.mapToScene(QPointF(control.width(), control.height()))
                assert 0 <= start.x() <= end.x() <= 961, (name, start, end)
                assert 0 <= start.y() <= end.y() <= 641, (name, start, end)
            click("historyLoad")
            assert controller.table.rowCount() == 2
            assert controller.state["viewMode"] == "history"
            assert controller.devices[1]["tipo"] == "Estação"
            network.start.assert_not_called()
            assert not engine.qml_warnings, engine.qml_warnings
        finally:
            controller.close()
            history.close()
            window.close()
            shiboken6.delete(engine)
        reopened = SqliteHistoryStore(store.path)
        reopened.initialize()
        assert len(reopened.list_sessions()) == 2
        assert len(reopened.list_reservations("lab-a")) == 1
    print("Histórico OK: SQLite temporário, comparação, mapa de endereços, reservas, backup/restauração, abertura offline, 960x640 e zero avisos QML; sem rede.")


if __name__ == "__main__":
    main(capture="--capture" in sys.argv)
