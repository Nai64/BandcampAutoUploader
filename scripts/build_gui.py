"""
Build script for creating executable and optional installer.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path


def build_exe():
    """Build the executable using PyInstaller"""
    print("=" * 60)
    print("Building Bandcamp Auto Uploader GUI Executable")
    print("=" * 60)

    # Ensure PyInstaller is installed
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("[FAIL] PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("[OK] PyInstaller installed")

    # Build using spec file
    spec_file = Path("bandcamp_auto_uploader.spec")
    if not spec_file.exists():
        print(f"[FAIL] Spec file not found: {spec_file}")
        return 1

    print(f"\n{'=' * 60}")
    print("Running PyInstaller...")
    print(f"{'=' * 60}\n")

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", str(spec_file)],
        check=False
    )

    if result.returncode == 0:
        print(f"\n{'=' * 60}")
        print("[OK] Build completed successfully!")
        print(f"{'=' * 60}")
        exe_path = Path("dist") / "Bandcamp Auto Uploader.exe"
        print(f"\nExecutable: {exe_path}")
    else:
        print(f"\n{'=' * 60}")
        print("[FAIL] Build failed!")
        print(f"{'=' * 60}")
        return result.returncode

    return 0


def _find_iscc():
    """Locate ISCC.exe across common Inno Setup install paths (v5, v6, v7+)."""
    search_roots = [
        Path("C:\\Program Files (x86)"),
        Path("C:\\Program Files"),
    ]
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
    if local.exists():
        search_roots.append(local)

    for root in search_roots:
        if not root.exists():
            continue
        for dir in root.iterdir():
            if "Inno Setup" in dir.name and (dir / "ISCC.exe").exists():
                return dir / "ISCC.exe"
    return None


def build_installer():
    """Build the Inno Setup installer."""
    iscc = _find_iscc()
    if not iscc:
        print("[FAIL] Inno Setup not found. Install from https://jrsoftware.org/isdl.php")
        return 1

    iss_script = Path("scripts") / "installer.iss"
    if not iss_script.exists():
        print(f"[FAIL] Installer script not found: {iss_script}")
        return 1

    print(f"\n{'=' * 60}")
    print("Building installer...")
    print(f"{'=' * 60}\n")

    result = subprocess.run([str(iscc), str(iss_script)], check=False)
    if result.returncode == 0:
        print(f"\n[OK] Installer built successfully!")
        print(f"  dist\\installer\\")
    else:
        print(f"\n[FAIL] Installer build failed!")
        return result.returncode
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Bandcamp Auto Uploader")
    parser.add_argument("--installer", action="store_true", help="Build installer after EXE")
    args = parser.parse_args()

    ret = build_exe()
    if ret != 0:
        sys.exit(ret)

    if args.installer:
        ret = build_installer()
        sys.exit(ret)
