# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
source = root / "src"
project_root = root.parent
icon = project_root / "src-tauri" / "icons" / "icon.ico"

datas = [
    (str(source / "anidesk" / "resources" / "style.qss"), "anidesk/resources"),
    (str(source / "anidesk" / "storage" / "migrations" / "001_initial.sql"), "anidesk/storage/migrations"),
    (str(icon), "resources"),
]

a = Analysis(
    [str(root / "run_anidesk.py")],
    pathex=[str(source)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AniDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    icon=str(icon),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AniDesk",
)
