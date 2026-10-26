"""Qt application lifecycle and local QML resources."""

import logging
from pathlib import Path
import sys
import shiboken6

from PySide6.QtCore import QTimer, QUrl, QObject
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMessageBox

from core.html_topology import gerar_html_topologia_interativa
from ui.qt_controller import ScannerController

logger = logging.getLogger(__name__)
RESOURCES = Path(__file__).resolve().parent


def create_window(controller):
    QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    warnings = []
    def report_warnings(errors):
        for error in errors:
            warnings.append(error.toString())
            logger.warning("QML: %s", error.toString())
    engine.warnings.connect(report_warnings)
    engine.qml_warnings = warnings
    engine.rootContext().setContextProperty("scanner", controller)
    engine.rootContext().setContextProperty("inventoryModel", controller.table)
    engine.load(QUrl.fromLocalFile(str(RESOURCES / "qml" / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("Não foi possível carregar a interface Qt Quick: " + "\n".join(warnings))
    return engine, engine.rootObjects()[0]


def run(args):
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("IP Scanner Helper")
    app.setOrganizationName("IPScannerHelper")
    app.setWindowIcon(QIcon(str(RESOURCES / "assets" / "app.ico")))
    controller = ScannerController(demo=args.demo or args.self_check)
    try:
        engine, window = create_window(controller)
    except Exception:
        controller.close()
        logger.exception("Falha ao iniciar a interface")
        if not args.self_check:
            QMessageBox.critical(None, "Erro ao iniciar", "Não foi possível carregar a interface. Consulte scanner.log para os detalhes.")
        return 1
    failures = []
    app.aboutToQuit.connect(controller.close)

    def check():
        try:
            if args.self_check:
                assert controller.table.rowCount() == 6, "Inventário de demonstração incompleto"
                assert not controller.state["detailsOpen"], "Detalhes devem iniciar fechados"
                assert window.findChild(QObject, "inventoryTable") is not None, "Tabela não carregou"
                html = gerar_html_topologia_interativa(controller.devices, controller._gateway)
                assert "__GRAPH_DATA__" not in html, "Template HTML incompleto"
                assert not engine.qml_warnings, "Avisos QML: " + "; ".join(engine.qml_warnings)
            if args.screenshot:
                path = Path(args.screenshot).resolve()
                path.parent.mkdir(parents=True, exist_ok=True)
                assert window.grabWindow().save(str(path)), "Não foi possível salvar a captura"
            logger.info("Self-check OK: Qt Quick, inventário, recursos e mapa offline")
        except Exception as exc:
            failures.append(exc)
            logger.exception("Self-check falhou")
        finally:
            if args.self_check:
                app.quit()

    if args.self_check or args.screenshot:
        QTimer.singleShot(1000, check)
    result = app.exec()
    shiboken6.delete(engine)
    return 1 if failures else result
