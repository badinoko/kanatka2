"""Build script for creating both EXE distributions.

Usage: python build/build.py [--main] [--receiver] [--all]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BUILD_DIR.parent
DIST_DIR = PROJECT_ROOT / "dist"


def build_main():
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


def build_receiver():
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


def main():
    parser = argparse.ArgumentParser(description="Build kanatka2 EXE distributions")
    parser.add_argument("--main", action="store_true", help="Build main app only")
    parser.add_argument("--receiver", action="store_true", help="Build receiver only")
    parser.add_argument("--all", action="store_true", help="Build both (default)")
    args = parser.parse_args()

    if not args.main and not args.receiver:
        args.all = True

    results = []
    if args.main or args.all:
        results.append(("PhotoSelector", build_main()))
    if args.receiver or args.all:
        results.append(("KanatkaReceiver", build_receiver()))

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
