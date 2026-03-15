"""E2E test: запуск обеих программ на одном компьютере.

Сценарий:
1. Основная программа (PhotoSelector) следит за workdir/incoming.
2. Камера-симулятор подаёт фото из INBOX в workdir/incoming.
3. PhotoSelector обрабатывает → создаёт листы в workdir/sheets.
4. Приёмник (KanatkaReceiver) следит за workdir/sheets и показывает их.

Всё на localhost, сеть не нужна.

Запуск:
    .venv/Scripts/python.exe tools/e2e_test.py
    .venv/Scripts/python.exe tools/e2e_test.py --fast       # быстрый режим
    .venv/Scripts/python.exe tools/e2e_test.py --headless    # без окон (только консоль)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def ensure_dirs(config: dict) -> None:
    """Создать все рабочие директории."""
    for key, val in config.get("paths", {}).items():
        p = Path(val)
        if not p.is_absolute():
            p = ROOT / val
        p.mkdir(parents=True, exist_ok=True)


def clean_workdir() -> None:
    """Очистить рабочие папки перед тестом."""
    import shutil
    for folder_name in ["incoming", "selected", "sheets", "rejected", "discarded", "archive", "temp"]:
        folder = ROOT / "workdir" / folder_name
        if folder.exists():
            for f in folder.iterdir():
                if f.is_file():
                    f.unlink()
            print(f"  Очищена: {folder.name}/")


def run_camera_simulator(fast: bool = False) -> subprocess.Popen:
    """Запустить симулятор камеры в фоне."""
    cmd = [
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        str(ROOT / "tools" / "camera_simulator.py"),
    ]
    if fast:
        cmd += ["--frame-delay", "0.05", "--series-delay-min", "2", "--series-delay-max", "4"]
    else:
        cmd += ["--frame-delay", "0.2", "--series-delay-min", "5", "--series-delay-max", "8"]

    print(f"  Симулятор камеры: {'быстрый' if fast else 'нормальный'} режим")
    return subprocess.Popen(cmd, cwd=str(ROOT))


def run_main_app_headless() -> subprocess.Popen:
    """Запустить основную обработку (мониторинг incoming) без GUI."""
    cmd = [
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        str(ROOT / "src" / "main.py"),
        "watch",
    ]
    print("  Основная программа: мониторинг incoming/")
    return subprocess.Popen(cmd, cwd=str(ROOT))


def run_main_app_gui() -> subprocess.Popen:
    """Запустить основную программу с окном pywebview."""
    cmd = [
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        str(ROOT / "src" / "app.py"),
    ]
    print("  Основная программа: pywebview (порт 8787)")
    return subprocess.Popen(cmd, cwd=str(ROOT))


def run_receiver(sheets_folder: str) -> subprocess.Popen:
    """Запустить приёмник, указав ему папку с листами."""
    # Записать конфиг приёмника с нужной папкой
    receiver_config = ROOT / "receiver" / "receiver_config.json"
    config_data = {
        "watched_folder": str(sheets_folder),
        "port": 8788,
        "refresh_interval_seconds": 3,
        "thumbnails_per_page": 20,
        "window_title": "Канатка — Приёмник листов",
    }
    receiver_config.write_text(json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        str(ROOT / "receiver" / "receiver_app.py"),
    ]
    print(f"  Приёмник: pywebview (порт 8788), папка: {sheets_folder}")
    return subprocess.Popen(cmd, cwd=str(ROOT))


def monitor_results(sheets_folder: Path, duration: int = 120) -> None:
    """Мониторить появление листов в sheets/."""
    start = time.time()
    seen = set()
    print(f"\n{'='*60}")
    print(f"  Ожидание результатов ({duration} сек макс)...")
    print(f"{'='*60}\n")

    while time.time() - start < duration:
        current = set(sheets_folder.glob("*.jpg")) | set(sheets_folder.glob("*.jpeg"))
        new = current - seen
        for f in sorted(new):
            elapsed = time.time() - start
            print(f"  [{elapsed:5.1f}с] Новый лист: {f.name}")
            seen.update(new)
        time.sleep(1)

    print(f"\n{'='*60}")
    print(f"  Итого листов: {len(seen)}")
    # Подсчёт в других папках
    selected = list((ROOT / "workdir" / "selected").glob("*.jpg"))
    rejected = list((ROOT / "workdir" / "rejected").glob("*.jpg"))
    discarded = list((ROOT / "workdir" / "discarded").glob("*.jpg"))
    print(f"  Отобрано (selected): {len(selected)}")
    print(f"  Отклонено (rejected): {len(rejected)}")
    print(f"  Пустые (discarded): {len(discarded)}")
    print(f"{'='*60}")


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E тест: обе программы на одном компьютере")
    parser.add_argument("--fast", action="store_true", help="Быстрый режим (меньше задержки)")
    parser.add_argument("--headless", action="store_true", help="Без окон pywebview (только консоль)")
    parser.add_argument("--duration", type=int, default=120, help="Длительность теста в секундах (по умолчанию 120)")
    parser.add_argument("--no-clean", action="store_true", help="Не очищать workdir перед тестом")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("  E2E ТЕСТ: PhotoSelector + KanatkaReceiver")
    print(f"{'='*60}\n")

    # Загрузить конфиг
    config_path = ROOT / "src" / "config.json"
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    # Подготовить пути
    sheets_folder = ROOT / config["paths"]["output_sheets"]
    ensure_dirs(config)

    # Очистка
    if not args.no_clean:
        print("Подготовка:")
        clean_workdir()
        print()

    processes: list[subprocess.Popen] = []

    try:
        print("Запуск компонентов:")

        # 1. Основная программа
        if args.headless:
            processes.append(run_main_app_headless())
        else:
            processes.append(run_main_app_gui())

        time.sleep(2)  # дать серверу стартовать

        # 2. Приёмник
        if not args.headless:
            processes.append(run_receiver(str(sheets_folder)))
            time.sleep(1)

        # 3. Симулятор камеры
        sim = run_camera_simulator(fast=args.fast)
        processes.append(sim)

        # 4. Мониторинг результатов
        monitor_results(sheets_folder, duration=args.duration)

    except KeyboardInterrupt:
        print("\n\nОстановка по Ctrl+C...")
    finally:
        print("\nЗавершение процессов...")
        for p in processes:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                p.kill()
        print("Готово.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
