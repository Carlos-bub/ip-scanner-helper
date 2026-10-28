"""Exercise the rendered Qt Quick UI with fixtures and real pointer/key input."""

from pathlib import Path
import sys
import time
from threading import Event
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

from PySide6.QtCore import QObject, QPointF, QMetaObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import shiboken6

from ip_scanner_helper.application.scan_service import ScanEvent
from ip_scanner_helper.bootstrap import create_scan_service, create_desktop_services
from ip_scanner_helper.presentation.qt_app import create_window
from ip_scanner_helper.presentation.qt_controller import ScannerController


def main(capture=False):
    app = QApplication.instance() or QApplication([])
    controller = ScannerController(service=create_scan_service(), desktop=create_desktop_services(), demo=True)
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
        with patch("ip_scanner_helper.infrastructure.network.switch_port_mapper.SwitchPortMapper.mapear_switch", return_value=ports):
            controller.mapSwitch("public")
            QMetaObject.invokeMethod(dialog, "open")
            wait_for(lambda: not controller.state["switchBusy"])
            assert len(controller.state["switchRows"]) == 1
            QTest.qWait(100)
            save("desktop-switch.png")
            QMetaObject.invokeMethod(dialog, "close")

        sample = dict(controller.devices[1])
        controller.service = create_scan_service(worker=lambda ip, *args: dict(sample, ip=ip))
        with patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.carregar_arp_cache", return_value={}):
            controller.setTarget("192.0.2.1-192.0.2.3")
            controller.startScan("public", 2)
            wait_for(lambda: not controller.state["scanning"])
        assert controller.table.rowCount() == 3
        assert controller.state["progress"] == 1.0

        # Exercise the actual pipeline in the rendered UI, with every collector
        # replaced. Pause DNS until partial rows are visibly selected.
        entered, release = Event(), Event()
        def slow_dns(*args, **kwargs):
            entered.set()
            release.wait(2)
            return "fixture.example"
        controller.service = create_scan_service()
        with patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.carregar_arp_cache", return_value={}), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.obter_mac_e_presenca_windows", return_value=("02:00:00:00:00:01", True)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.ping_measurement", return_value=(True, 1)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.scan_ports", return_value=[]), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_snmp", return_value=(None, None, None)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_dns_ptr", side_effect=slow_dns), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_netbios", return_value=None):
            controller.setMode("Rápido")
            controller.startScan("public", 3)
            try:
                wait_for(lambda: entered.is_set() and controller.table.rowCount() == 3)
                assert controller.state["completed"] == 0
                assert all(not item["coleta_completa"] for item in controller.devices)
                # rowsInserted updates the Python count before TableView's next
                # polish/render pass; wait for the visible cells before clicking.
                QTest.qWait(120)
                click(table, 40, 23)
                assert controller.state["selectedIp"], (
                    "Partial row was not selectable", table.property("contentX"),
                    table.property("contentY"), engine.qml_warnings)
                QTest.keyClick(window, Qt.Key_Return)
                QTest.qWait(50)
                selected_ip = controller.state["selectedIp"]
                assert panel.isVisible()
            finally:
                release.set()
            wait_for(lambda: not controller.state["scanning"])
        assert controller.table.rowCount() == 3
        assert len(controller.devices) == 3
        assert all(item["coleta_completa"] for item in controller.devices)
        assert controller.state["selectedIp"] == selected_ip
        assert controller.state["selected"]["nome"] == "fixture.example"
        assert panel.isVisible()

        # Real coordinator/scanner deadline, with no network I/O. Keep partial
        # rows and offer the list of limited IPs without turning them into errors.
        def deadline_dns(*args, **kwargs):
            context = kwargs["context"]
            context.cancelled.wait(.04)
            context.check()
            raise AssertionError("The per-IP deadline was not applied")

        controller.service = create_scan_service()
        with patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.carregar_arp_cache", return_value={}), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.obter_mac_e_presenca_windows", return_value=("02:00:00:00:00:01", True)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.ping_measurement", return_value=(False, None)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.scan_ports", return_value=[]), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_snmp", return_value=(None, None, None)), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_dns_ptr", side_effect=deadline_dns), \
             patch("ip_scanner_helper.infrastructure.network.resolver.NetworkResolver.query_netbios", return_value=None):
            controller.startScan("public", 3, .03)
            wait_for(lambda: not controller.state["scanning"])
        assert controller.table.rowCount() == 3
        assert controller.state["limitedCount"] == 3
        assert controller.state["errorCount"] == 0
        assert all(not item["coleta_completa"] for item in controller.devices)
        assert all(item["motivo_coleta_incompleta"] == "tempo" for item in controller.devices)
        window.setWidth(960)
        QTest.qWait(150)
        incomplete_button = window.findChild(QObject, "incompleteButton")
        messages = window.findChild(QObject, "messageDialog")
        assert incomplete_button.isVisible()
        assert incomplete_button.mapToScene(QPointF(incomplete_button.width(), 0)).x() < window.width()
        click(incomplete_button)
        QTest.qWait(80)
        assert messages.property("visible")
        QMetaObject.invokeMethod(messages, "close")
        window.setWidth(1440)
        QTest.qWait(150)

        # Enrich a selected row inside a scrolled inventory, without moving the
        # viewport back to the top or losing the selected IP.
        base = dict(controller.devices[0])
        controller.devices = [dict(base, ip=f"192.0.2.{index}") for index in range(1, 97)]
        controller._refresh()
        QTest.qWait(150)
        table.setProperty("contentY", 46 * 30)
        controller.selectRow(32)
        QTest.qWait(100)
        scroll_before = table.property("contentY")
        assert scroll_before > 1000
        selected_ip = controller.state["selectedIp"]
        controller.service.events.put(ScanEvent(controller._session, "device",
                                               {"device": dict(controller.devices[32], nome="Nome atualizado")}))
        controller.poll()
        QTest.qWait(100)
        assert abs(table.property("contentY") - scroll_before) < 1
        assert controller.state["selectedIp"] == selected_ip
        assert controller.state["selected"]["nome"] == "Nome atualizado"
        assert not engine.qml_warnings, "\n".join(engine.qml_warnings)
    finally:
        controller.close()
        window.close()
        shiboken6.delete(engine)
    print("Qt Quick OK: cliques, teclado, filtros, colunas, 3 larguras, switches, identificação progressiva e limite por IP simulados.")


if __name__ == "__main__":
    main("--capture" in sys.argv)
