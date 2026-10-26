"""Exercise the rendered Qt Quick UI with fixtures and real pointer/key input."""

from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QPointF, QMetaObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import shiboken6

from core.scan_service import ScanService
from ui.qt_app import create_window
from ui.qt_controller import ScannerController


def main(capture=False):
    app = QApplication.instance() or QApplication([])
    controller = ScannerController(demo=True)
    engine, window = create_window(controller)
    table = window.findChild(QObject, "inventoryTable")
    panel = window.findChild(QObject, "detailPanel")
    search = window.findChild(QObject, "searchField")
    details = window.findChild(QObject, "detailsButton")
    dialog = window.findChild(QObject, "switchDialog")
    options = window.findChild(QObject, "optionsButton")
    advanced = window.findChild(QObject, "advancedOptions")
    category = window.findChild(QObject, "categoryCombo")

    def click(item, x=None, y=None, double=False):
        point = item.mapToScene(QPointF(x if x is not None else item.width() / 2,
                                       y if y is not None else item.height() / 2)).toPoint()
        if double:
            QTest.mouseDClick(window, Qt.LeftButton, pos=point)
        else:
            QTest.mouseClick(window, Qt.LeftButton, pos=point)
        QTest.qWait(120)

    def wait_for(predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(25)
        assert predicate(), "Tempo excedido aguardando tarefa simulada"

    def save(name):
        if capture:
            assert window.grabWindow().save(str(ROOT / "docs" / name))

    try:
        QTest.qWait(400)
        assert controller.table.rowCount() == 6
        assert not panel.isVisible()
        click(table, 40, 23)
        assert controller.state["selectedIp"] == "192.0.2.2"
        assert not panel.isVisible(), "Seleção simples abriu detalhes"
        save("desktop-demo.png")
        click(details)
        assert panel.isVisible()
        save("desktop-details.png")
        click(details)
        assert not panel.isVisible()
        # Keyboard navigation and manual details must reach the same selected IP.
        click(table, 40, 23)
        QTest.keyClick(window, Qt.Key_Down)
        QTest.keyClick(window, Qt.Key_Return)
        QTest.qWait(100)
        assert controller.state["selectedIp"] == "192.0.2.10"
        assert panel.isVisible()
        search.setProperty("text", "443")
        QTest.qWait(100)
        assert controller.table.rowCount() == 2
        assert not panel.isVisible(), "Detalhes não fecharam ao ocultar seleção"
        search.setProperty("text", "")
        QTest.qWait(100)
        click(table, 40, 23, double=True)
        assert panel.isVisible(), "Duplo clique não abriu os detalhes"
        controller.closeDetails()
        controller.setColumn("portas", True)
        QTest.qWait(100)
        assert controller.table.columnCount() == 8
        controller.setColumn("portas", False)

        for width, height in ((960, 640), (1100, 720), (1440, 900)):
            window.resize(width, height)
            QTest.qWait(150)
            assert table.width() > width - 60
            if width == 960:
                save("desktop-compact.png")
                click(options)
                assert advanced.isVisible()
                click(options)
                assert not advanced.isVisible()
            controller.openDetails()
            QTest.qWait(150)
            assert details.mapToScene(QPointF(details.width(), 0)).x() < panel.x()
            assert table.width() > 500
            if width == 960:
                save("desktop-compact-details.png")
            controller.closeDetails()

        # Instantiate popup delegates as well as the closed controls.
        click(category)
        QTest.keyClick(window, Qt.Key_Escape)
        popup = window.findChild(QObject, "columnsPopup")
        QMetaObject.invokeMethod(popup, "open")
        QTest.qWait(100)
        QMetaObject.invokeMethod(popup, "close")

        # No actual network collector is used; auxiliary jobs still cross threads.
        controller.demo = False
        controller._data["demo"] = False
        controller.selectRow(0)
        host = controller.devices[1]
        ports = [{"nome": "Gi1/0/1", "status": "Link UP", "macs": [host["mac"]],
                  "hosts": [host], "coleta_parcial": False}]
        with patch("ui.qt_controller.SwitchPortMapper.mapear_switch", return_value=ports):
            controller.mapSwitch("public")
            QMetaObject.invokeMethod(dialog, "open")
            wait_for(lambda: not controller.state["switchBusy"])
            assert len(controller.state["switchRows"]) == 1
            QTest.qWait(100)
            save("desktop-switch.png")
            QMetaObject.invokeMethod(dialog, "close")

        sample = dict(controller.devices[1])
        controller.service = ScanService(worker=lambda ip, *args: dict(sample, ip=ip))
        with patch("core.scan_service.NetworkResolver.carregar_arp_cache", return_value={}):
            controller.setTarget("192.0.2.1-192.0.2.3")
            controller.startScan("public", 2)
            wait_for(lambda: not controller.state["scanning"])
        assert controller.table.rowCount() == 3
        assert controller.state["progress"] == 1.0
        assert not engine.qml_warnings, "\n".join(engine.qml_warnings)
    finally:
        controller.close()
        window.close()
        shiboken6.delete(engine)
    print("Qt Quick OK: cliques, teclado, filtros, colunas, 3 larguras, switches e varredura simulada.")


if __name__ == "__main__":
    main("--capture" in sys.argv)
