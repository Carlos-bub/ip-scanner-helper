"""Real DPAPI + rendered vault UI; synthetic credentials and mocked scans only."""

import json
import logging
from pathlib import Path
from queue import Queue
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import shiboken6

from ip_scanner_helper.bootstrap import create_desktop_services
from ip_scanner_helper.domain.preferences import Preferences
from ip_scanner_helper.infrastructure.credential_vault import EncryptedCredentialVault
from ip_scanner_helper.infrastructure.logging_config import configure_logging
from ip_scanner_helper.infrastructure.preferences import JsonPreferencesStore
from ip_scanner_helper.infrastructure.windows_dpapi import WindowsDPAPI
from ip_scanner_helper.presentation.qt_app import create_window
from ip_scanner_helper.presentation.qt_controller import ScannerController


def main(capture=False):
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        configure_logging(root / "logs")
        vault = EncryptedCredentialVault(root / "credentials.vault", WindowsDPAPI())
        store = JsonPreferencesStore(root / "settings.json")
        service = SimpleNamespace(events=Queue(), start=Mock(return_value="fixture"), cancel=Mock())
        controller = ScannerController(service, create_desktop_services(), auto_discover=False,
                                       preferences=Preferences(last_target="192.0.2.1"), preferences_store=store,
                                       credential_vault=vault)
        assert not vault.path.exists(), "Listar cofre ausente criou um arquivo"
        secret = "synthetic-" + uuid4().hex
        replacement = "replacement-" + uuid4().hex
        engine, window = create_window(controller)

        def item(name):
            found = window.findChild(QObject, name)
            pending = [window.contentItem()]
            while found is None and pending:
                candidate = pending.pop()
                if candidate.objectName() == name:
                    found = candidate
                pending.extend(candidate.childItems())
            assert found is not None, name
            return found

        def click(name):
            button = item(name)
            point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, pos=point)
            QTest.qWait(100)

        def open_vault():
            click("preferencesButton")
            click("preferencesTab3")

        try:
            QTest.qWait(300)
            open_vault()
            item("vaultName").setProperty("text", "Monitoramento do laboratório")
            item("vaultEnvironment").setProperty("text", "Laboratório fictício")
            item("vaultCommunity").setProperty("text", secret)
            click("vaultSave")
            assert not controller.state["vaultError"], controller.state["vaultError"]
            assert item("vaultCommunity").property("text") == ""
            entries = vault.list_credentials()
            assert len(entries) == 1
            identifier = entries[0]["id"]
            assert secret.encode() not in vault.path.read_bytes()
            assert secret not in str(controller.state)
            click("vaultUse")
            assert controller.state["credentialId"] == identifier
            assert controller.state["environmentName"] == "Laboratório fictício"
            click("preferencesCancel")
            controller.startScan("public", 2)
            captured = service.start.call_args.args[1]
            assert captured.community == secret
            open_vault()
            assert item("vaultCommunity").property("text") == "", "Editar revelou a comunidade"
            item("vaultCommunity").setProperty("text", replacement)
            click("vaultSave")
            assert vault.resolve(identifier).community == replacement
            assert captured.community == secret, "Alterou a credencial da sessão ativa"
            # Blank community edits metadata without erasing the existing secret.
            item("vaultName").setProperty("text", "Monitoramento do laboratório · revisão")
            click("vaultSave")
            assert vault.resolve(identifier).community == replacement
            if capture:
                target = Path(__file__).resolve().parents[1] / "docs" / "desktop-credential-vault.png"
                assert window.grabWindow().save(str(target))
            click("vaultDelete")
            click("vaultDeleteCancel")
            assert len(vault.list_credentials()) == 1
            click("vaultDelete")
            click("vaultDeleteConfirm")
            assert vault.list_credentials() == []
            assert captured.community == secret
            click("preferencesCancel")
            window.resize(960, 640)
            QTest.qWait(150)
            open_vault()
            close = item("preferencesCancel")
            edge = close.mapToScene(QPointF(close.width(), close.height()))
            assert edge.x() <= window.width() and edge.y() <= window.height()
            click("preferencesCancel")
            controller._data["scanning"] = False
            controller.startScan("public", 2)
            assert service.start.call_count == 1, "Credencial removida acionou fallback"
            controller.devices = [{"ip": "192.0.2.1", "nome": "Dispositivo fictício", "mac": "02:00:00:00:00:01"}]
            for kind in ("csv", "json", "html"):
                path = root / ("inventory." + kind)
                controller.export_to(path, kind)
                assert secret not in path.read_text(encoding="utf-8-sig")
                assert replacement not in path.read_text(encoding="utf-8-sig")
            controller.close()
            settings = store.path.read_text(encoding="utf-8")
            assert secret not in settings and replacement not in settings
            assert json.loads(settings)["preferences"]["credential_id"] == identifier
            for handler in logging.getLogger().handlers:
                handler.flush()
            log = (root / "logs" / "scanner.log").read_text(encoding="utf-8")
            assert secret not in log and replacement not in log
            assert not engine.qml_warnings, "\n".join(engine.qml_warnings)
        finally:
            controller.close()
            window.close()
            shiboken6.delete(engine)
            for handler in list(logging.getLogger().handlers):
                handler.close()
                logging.getLogger().removeHandler(handler)
    print("Cofre OK: DPAPI real, criar/editar/excluir, seleção, sessão imutável, janela compacta e ausência de segredos em estado/configurações/logs/exportações.")


if __name__ == "__main__":
    main("--capture" in sys.argv)
