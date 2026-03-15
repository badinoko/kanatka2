"""Build script for creating EXE distributions and Windows installers.

Usage:
    python build/build.py                    # Build both EXEs + both installers
    python build/build.py --main             # Build main app EXE only
    python build/build.py --receiver         # Build receiver EXE only
    python build/build.py --installers       # Build Inno Setup installers only (requires EXEs)
    python build/build.py --all              # Build everything
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BUILD_DIR.parent
DIST_DIR = PROJECT_ROOT / "dist"
INSTALLERS_DIR = PROJECT_ROOT / "installers"

# Inno Setup compiler — стандартные пути
ISCC_PATHS = [
    Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
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
    print("Building PhotoSelector (main app)...")
    print("=" * 60)
    spec = BUILD_DIR / "kanatka.spec"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR / "work_main"),
        str(spec),
    ]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print("FAILED: PhotoSelector build failed")
        return False
    print("SUCCESS: PhotoSelector built -> dist/PhotoSelector/")
    return True


def build_receiver() -> bool:
    """Build the Receiver EXE."""
    print("=" * 60)
    print("Building KanatkaReceiver...")
    print("=" * 60)
    spec = BUILD_DIR / "receiver.spec"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR / "work_receiver"),
        str(spec),
    ]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print("FAILED: KanatkaReceiver build failed")
        return False
    print("SUCCESS: KanatkaReceiver built -> dist/KanatkaReceiver/")
    return True


def build_installer(name: str, iss_file: str, iscc: Path) -> bool:
    """Build a single Inno Setup installer."""
    print("=" * 60)
    print(f"Building installer: {name}...")
    print("=" * 60)
    iss_path = BUILD_DIR / iss_file
    if not iss_path.exists():
        print(f"FAILED: {iss_path} not found")
        return False

    INSTALLERS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [str(iscc), str(iss_path)]
    result = subprocess.run(cmd, cwd=str(BUILD_DIR))
    if result.returncode != 0:
        print(f"FAILED: {name} installer build failed")
        return False
    print(f"SUCCESS: {name} installer built -> installers/")
    return True


def build_installers() -> bool:
    """Build both Inno Setup installers."""
    iscc = find_iscc()
    if not iscc:
        print("ERROR: Inno Setup not found!")
        print("Install: winget install JRSoftware.InnoSetup")
        return False

    print(f"Using Inno Setup: {iscc}\n")
    ok1 = build_installer("PhotoSelector", "photoselector.iss", iscc)
    ok2 = build_installer("KanatkaReceiver", "receiver.iss", iscc)
    return ok1 and ok2


def main():
    parser = argparse.ArgumentParser(description="Build kanatka2 EXE distributions and installers")
    parser.add_argument("--main", action="store_true", help="Build main app EXE only")
    parser.add_argument("--receiver", action="store_true", help="Build receiver EXE only")
    parser.add_argument("--installers", action="store_true", help="Build Inno Setup installers only")
    parser.add_argument("--all", action="store_true", help="Build everything (default)")
    args = parser.parse_args()

    if not args.main and not args.receiver and not args.installers:
        args.all = True

    results = []

    # Build EXEs
    if args.main or args.all:
        results.append(("PhotoSelector EXE", build_main()))
    if args.receiver or args.all:
        results.append(("KanatkaReceiver EXE", build_receiver()))

    # Build installers
    if args.installers or args.all:
        results.append(("Installers", build_installers()))

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
