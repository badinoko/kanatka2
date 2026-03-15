"""Build script for creating PhotoSelector EXE and Windows installer.

Usage:
    python build/build.py                    # Build EXE + installer (default)
    python build/build.py --exe              # Build EXE only
    python build/build.py --installer        # Build Inno Setup installer only (requires EXE)
    python build/build.py --receiver         # Build legacy receiver (optional, not part of standard build)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BUILD_DIR.parent
DIST_DIR = PROJECT_ROOT / "dist"
INSTALLERS_DIR = PROJECT_ROOT / "installers"

def _safe_home() -> Path:
    """Return a stable home path even when Path.home() is unavailable."""
    try:
        return Path.home()
    except RuntimeError:
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            return Path(userprofile)
        homedrive = os.environ.get("HOMEDRIVE", "")
        homepath = os.environ.get("HOMEPATH", "")
        if homedrive and homepath:
            return Path(f"{homedrive}{homepath}")
        return PROJECT_ROOT


# Inno Setup compiler — стандартные пути
ISCC_PATHS = [
    _safe_home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
    Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
]


def find_iscc() -> Path | None:
    """Find Inno Setup compiler."""
    # Check PATH first
    iscc = shutil.which("ISCC")
    if iscc:
        return Path(iscc)
    # Check standard locations
    for p in ISCC_PATHS:
        if p.exists():
            return p
    return None


def build_main() -> bool:
    """Build the main PhotoSelector EXE."""
    print("=" * 60)
    print("Building PhotoSelector...")
    print("=" * 60)
    spec = BUILD_DIR / "kanatka.spec"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR / "work_main"),
        "-y",
        str(spec),
    ]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print("FAILED: PhotoSelector build failed")
        return False
    print("SUCCESS: PhotoSelector built -> dist/PhotoSelector/")
    return True


def build_receiver() -> bool:
    """Build the legacy Receiver EXE (optional, not part of standard build)."""
    print("=" * 60)
    print("Building KanatkaReceiver (legacy/optional)...")
    print("=" * 60)
    spec = BUILD_DIR / "receiver.spec"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR / "work_receiver"),
        "-y",
        str(spec),
    ]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print("FAILED: KanatkaReceiver build failed")
        return False
    print("SUCCESS: KanatkaReceiver built -> dist/KanatkaReceiver/")
    return True


def build_installer() -> bool:
    """Build the PhotoSelector Inno Setup installer."""
    iscc = find_iscc()
    if not iscc:
        print("ERROR: Inno Setup not found!")
        print("Install: winget install JRSoftware.InnoSetup")
        return False

    print(f"Using Inno Setup: {iscc}\n")
    print("=" * 60)
    print("Building installer: PhotoSelector...")
    print("=" * 60)
    iss_path = BUILD_DIR / "photoselector.iss"
    if not iss_path.exists():
        print(f"FAILED: {iss_path} not found")
        return False

    INSTALLERS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [str(iscc), str(iss_path)]
    result = subprocess.run(cmd, cwd=str(BUILD_DIR))
    if result.returncode != 0:
        print("FAILED: PhotoSelector installer build failed")
        return False
    print("SUCCESS: PhotoSelector installer built -> installers/")
    return True


def main():
    parser = argparse.ArgumentParser(description="Build PhotoSelector EXE and installer")
    parser.add_argument("--exe", action="store_true", help="Build PhotoSelector EXE only")
    parser.add_argument("--installer", action="store_true", help="Build Inno Setup installer only")
    parser.add_argument("--receiver", action="store_true", help="Build legacy receiver EXE (optional)")
    args = parser.parse_args()

    # Default: build EXE + installer
    build_all = not args.exe and not args.installer and not args.receiver

    results = []

    if args.exe or build_all:
        results.append(("PhotoSelector EXE", build_main()))

    if args.receiver:
        results.append(("KanatkaReceiver EXE (legacy)", build_receiver()))

    if args.installer or build_all:
        results.append(("PhotoSelector Installer", build_installer()))

    print("\n" + "=" * 60)
    print("Build Summary:")
    for name, ok in results:
        status = "OK" if ok else "FAILED"
        print(f"  {name}: {status}")
    print("=" * 60)

    if not all(ok for _, ok in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
