# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

import PySide6

root = Path(SPECPATH)
source = root / "src"
project_root = root.parent
icon = project_root / "src-tauri" / "icons" / "icon.ico"
pyside_dir = Path(PySide6.__file__).parent

# Python 3.13 can ship an older VC runtime than the one bundled with the
# current PySide6 wheel. Put PySide6's matching runtime beside python313.dll
# so Windows does not load the older copy first and fail while importing QtCore.
vc_runtime_names = (
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
)
vc_runtime_binaries = [
    (str(pyside_dir / name), ".")
    for name in vc_runtime_names
    if (pyside_dir / name).is_file()
]

datas = [
    (str(source / "anidesk" / "resources" / "style.qss"), "anidesk/resources"),
    (str(source / "anidesk" / "storage" / "migrations" / "001_initial.sql"), "anidesk/storage/migrations"),
    (str(icon), "resources"),
]

a = Analysis(
    [str(root / "run_anidesk.py")],
    pathex=[str(source)],
    binaries=vc_runtime_binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
    optimize=1,
)

# Qt intentionally uses Windows' system ICU. A developer PATH can contain an
# unrelated Poppler ICU build; if PyInstaller collects that copy, QtCore fails
# at startup with a missing-procedure error on both the build PC and recipients.
system_icu_names = {"icuuc.dll", "icudt78.dll"}
a.binaries = [
    item for item in a.binaries if Path(item[0]).name.lower() not in system_icu_names
]
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
