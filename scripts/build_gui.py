"""
Build script for creating executable
"""
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
        print("\nExecutable location:")
        print(f"  dist\\BandcampAutoUploaderGUI.exe")
        print("\nYou can now run the executable or distribute it.")
    else:
        print(f"\n{'=' * 60}")
        print("✗ Build failed!")
        print(f"{'=' * 60}")
        return result.returncode
    
    return 0


if __name__ == "__main__":
    sys.exit(build_exe())
