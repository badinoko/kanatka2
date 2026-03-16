# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the main PhotoSelector application."""

import sys
from pathlib import Path

project_root = Path(SPECPATH).parent
src_dir = project_root / "src"
models_dir = project_root / "models"

a = Analysis(
    [str(src_dir / "app.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[
        (str(src_dir / "config.json"), "."),
        (str(models_dir / "face_landmarker.task"), "models"),
        (str(models_dir / "face_detector.tflite"), "models"),
    ],
    hiddenimports=[
        "mediapipe",
        "mediapipe.python",
        "mediapipe.python._framework_bindings",
        "cv2",
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
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhotoSelector",
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
    name="PhotoSelector",
)
