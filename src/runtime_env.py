from __future__ import annotations

import os
from pathlib import Path


def prepare_runtime_environment(base_dir: Path | None = None) -> Path:
    project_root = Path(base_dir or Path(__file__).resolve().parents[1])

    mpl_config_dir = Path(os.environ.get("MPLCONFIGDIR", project_root / ".mplconfig"))
    mpl_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(mpl_config_dir)
    return project_root
