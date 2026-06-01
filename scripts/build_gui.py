"""
Build script for creating executable and optional installer.
"""
import argparse
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
        print(f"✓ PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("✗ PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("✓ PyInstaller installed")

    # Build using spec file
    spec_file = Path("bandcamp_auto_uploader.spec")
    if not spec_file.exists():
        print(f"✗ Spec file not found: {spec_file}")
        return 1

    print(f"\n{'=' * 60}")
    print("Running PyInstaller...")
    print(f"{'=' * 60}\n")

    result = subprocess.run(
        ["pyinstaller", "--clean", str(spec_file)],
        check=False
    )

    if result.returncode == 0:
        print(f"\n{'=' * 60}")
        print("✓ Build completed successfully!")
        print(f"{'=' * 60}")
        exe_path = Path("dist") / "Bandcamp Auto Uploader.exe"
        print(f"\nExecutable: {exe_path}")
    else:
        print(f"\n{'=' * 60}")
        print("✗ Build failed!")
        print(f"{'=' * 60}")
        return result.returncode

    return 0


def build_installer():
    """Build the Inno Setup installer."""
    iscc = Path("C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe")
    if not iscc.exists():
        iscc = Path("C:\\Program Files\\Inno Setup 6\\ISCC.exe")
    if not iscc.exists():
        print("✗ Inno Setup not found. Install from https://jrsoftware.org/isdl.php")
        return 1

    iss_script = Path("scripts") / "installer.iss"
    if not iss_script.exists():
        print(f"✗ Installer script not found: {iss_script}")
        return 1

    print(f"\n{'=' * 60}")
    print("Building installer...")
    print(f"{'=' * 60}\n")

    result = subprocess.run([str(iscc), str(iss_script)], check=False)
    if result.returncode == 0:
        print(f"\n✓ Installer built successfully!")
        print(f"  dist\\installer\\")
    else:
        print(f"\n✗ Installer build failed!")
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
