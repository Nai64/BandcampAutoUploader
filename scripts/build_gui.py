"""
Build script for creating executable and optional installer.

Supports building for multiple architectures (x64, x86, arm64).
Each architecture gets its own output folder:
    dist/{arch}/Bandcamp Auto Uploader.exe
    dist/installer/{arch}/BandcampAutoUploader-Setup-{version}-{arch}.exe

Cross-compilation note: PyInstaller cannot cross-compile. To build for a
target architecture you must run this script on a Python interpreter that
matches that architecture (e.g. x86 Python for x86 builds, ARM64 Python
for arm64 builds). Use the --all flag to attempt every known arch via
the Windows `py` launcher and skip any that aren't installed.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Arch -> PEP 514 "py launcher" tag. Add entries here to support more.
KNOWN_ARCHS = {
    "x64":   "3.14-64",
    "x86":   "3.14-32",
    "arm64": "3.14-arm64",
}

SPEC_TEMPLATE = Path("bandcamp_auto_uploader.spec")
TEMP_SPEC = Path("bandcamp_auto_uploader.generated.spec")


def _run(cmd, **kwargs):
    """Run a command, print it, and stream output."""
    print(f"\n$ {' '.join(str(c) for c in cmd)}\n")
    return subprocess.run(cmd, check=False, **kwargs)


def _py_for_arch(arch: str) -> list:
    """Return the Python interpreter argv prefix for the given arch.

    Uses the Windows `py` launcher when a PEP 514 tag is known for the arch,
    otherwise falls back to the currently running interpreter.
    """
    tag = KNOWN_ARCHS.get(arch)
    if tag and sys.platform == "win32":
        return ["py", f"-{tag}"]
    return [sys.executable]


def _detect_installed_archs():
    """Query `py --list` to figure out which arches are actually installed.

    Returns a subset of KNOWN_ARCHS whose matching interpreter is present.
    Falls back to the current arch when only a single Python is installed
    (the `py` launcher only shows PEP 514 tags when multiple interpreters exist).
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
        # PEP 514 tag present in `py --list` output (only when multiple Pythons exist)
        for sep in (" ", "\t", "\n"):
            if f"-{tag}{sep}" in output or f"-{tag} *{sep}" in output:
                available.append(arch)
                break

    if not available and "Python" in output:
        # Single Python installed: assume it matches the running interpreter's arch.
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
    """Copy the tracked spec to a temp file with target_arch injected."""
    if not SPEC_TEMPLATE.exists():
        raise FileNotFoundError(f"Spec file not found: {SPEC_TEMPLATE}")
    content = SPEC_TEMPLATE.read_text(encoding="utf-8")
    # Replace the bare `target_arch=None` with the requested arch.
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
    TEMP_SPEC.write_text(new_content, encoding="utf-8")
    print(f"[OK] Generated spec for arch '{arch}': {TEMP_SPEC}")
    return TEMP_SPEC


def build_exe(arch: str = "x64") -> int:
    """Build the executable using PyInstaller for the given architecture."""
    print("=" * 60)
    print(f"Building Bandcamp Auto Uploader GUI Executable  (arch={arch})")
    print("=" * 60)

    py = _py_for_arch(arch)
    print(f"[i] Using Python: {' '.join(py)}")

    spec = _generate_spec(arch)
    dist_dir = Path(f"dist/{arch}")

    print(f"\n{'=' * 60}")
    print("Running PyInstaller...")
    print(f"{'=' * 60}\n")

    result = _run([
        *py, "-m", "PyInstaller", "--clean",
        "--distpath", str(dist_dir),
        "--workpath", f"build/{arch}",
        str(spec),
    ])

    if result.returncode == 0:
        print(f"\n{'=' * 60}")
        print(f"[OK] Build completed successfully!  (arch={arch})")
        print(f"{'=' * 60}")
        exe_path = dist_dir / "Bandcamp Auto Uploader.exe"
        print(f"\nExecutable: {exe_path}")
        return 0
    else:
        print(f"\n{'=' * 60}")
        print(f"[FAIL] Build failed!  (arch={arch})")
        print(f"{'=' * 60}")
        return result.returncode


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

    print(f"\n{'=' * 60}")
    print(f"Building installer  (arch={arch})...")
    print(f"{'=' * 60}\n")

    src_path = f"..\\dist\\{arch}\\Bandcamp Auto Uploader.exe"
    result = _run([
        str(iscc),
        f"/DMyAppArch={arch}",
        f"/DMyAppSourcePath={src_path}",
        str(iss_script),
    ])
    if result.returncode == 0:
        print(f"\n[OK] Installer built successfully!  (arch={arch})")
        print(f"  dist\\installer\\{arch}\\")
        return 0
    else:
        print(f"\n[FAIL] Installer build failed!  (arch={arch})")
        return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Bandcamp Auto Uploader (per-architecture)."
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
