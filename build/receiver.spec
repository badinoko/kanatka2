# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Receiver application."""

import sys
from pathlib import Path

project_root = Path(SPECPATH).parent
receiver_dir = project_root / "receiver"

a = Analysis(
    [str(receiver_dir / "receiver_app.py")],
    pathex=[str(receiver_dir)],
    binaries=[],
    datas=[
        (str(receiver_dir / "receiver_config.json"), "."),
    ],
    hiddenimports=[
        "PIL",
        "PIL.Image",
        "watchdog",
        "watchdog.observers",
        "watchdog.events",
        "webview",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "cv2", "mediapipe"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KanatkaReceiver",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="KanatkaReceiver",
)
