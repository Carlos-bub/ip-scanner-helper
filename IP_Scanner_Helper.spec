# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('ui/assets', 'ui/assets'), ('ui/qml', 'ui/qml'),
           ('docs/licenses', 'licenses'), ('THIRD_PARTY_NOTICES.md', '.')],
    hiddenimports=['PySide6.QtQuick'],
    hookspath=['scripts/pyinstaller_hooks'],
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
    icon='ui/assets/app.ico',
    version='scripts/windows_version.txt',
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
