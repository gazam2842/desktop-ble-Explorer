# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec — single exe (windowed mode).

Build: .venv/Scripts/pyinstaller --noconfirm ble_explorer.spec
Output: dist/BLE_Explorer_v<version>.exe (version is sourced solely from version.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH)))
from version import __version__  # noqa: E402

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("ui/theme/dark.qss", "ui/theme"),
        ("ui/theme/light.qss", "ui/theme"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "pytest_asyncio"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f"BLE_Explorer_v{__version__}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app — hide the console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
