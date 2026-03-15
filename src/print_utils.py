from __future__ import annotations

import subprocess
from pathlib import Path


def print_sheet(sheet_path: Path, printer_name: str = "") -> bool:
    """Print a sheet image via Windows default printing.

    Uses mspaint /p for simplicity.  Returns True on success.
    If test_mode is handled by the caller, this function is never called.
    """
    path = Path(sheet_path)
    if not path.exists():
        return False
    try:
        cmd = ["mspaint", "/p", str(path)]
        subprocess.Popen(cmd, shell=True)
        return True
    except Exception:
        return False
