"""Rendered LLDP/CDP/VLAN dialog checks with synthetic, cancellable collectors."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
import sys
from threading import Event
import time
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import shiboken6

from ip_scanner_helper.bootstrap import create_desktop_services
from ip_scanner_helper.domain.l2 import identity
from ip_scanner_helper.presentation.qt_app import create_window
from ip_scanner_helper.presentation.qt_controller import ScannerController


def sample_result():
    """Addresses are documentation-only and cannot identify a real network."""
    return {
        "schema_version": 1, "observer_ip": "192.0.2.10",
        "source": "SNMP v2c · LLDP/CDP/Q-BRIDGE",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": None, "sys_uptime_ticks": 120000,
        "local_chassis": identity(4, bytes.fromhex("020000000010")),
        "local_system_name": "SW-Distribuição",
        "local_ports": [],
        "neighbors": [
            {"protocol": "LLDP", "row_index": [1000, 24, 1],
             "local_port": {"name": "Gi1/0/24", "if_index": 124,
                            "identity": identity(5, b"Gi1/0/24", port=True)},
             "remote_port": identity(5, b"Gi1/0/48", port=True),
             "remote_chassis": identity(4, bytes.fromhex("020000000020")),
             "remote_name": "SW-Acesso", "management_addresses": ["192.0.2.20"],
             "expires_at": None},
            {"protocol": "CDP", "row_index": [125, 1],
             "local_port": {"name": "Gi1/0/25", "if_index": 125,
                            "identity": identity(5, b"Gi1/0/25", port=True)},
             "remote_port": identity(5, b"Gi0/1", port=True),
             "remote_chassis": identity(7, b"SW-Externo"),
             "remote_name": "SW-Externo", "management_addresses": [], "expires_at": None},
        ],
        "vlan_ports": [
            {"name": "Gi1/0/24", "bridge_port": 7, "if_index": 124,
             "pvid": 10, "tagged": [20, 30], "untagged": [10],
             "egress": [10, 20, 30], "membership_complete": False},
            {"name": "Bridge porta 9", "bridge_port": 9, "if_index": None,
             "pvid": 20, "tagged": [], "untagged": [20],
             "egress": [20], "membership_complete": False},
        ],
        "coverage": {
            "lldp_remote": {"entries": 7, "requests": 2, "reason": "",
                            "unsupported": False, "fallback": False, "partial": False},
            "cdp": {"entries": 6, "requests": 3, "reason": "",
                    "unsupported": False, "fallback": True, "partial": False},
            "pvid": {"entries": 2, "requests": 1, "reason": "",
                     "unsupported": False, "fallback": False, "partial": False},
            "vlan_current": {"entries": 6, "requests": 2, "reason": "limite de entradas",
                             "unsupported": False, "fallback": False, "partial": True},
        },
        "vlan_issues": ["Bridge porta 9: ifIndex não disponível nesta consulta."],
        "partial": True, "cancelled": False,
    }


def main(capture=False):
    app = QApplication.instance() or QApplication([])
    entered = Event()
    collector = Mock(name="SyntheticL2Collector")
    phase = "normal"
    hostile_name = '<b>SW-Hostil</b><img src="https://invalid.example/l2.png">'

    def collect(ip, community, *, context):
        assert ip == "192.0.2.10" and community == "public"
        assert 0 < context.remaining() <= 30
        result = sample_result()
        if phase == "hostile":
            result["neighbors"][0]["remote_name"] = hostile_name
        elif phase == "cancel":
            entered.set()
            assert context.cancelled.wait(5), "Consulta simulada não recebeu cancelamento"
            result["neighbors"] = result["neighbors"][:1]
            result["cancelled"] = True
            result["coverage"]["vlan_current"].update(reason="cancelada", partial=True)
        return result

    collector.collect.side_effect = collect
    service = SimpleNamespace(events=Queue(), start=Mock(), cancel=Mock())
    desktop = replace(create_desktop_services(), l2_collector=collector)
    controller = ScannerController(service, desktop, auto_discover=False)
    controller.devices = [
        {"ip": "192.0.2.10", "nome": "SW-Distribuição", "tipo": "Switch",
         "mac": "02:00:00:00:00:10"},
        {"ip": "192.0.2.20", "nome": "SW-Acesso", "tipo": "Switch",
         "mac": "02:00:00:00:00:20"},
    ]
    controller._inventory_context = {"comparison_scope": "session:l2-smoke"}
    controller._refresh()
    controller.selectRow(0)
    engine, window = create_window(controller)

    def items():
        pending = [window.contentItem()]
        while pending:
            candidate = pending.pop()
            yield candidate
            pending.extend(candidate.childItems())

    def item(name):
        found = window.findChild(QObject, name)
        if found is None:
            found = next((candidate for candidate in items() if candidate.objectName() == name), None)
        assert found is not None, name
        return found

    def text_item(text):
        found = next((candidate for candidate in items()
                      if candidate.isVisible() and candidate.property("text") == text), None)
        assert found is not None, text
        # AppButton's label is a child of the actual input control.
        while found.parentItem() is not None and found.parentItem().property("text") == text:
            found = found.parentItem()
        return found

    def click(target):
        target = item(target) if isinstance(target, str) else target
        assert target.isVisible() and target.isEnabled(), target.objectName()
        point = target.mapToScene(QPointF(target.width() / 2, target.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, pos=point)
        QTest.qWait(100)

    def wait_for(predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(25)
        assert predicate(), "Tempo excedido aguardando a consulta L2 simulada"

    def shown_text():
        return "\n".join(str(candidate.property("text") or "")
                         for candidate in items() if candidate.isVisible())

    def contained(target):
        start = target.mapToScene(QPointF(0, 0))
        end = target.mapToScene(QPointF(target.width(), target.height()))
        assert 0 <= start.x() < end.x() <= window.width() + 1, (start, end)
        assert 0 <= start.y() < end.y() <= window.height() + 1, (start, end)

    try:
        window.resize(1180, 780)
        QTest.qWait(300)
        controller.openDetails()
        QTest.qWait(150)
        click("openL2")
        wait_for(lambda: collector.collect.call_count == 1 and not controller.state["l2Busy"])
        dialog, results = item("l2Dialog"), item("l2Results")
        assert dialog.property("visible")
        assert results.property("count") == 2
        assert "LLDP · Gi1/0/24 → SW-Acesso · Gi1/0/48" in shown_text(), repr(shown_text())
        assert "CDP · Gi1/0/25 → SW-Externo · Gi0/1" in shown_text()
        assert "Relato unilateral" in shown_text()
        assert "Sem correspondência no inventário" in shown_text()
        assert controller.state["l2Status"].startswith("Consulta parcial")
        assert controller.devices[0]["l2_observation"]["network_context"] == controller._inventory_context
        if capture:
            target = Path(__file__).resolve().parents[1] / "docs" / "desktop-l2.png"
            assert window.grabWindow().save(str(target))

        # Network labels must stay literal text, including Qt rich-text syntax.
        # Capture the normal fixture first so documentation keeps readable names.
        phase = "hostile"
        click("refreshL2")
        wait_for(lambda: collector.collect.call_count == 2 and not controller.state["l2Busy"])
        hostile_label = text_item(f"LLDP · Gi1/0/24 → {hostile_name} · Gi1/0/48")
        # PySide cannot convert QQuickText::TextFormat directly; read its numeric
        # value in the rendered object's own QML context instead.
        expression = QQmlExpression(QQmlEngine.contextForObject(hostile_label), hostile_label, "Number(textFormat)")
        text_format = expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        if isinstance(text_format, tuple):
            text_format = text_format[0]
        assert text_format == 0, "Nome SNMP não foi renderizado como Text.PlainText"
        assert hostile_name in shown_text()
        phase = "cancel"

        click(text_item("VLANs por porta"))
        assert results.property("count") == 2
        assert "Gi1/0/24 · Bridge 7 · ifIndex 124 · PVID 10" in shown_text()
        assert "Tagged: 20, 30 (parcial)     Untagged: 10 (parcial)" in shown_text()
        assert "Bridge porta 9 · Bridge 9 · ifIndex Não mapeado · PVID 20" in shown_text()
        click(text_item("Cobertura da consulta"))
        assert results.property("count") == 5
        assert "fallback GETNEXT/redução de lote" in shown_text()
        assert "limite de entradas" in shown_text()
        assert "Bridge porta 9: ifIndex não disponível nesta consulta." in shown_text()

        window.resize(960, 640)
        QTest.qWait(150)
        for page, label in (("neighbors", "Vizinhos"), ("vlans", "VLANs por porta"),
                            ("coverage", "Cobertura da consulta")):
            click(text_item(label))
            assert dialog.property("page") == page
            contained(results)
            contained(item("refreshL2"))
            contained(text_item("Fechar"))

        # The collector runs in a worker; the real button must signal its Event.
        entered.clear()
        click("refreshL2")
        wait_for(lambda: entered.is_set() and controller.state["l2Busy"])
        assert not item("refreshL2").isEnabled()
        contained(item("cancelL2"))
        click("cancelL2")
        wait_for(lambda: not controller.state["l2Busy"])
        assert controller.state["l2Status"].startswith("Consulta interrompida")
        assert len(controller.state["l2Neighbors"]) == 1, "Cancelamento descartou o relato já recebido"
        assert controller.devices[0]["l2_observation"]["cancelled"]

        # Closing the modal also cancels collection and preserves partial data.
        entered.clear()
        click("refreshL2")
        wait_for(lambda: entered.is_set() and controller.state["l2Busy"])
        click(text_item("Fechar"))
        wait_for(lambda: not controller.state["l2Busy"])
        assert not dialog.property("visible")
        assert controller.state["l2Status"].startswith("Consulta interrompida")
        assert collector.collect.call_count == 4
        service.start.assert_not_called()
        assert not engine.qml_warnings, "\n".join(engine.qml_warnings)
    finally:
        controller.cancelL2()
        controller.close()
        window.close()
        shiboken6.delete(engine)
    print("L2 Qt Quick OK: LLDP/CDP, VLANs, cobertura parcial, nomes hostis em PlainText, consulta, cancelamento por botão e fechamento, 960×640 e zero avisos QML; sem acesso à rede.")


if __name__ == "__main__":
    main("--capture" in sys.argv)
