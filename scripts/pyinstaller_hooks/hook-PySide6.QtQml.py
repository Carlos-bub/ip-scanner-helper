"""Collect the QML modules actually used by the Basic-style desktop interface.

The upstream hook collects every installed QML plugin, including WebEngine and
3D modules. Keep its dependency checks, then limit the result to our imports.
"""

from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()
root = Path(pyside6_library_info.location["QmlImportsPath"]).resolve()
modules = {
    "QtQml", "QtQml/Models", "QtQml/WorkerScript", "QtQuick", "QtQuick/Window",
    "QtQuick/Layouts", "QtQuick/Templates", "QtQuick/Controls",
    "QtQuick/Controls/Basic", "QtQuick/Controls/Basic/impl", "QtQuick/Controls/impl",
}


def required(entry):
    return Path(entry[0]).resolve().relative_to(root).parent.as_posix() in modules


binaries += [entry for entry in qml_binaries if required(entry)]
datas += [entry for entry in qml_datas if required(entry)]
