"""
Build script for creating executable and optional installer.

Output layout (everything for a given version is grouped under one folder)::

    dist/
    +-- BandcampAutoUploader-V3b/
        +-- BandcampAutoUploader-3b-x64.exe          (standalone)
        +-- BandcampAutoUploader-3b-x86.exe
        +-- BandcampAutoUploader-3b-arm64.exe
        +-- BandcampAutoUploader-Setup-3b-x64.exe    (installer)
        +-- BandcampAutoUploader-Setup-3b-x86.exe
        +-- BandcampAutoUploader-Setup-3b-arm64.exe

The folder name follows ``BandcampAutoUploader-V{__version__}`` and is read
from ``bandcamp_auto_uploader/__version__.py`` (the single source of truth).

Cross-compilation note: PyInstaller cannot cross-compile. To build for a
target architecture you must run this script on a Python interpreter that
matches that architecture (e.g. x86 Python for x86 builds, ARM64 Python
for arm64 builds). Use the --all flag to attempt every known arch via
the Windows ``py`` launcher and skip any that are not installed.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bandcamp_auto_uploader import __version__  # noqa: E402

# Arch -> PEP 514 "py launcher" tag. Add entries here to support more.
KNOWN_ARCHS = {
    "x64":   "3.14-64",
    "x86":   "3.14-32",
    "arm64": "3.14-arm64",
}

SPEC_TEMPLATE = Path("bandcamp_auto_uploader.spec")
TEMP_SPEC = Path("bandcamp_auto_uploader.generated.spec")
INTERMEDIATE_DIR = Path("dist/_intermediate")


def _version_folder_name() -> str:
    """Top-level version folder: ``BandcampAutoUploader-V{version}``."""
    return f"BandcampAutoUploader-V{__version__}"


def _version_dir() -> Path:
    """Absolute path to the version output folder."""
    return ROOT / "dist" / _version_folder_name()


def _version_dir_rel_from_scripts() -> str:
    """Path to the version folder relative to scripts/installer.iss."""
    return f"..\\dist\\{_version_folder_name()}"


def _standalone_name(arch: str) -> str:
    return f"BandcampAutoUploader-{__version__}-{arch}.exe"


def _run(cmd, **kwargs):
    """Run a command, print it, and stream output."""
    print(f"\n$ {' '.join(str(c) for c in cmd)}\n")
    return subprocess.run(cmd, check=False, **kwargs)


def _py_for_arch(arch: str) -> list:
    """Return the Python interpreter argv prefix for the given arch.

    Uses the Windows ``py`` launcher when a PEP 514 tag is known for the arch,
    otherwise falls back to the currently running interpreter.
    """
    tag = KNOWN_ARCHS.get(arch)
    if tag and sys.platform == "win32":
        return ["py", f"-{tag}"]
    return [sys.executable]


def _detect_installed_archs():
    """Query ``py --list`` to figure out which arches are actually installed.

    Returns a subset of KNOWN_ARCHS whose matching interpreter is present.
    Falls back to the current arch when only a single Python is installed
    (the ``py`` launcher only shows PEP 514 tags when multiple interpreters
    exist).
    """
    if sys.platform != "win32":
        return list(KNOWN_ARCHS.keys())
    try:
        result = subprocess.run(
            ["py", "--list"], capture_output=True, text=True, timeout=15
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    output = (result.stdout or "") + (result.stderr or "")

    available = []
    for arch, tag in KNOWN_ARCHS.items():
        for sep in (" ", "\t", "\n"):
            if f"-{tag}{sep}" in output or f"-{tag} *{sep}" in output:
                available.append(arch)
                break

    if not available and "Python" in output:
        import platform
        machine = platform.machine().lower()
        if machine in ("amd64", "x86_64"):
            available.append("x64")
        elif machine in ("x86", "i386", "i686"):
            available.append("x86")
        elif machine in ("arm64", "aarch64"):
            available.append("arm64")
    return available


def _generate_spec(arch: str) -> Path:
    """Copy the tracked spec to a temp file with target_arch injected and UPX disabled."""
    if not SPEC_TEMPLATE.exists():
        raise FileNotFoundError(f"Spec file not found: {SPEC_TEMPLATE}")
    content = SPEC_TEMPLATE.read_text(encoding="utf-8")
    new_content, n = re.subn(
        r"target_arch\s*=\s*None",
        f'target_arch="{arch}"',
        content,
        count=1,
    )
    if n != 1:
        raise RuntimeError(
            "Could not inject target_arch into spec file "
            "(expected exactly one 'target_arch=None' line)."
        )
    new_content, _ = re.subn(
        r"upx\s*=\s*True",
        "upx=False",
        new_content,
        count=1,
    )
    TEMP_SPEC.write_text(new_content, encoding="utf-8")
    print(f"[OK] Generated spec for arch '{arch}': {TEMP_SPEC}")
    return TEMP_SPEC


def build_exe(arch: str = "x64") -> int:
    """Build the executable using PyInstaller for the given architecture."""
    print("=" * 60)
    print(f"Building Bandcamp Auto Uploader GUI Executable  (arch={arch})")
    print("=" * 60)

    # UPX check
    py = _py_for_arch(arch)
    print(f"[i] Using Python: {' '.join(py)}")

    spec = _generate_spec(arch)
    intermediate = INTERMEDIATE_DIR / arch
    version_dir = _version_dir()
    version_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print("Running PyInstaller...")
    print(f"{'=' * 60}\n")

    result = _run([
        *py, "-m", "PyInstaller", "--clean",
        "--distpath", str(intermediate),
        "--workpath", f"build/{arch}",
        str(spec),
    ])

    if result.returncode != 0:
        print(f"\n{'=' * 60}")
        print(f"[FAIL] Build failed!  (arch={arch})")
        print(f"{'=' * 60}")
        return result.returncode

    # PyInstaller emits the EXE under its spec-defined name; rename to the
    # versioned + arch-tagged filename and move it into the version folder.
    src = intermediate / "Bandcamp Auto Uploader.exe"
    dst = version_dir / _standalone_name(arch)
    shutil.move(str(src), str(dst))
    shutil.rmtree(INTERMEDIATE_DIR, ignore_errors=True)

    size_mb = dst.stat().st_size / (1024 * 1024)
    print(f"\n{'=' * 60}")
    print(f"[OK] Build completed successfully!  (arch={arch})")
    print(f"{'=' * 60}")
    print(f"\nStandalone: {dst.relative_to(ROOT)}")
    print(f"EXE size:   {size_mb:.1f} MB")
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


def build_installer(arch: str = "x64") -> int:
    """Build the Inno Setup installer for the given architecture."""
    iscc = _find_iscc()
    if not iscc:
        print("[FAIL] Inno Setup not found. Install from https://jrsoftware.org/isdl.php")
        return 1

    iss_script = Path("scripts") / "installer.iss"
    if not iss_script.exists():
        print(f"[FAIL] Installer script not found: {iss_script}")
        return 1

    version_dir = _version_dir()
    standalone = version_dir / _standalone_name(arch)
    if not standalone.exists():
        print(f"[FAIL] Standalone EXE not found, build it first: {standalone}")
        return 1

    print(f"\n{'=' * 60}")
    print(f"Building installer  (arch={arch})...")
    print(f"{'=' * 60}\n")

    output_dir = _version_dir_rel_from_scripts()
    src_path = f"{output_dir}\\{_standalone_name(arch)}"

    result = _run([
        str(iscc),
        f"/DMyAppArch={arch}",
        f"/DMyAppOutputDir={output_dir}",
        f"/DMyAppExePath={src_path}",
        str(iss_script),
    ])
    if result.returncode == 0:
        installer = version_dir / f"BandcampAutoUploader-Setup-{__version__}-{arch}.exe"
        print(f"\n[OK] Installer built successfully!  (arch={arch})")
        print(f"  {installer.relative_to(ROOT)}")
        return 0
    else:
        print(f"\n[FAIL] Installer build failed!  (arch={arch})")
        return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Bandcamp Auto Uploader (per-architecture, versioned)."
    )
    parser.add_argument(
        "--arch",
        choices=list(KNOWN_ARCHS.keys()),
        default="x64",
        help="Target architecture (default: x64). Ignored if --all is set.",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="Build installer after EXE.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Build for every arch whose matching Python interpreter is installed.",
    )
    args = parser.parse_args()

    archs = _detect_installed_archs() if args.all else [args.arch]
    if not archs:
        print("[FAIL] No matching Python interpreters found for any known arch.")
        return 1

    print(f"Target architectures: {', '.join(archs)}")
    print(f"Output folder: dist/{_version_folder_name()}/")

    overall_rc = 0
    for arch in archs:
        rc = build_exe(arch)
        if rc == 0 and args.installer:
            rc = build_installer(arch)
        if rc != 0:
            overall_rc = rc
            if not args.all:
                break
            print(f"[!] Skipping remaining architectures after failure on {arch}.")
            break

    if TEMP_SPEC.exists():
        try:
            TEMP_SPEC.unlink()
            print(f"[OK] Cleaned up {TEMP_SPEC}")
        except OSError:
            pass

    return overall_rc


if __name__ == "__main__":
    sys.exit(main())
