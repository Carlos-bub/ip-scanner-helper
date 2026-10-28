"""Exercise native navigation, appearance and draft protection without LAN I/O."""

from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock
import json
from ipaddress import IPv4Address
import sys

from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import shiboken6

from ip_scanner_helper.bootstrap import create_desktop_services
from ip_scanner_helper.domain.preferences import Preferences
from ip_scanner_helper.infrastructure.preferences import JsonPreferencesStore
from ip_scanner_helper.presentation.qt_app import create_window
from ip_scanner_helper.presentation.qt_controller import ScannerController
from ip_scanner_helper.resources import RESOURCE_ROOT

ROOT = Path(__file__).resolve().parents[1]


def main(capture=False):
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as directory:
        store = JsonPreferencesStore(Path(directory) / "settings.json")
        store.save(Preferences())
        network = SimpleNamespace(events=Queue(), start=Mock(return_value="fixture"), cancel=Mock())
        controller = ScannerController(network, create_desktop_services(), auto_discover=False,
                                       preferences=store.load(), preferences_store=store)
        controller.devices = json.loads((RESOURCE_ROOT / "demo_inventory.json").read_text(encoding="utf-8"))
        controller._inventory_gateway = "192.0.2.1"
        controller._refresh()
        engine, window = create_window(controller)

        def item(name):
            found = window.findChild(QObject, name)
            if found is None:
                pending = [window.contentItem()]
                while pending:
                    candidate = pending.pop()
                    if candidate.objectName() == name:
                        found = candidate
                        break
                    pending.extend(candidate.childItems())
            assert found is not None, name
            return found

        def click(name):
            control = item(name)
            assert control.isVisible() and control.isEnabled(), name
            point = control.mapToScene(QPointF(control.width() / 2, control.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, pos=point)
            QTest.qWait(140)

        def value(name, prop):
            result = item(name).property(prop)
            return result.toVariant() if hasattr(result, "toVariant") else result

        def save_image(name):
            if capture:
                assert window.grabWindow().save(str(ROOT / "docs" / name))

        try:
            QTest.qWait(250)
            assert window.property("currentPage") == 0
            assert item("inventoryTable").isVisible()
            primary_text = item("navInventory").property("contentItem").property("color").name()
            assert primary_text == "#ffffff", primary_text
            controller.selectRow(1)
            selection = controller.state["selectedIp"]
            click("navTopology")
            assert window.property("currentPage") == 1
            assert value("topologyPage", "cardCount") > 0
            assert controller.state["selectedIp"] == selection
            old_zoom = value("topologyPage", "zoom")
            click("topologyZoomIn")
            assert value("topologyPage", "zoom") > old_zoom
            click("topologyFit")
            page = item("topologyPage")
            scene = value("topologyPage", "geometry")
            first = next(card for card in scene["cards"] if not card["group"])
            x = (first["x"] + first["width"] / 2) * page.property("zoom") + page.property("panX")
            y = (first["y"] + first["height"] / 2) * page.property("zoom") + page.property("panY")
            canvas = item("topologyCanvas")
            QTest.mouseClick(window, Qt.LeftButton, pos=canvas.mapToScene(QPointF(x, y)).toPoint())
            QTest.qWait(180)
            assert value("topologyPage", "selected")["id"] == first["id"]
            assert canvas.width() >= 320
            click("topologyInspect")
            assert window.property("currentPage") == 0
            assert controller.state["selectedIp"] == first["id"]
            assert controller.state["detailsOpen"]
            controller.closeDetails()
            click("preferencesButton")
            assert window.property("currentPage") == 3
            assert item("preferencesDialog").property("currentTab") == 4
            item("preferenceTheme").setProperty("currentIndex", 1)
            click("navTopology")
            assert item("unsavedSettingsDialog").property("visible")
            assert window.property("currentPage") == 3
            click("settingsKeepEditing")
            assert item("preferenceTheme").property("currentIndex") == 1
            click("navTopology")
            click("settingsDiscard")
            assert window.property("currentPage") == 1
            assert store.load().theme == "light"
            click("preferencesButton")
            item("preferenceTheme").setProperty("currentIndex", 1)
            click("preferencesSave")
            assert window.property("currentPage") == 0
            assert store.load().theme == "dark"
            assert window.property("color").name() == "#12151a"
            assert item("navInventory").property("contentItem").property("color").name() == "#10261e"
            save_image("desktop-navigation-dark.png")
            click("preferencesButton")
            save_image("desktop-settings-central.png")
            item("preferenceTheme").setProperty("currentIndex", 2)
            click("preferencesSave")
            app.styleHints().setColorScheme(Qt.ColorScheme.Light)
            QTest.qWait(150)
            assert window.property("color").name() == "#f4f6f8"
            app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
            QTest.qWait(150)
            assert window.property("color").name() == "#12151a"
            assert store.load().theme == "system"
            # A logical group keeps large inventories compact; its expanded
            # layout can still be fitted, and the canvas stays viewport-sized.
            original = controller.devices
            controller.devices = [{"ip": str(IPv4Address("198.18.0.1") + index), "nome": f"PC{index}",
                                   "tipo": "Estação", "coleta_completa": True} for index in range(4096)]
            controller._refresh()
            click("navTopology")
            assert len(value("topologyPage", "graph")["nodes"]) == 4096
            assert value("topologyPage", "cardCount") == 1
            scene = value("topologyPage", "geometry")
            group = scene["cards"][0]
            x = (group["x"] + group["width"] / 2) * page.property("zoom") + page.property("panX")
            y = (group["y"] + group["height"] / 2) * page.property("zoom") + page.property("panY")
            QTest.mouseClick(window, Qt.LeftButton, pos=canvas.mapToScene(QPointF(x, y)).toPoint())
            QTest.qWait(160)
            assert value("topologyPage", "cardCount") == 4097
            click("topologyFit")
            scene = value("topologyPage", "geometry")
            assert scene["height"] * page.property("zoom") <= canvas.height() + 1
            assert canvas.height() < window.height()
            controller.devices = original
            controller._refresh()
            click("topologyRefresh")
            click("topologyFit")
            for width, height in ((960, 640), (1100, 720), (1440, 900)):
                window.resize(width, height)
                QTest.qWait(150)
                for nav, page_index in (("openHistory", 2), ("preferencesButton", 3), ("navTopology", 1), ("navInventory", 0)):
                    click(nav)
                    assert window.property("currentPage") == page_index
                assert item("inventoryTable").width() > width - 60
            click("navTopology")
            save_image("desktop-topology-native.png")
            click("navInventory")
            click("preferencesButton")
            item("preferenceTheme").setProperty("currentIndex", 0)
            window.close()
            QTest.qWait(150)
            assert window.isVisible() and item("unsavedSettingsDialog").property("visible")
            click("settingsKeepEditing")
            click("preferencesCancel")
            controller.setTarget("192.0.2.1")
            controller.startScan("synthetic-only", 3, 5)
            captured = network.start.call_args.args[1]
            click("preferencesButton")
            click("preferencesTab0")
            item("preferenceWorkers").setProperty("text", "8")
            click("preferencesSave")
            assert captured.workers == 3
            assert controller.state["workers"] == 8
            click("openHistory")
            click("navTopology")
            click("navInventory")
            assert controller.state["scanning"]
            network.start.assert_called_once()
            network.cancel.assert_not_called()
            assert not engine.qml_warnings, "\n".join(engine.qml_warnings)
        finally:
            app.styleHints().unsetColorScheme()
            controller.close()
            window.close()
            shiboken6.delete(engine)
    print("Navegação OK: quatro páginas, estado preservado, rascunhos, temas claro/escuro/sistema, topologia nativa e três tamanhos, sem sondagens.")


if __name__ == "__main__":
    main("--capture" in sys.argv)
