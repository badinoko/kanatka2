# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the main PhotoSelector application."""

import sys
from pathlib import Path

project_root = Path(SPECPATH).parent
src_dir = project_root / "src"
models_dir = project_root / "models"

# Find mediapipe site-packages dir to locate libmediapipe.dll
import site
_sp = site.getsitepackages()
_mp_c_dir = None
for _d in _sp:
    _candidate = Path(_d) / "mediapipe" / "tasks" / "c"
    if (_candidate / "libmediapipe.dll").exists():
        _mp_c_dir = _candidate
        break

a = Analysis(
    [str(src_dir / "app.py")],
    pathex=[str(src_dir)],
    binaries=(
        [(str(_mp_c_dir / "libmediapipe.dll"), "mediapipe/tasks/c")] if _mp_c_dir else []
    ),
    datas=[
        (str(src_dir / "config.json"), "."),
        (str(models_dir / "face_landmarker.task"), "models"),
        (str(models_dir / "face_detector.tflite"), "models"),
    ],
    hiddenimports=[
        "mediapipe",
        "mediapipe.python",
        "mediapipe.python._framework_bindings",
        "mediapipe.tasks",
        "mediapipe.tasks.c",
        "mediapipe.tasks.python",
        "mediapipe.tasks.python.core",
        "mediapipe.tasks.python.core.mediapipe_c_bindings",
        "mediapipe.tasks.python.core.mediapipe_c_utils",
        "mediapipe.tasks.python.core.serial_dispatcher",
        "mediapipe.tasks.python.vision",
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
