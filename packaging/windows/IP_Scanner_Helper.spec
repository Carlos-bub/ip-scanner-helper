# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import tomllib
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

ROOT = Path(SPECPATH).resolve().parents[1]
PACKAGE = ROOT / 'src' / 'ip_scanner_helper'
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
VERSION_PARTS = (*map(int, VERSION.split('.')), 0)
VERSION_RESOURCE = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION_PARTS, prodvers=VERSION_PARTS,
                      mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('041604b0', [
        StringStruct('FileDescription', 'IP Scanner Helper - Inventário IPv4'),
        StringStruct('FileVersion', VERSION + '.0'),
        StringStruct('InternalName', 'IP_Scanner_Helper'),
        StringStruct('OriginalFilename', 'IP_Scanner_Helper.exe'),
        StringStruct('ProductName', 'IP Scanner Helper'),
        StringStruct('ProductVersion', VERSION),
    ])]), VarFileInfo([VarStruct('Translation', [1046, 1200])])],
)

a = Analysis(
    [str(PACKAGE / '__main__.py')],
    pathex=[str(ROOT / 'src')],
    binaries=[],
    datas=[(str(PACKAGE / 'presentation/assets'), 'ip_scanner_helper/presentation/assets'),
           (str(PACKAGE / 'presentation/qml'), 'ip_scanner_helper/presentation/qml'),
           (str(PACKAGE / 'resources/demo_inventory.json'), 'ip_scanner_helper/resources'),
           (str(PACKAGE / 'resources/templates'), 'ip_scanner_helper/resources/templates'),
           (str(ROOT / 'docs/licenses'), 'licenses'), (str(ROOT / 'THIRD_PARTY_NOTICES.md'), '.')],
    hiddenimports=['PySide6.QtQuick'],
    hookspath=[str(ROOT / 'packaging/windows/hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.QtWebEngineQuick', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
              'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.Qt3DCore',
              'PySide6.QtCharts', 'PySide6.QtGraphs', 'PySide6.QtQuick3D', 'PySide6.QtTest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='IP_Scanner_Helper',
    icon=str(PACKAGE / 'presentation/assets/app.ico'),
    version=VERSION_RESOURCE,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='IP_Scanner_Helper',
)
