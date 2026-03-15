"""Export utilities: ZIP packing and network sync."""
from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path


def create_results_zip(
    config: dict,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Path:
    """Pack selected photos and sheets into a ZIP file on the Desktop.

    Parameters
    ----------
    config : dict
        Full application config with resolved paths.
    date_from : str, optional
        Start date filter "YYYY-MM-DD". Only files modified on or after this date.
    date_to : str, optional
        End date filter "YYYY-MM-DD". Only files modified on or before this date.

    Returns
    -------
    Path
        Path to the created ZIP file.

    Raises
    ------
    ValueError
        If no files match the criteria.
    """
    selected_dir = Path(config["paths"]["output_selected"])
    sheets_dir = Path(config["paths"]["output_sheets"])

    all_files: list[tuple[str, Path]] = []

    for jpg in selected_dir.glob("*.jpg"):
        if _matches_date_filter(jpg, date_from, date_to):
            all_files.append((f"selected/{jpg.name}", jpg))

    for jpg in sheets_dir.glob("*.jpg"):
        if _matches_date_filter(jpg, date_from, date_to):
            all_files.append((f"sheets/{jpg.name}", jpg))

    if not all_files:
        raise ValueError("Нет файлов для упаковки. Сначала обработайте фото.")

    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path.home()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"kanatka_results_{timestamp}.zip"
    zip_path = desktop / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for archive_name, file_path in all_files:
            zf.write(file_path, archive_name)

    return zip_path


def sync_to_network(source_dir: Path, network_path: str, logger=None) -> int:
    """Copy new .jpg files from source_dir to network_path.

    Only copies files that don't already exist at the destination.
    Never deletes anything.

    Returns the number of files copied.
    """
    target = Path(network_path)
    try:
        if not target.exists():
            if logger:
                logger.warning("Сетевая папка недоступна: %s", network_path)
            return 0
    except OSError:
        if logger:
            logger.warning("Ошибка доступа к сетевой папке: %s", network_path)
        return 0

    copied = 0
    for jpg in source_dir.glob("*.jpg"):
        dest = target / jpg.name
        if not dest.exists():
            try:
                shutil.copy2(jpg, dest)
                copied += 1
            except OSError as exc:
                if logger:
                    logger.warning("Не удалось скопировать %s: %s", jpg.name, exc)
    return copied


def sync_sheets_to_network(config: dict, logger=None) -> int:
    """Convenience wrapper: sync sheets to the configured network path."""
    network_config = config.get("network", {})
    if not network_config.get("auto_sync_sheets", False):
        return 0
    network_path = network_config.get("output_path", "")
    if not network_path:
        return 0

    sheets_dir = Path(config["paths"]["output_sheets"])
    return sync_to_network(sheets_dir, network_path, logger)


def _matches_date_filter(
    file_path: Path,
    date_from: str | None,
    date_to: str | None,
) -> bool:
    """Check if a file's modification date falls within the date range."""
    if not date_from and not date_to:
        return True

    file_date = datetime.fromtimestamp(file_path.stat().st_mtime).date()

    if date_from:
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d").date()
            if file_date < start:
                return False
        except ValueError:
            pass

    if date_to:
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d").date()
            if file_date > end:
                return False
        except ValueError:
            pass

    return True
