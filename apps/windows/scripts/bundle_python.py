#!/usr/bin/env python3
# SpektraFilm Windows edition.
# Licensed under the GNU General Public License v3.0 only.
# See the LICENSE file in the repository root.
"""Build the private CPython runtime shipped inside the Windows installer.

The build machine must be 64-bit Windows. It downloads a pinned
python-build-standalone CPython, installs the sidecar's Windows wheels into
that prefix, then copies this repository's packages in. ``tauri dev`` does not
run this script and keeps using the developer's own interpreter.

End users never install Python. The Tauri bundle picks up
``src-tauri/resources/python`` only when you build with
``tauri.standalone.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# python-build-standalone release. install_only_stripped is a normal prefix
# (python.exe + Lib/ + DLLs/), not the python.org embeddable zip, and it has
# no ._pth file isolating site-packages. vcruntime140.dll ships beside python.exe.
PBS_RELEASE = "20261021"
PYTHON_VERSION = "3.13.17"
PBS_TRIPLE = "x86_64-pc-windows-msvc"
PBS_ASSET = (
    f"cpython-{PYTHON_VERSION}+{PBS_RELEASE}-{PBS_TRIPLE}-install_only_stripped.tar.gz"
)
PBS_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    f"{PBS_RELEASE}/{PBS_ASSET}"
)
PBS_SHA256 = "56cde3b1a1dcc36576753cb408ee0c3568d211baafa0eee40423adc147c480f2"
BUNDLE_KIND = "spektrafilm-python-bundle"

# Removed after the wheels are installed. The sidecar forces MPLBACKEND=Agg,
# so Tk is unused, and pip is a build-machine tool rather than part of the app.
_STDLIB_DIRS = ("idlelib", "turtledemo", "tkinter", "ensurepip")
_DLL_NAMES = ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_output() -> Path:
    return repo_root() / "apps" / "windows" / "src-tauri" / "resources" / "python"


def lock_path() -> Path:
    return repo_root() / "apps" / "windows" / "sidecar" / "requirements-standalone-win.lock"


def requirements_path() -> Path:
    return repo_root() / "apps" / "windows" / "sidecar" / "requirements-standalone.in"


def normalize_name(name: str) -> str:
    return name.lower().replace("_", "-")


def direct_requirement_names(text: str) -> list[str]:
    names: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = stripped.split("~=", 1)[0].split("==", 1)[0].split(">=", 1)[0].strip()
        if name:
            names.append(normalize_name(name))
    return names


def locked_requirement_names(text: str) -> set[str]:
    names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("--hash"):
            continue
        if "==" not in stripped:
            continue
        names.add(normalize_name(stripped.split("==", 1)[0].strip().rstrip("\\").strip()))
    return names


def check_lock(requirements: Path, lock: Path) -> list[str]:
    """Return human-readable problems. Empty means the lock covers the direct deps."""
    if not requirements.is_file():
        return [f"missing {requirements}"]
    if not lock.is_file():
        return [f"missing {lock}"]
    wanted = direct_requirement_names(requirements.read_text(encoding="utf-8"))
    locked = locked_requirement_names(lock.read_text(encoding="utf-8"))
    missing = [name for name in wanted if name not in locked]
    problems = [f"lock is missing {name}" for name in missing]
    if "--hash=sha256:" not in lock.read_text(encoding="utf-8"):
        problems.append("lock has no hashes; regenerate with --generate-hashes")
    return problems


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, expected_sha256: str) -> None:
    if dest.is_file() and sha256_file(dest) == expected_sha256:
        print(f"using cached {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    print(f"downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "spektrafilm-windows-bundle"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out)
    digest = sha256_file(partial)
    if digest != expected_sha256:
        partial.unlink(missing_ok=True)
        raise SystemExit(
            f"checksum mismatch for {dest.name}\n  expected {expected_sha256}\n  got      {digest}"
        )
    partial.replace(dest)


def extract_tar(archive: Path, dest: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:
            tar.extractall(dest)


def find_uv() -> str:
    found = shutil.which("uv")
    if found:
        return found
    raise SystemExit(
        "uv is required on the build machine. Install it from https://docs.astral.sh/uv/ "
        "and open a new terminal so `uv` is on PATH. The installed app does not need uv."
    )


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def _rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def slim_prefix(prefix: Path) -> tuple[int, int]:
    """Drop build-only and test files. Returns (files removed, bytes removed)."""
    removed_files = 0
    removed_bytes = 0

    def drop(path: Path) -> None:
        nonlocal removed_files, removed_bytes
        if not path.exists():
            return
        if path.is_file() or path.is_symlink():
            removed_files += 1
            try:
                removed_bytes += path.stat().st_size
            except OSError:
                pass
            path.unlink(missing_ok=True)
            return
        for child in path.rglob("*"):
            if child.is_file():
                removed_files += 1
                try:
                    removed_bytes += child.stat().st_size
                except OSError:
                    pass
        shutil.rmtree(path, ignore_errors=True)

    for name in ("include", "libs", "tcl", "Scripts"):
        drop(prefix / name)
    lib = prefix / "Lib"
    for name in _STDLIB_DIRS:
        drop(lib / name)
    dlls = prefix / "DLLs"
    for name in _DLL_NAMES:
        drop(dlls / name)

    site = lib / "site-packages"
    if site.is_dir():
        for child in list(site.iterdir()):
            lowered = child.name.lower()
            if lowered == "pip" or lowered.startswith("pip-"):
                drop(child)
        for dirpath, dirnames, filenames in os.walk(site, topdown=True):
            current = Path(dirpath)
            prune = [name for name in dirnames if name in {"__pycache__", "tests", "test"}]
            for name in prune:
                drop(current / name)
                dirnames.remove(name)
            for filename in filenames:
                if filename.endswith((".pyc", ".pyo")) or filename == "direct_url.json":
                    drop(current / filename)
    return removed_files, removed_bytes


def _metadata_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith(" ") or ":" not in line:
            if line.startswith(" ") and fields:
                continue
            if not line:
                break
            continue
        key, value = line.split(":", 1)
        fields.setdefault(key.strip(), value.strip())
        if key.strip() == "Description":
            break
    return fields


def _license_files(dist: Path) -> list[Path]:
    licenses = dist / "licenses"
    found: list[Path] = []
    if licenses.is_dir():
        found.extend(path for path in sorted(licenses.rglob("*")) if path.is_file())
    for path in sorted(dist.iterdir()):
        if path.is_file() and path.name.lower().startswith(("license", "copying", "notice")):
            found.append(path)
    return found


def render_third_party_notices(prefix: Path, app_license: str, profile_license: str) -> str:
    cpython = prefix / "LICENSE.txt"
    cpython_text = cpython.read_text(encoding="utf-8", errors="replace") if cpython.is_file() else ""
    parts = [
        "SpektraFilm Windows edition — third-party notices\n",
        "\n",
        "The application and the spektrafilm package are free software under the\n",
        "GNU General Public License version 3 only. See SPEKTRAFILM-GPL-3.0.txt\n",
        "in this folder and the LICENSE file in the source repository.\n",
        "Film and print profiles and the LUT data shipped inside the package are\n",
        "CC BY-SA 4.0. See SPEKTRAFILM_LICENSE.txt.\n",
        "\n",
        "This folder is a private CPython runtime plus the Python packages the\n",
        "Windows sidecar imports. It is not a system Python. Notices below are\n",
        "the license files shipped inside each distribution, plus the CPython\n",
        "license from the python-build-standalone archive.\n",
        "\n",
        "Two native libraries are vendored inside wheels whose own metadata names\n",
        "the Python wrapper rather than the C library:\n",
        "- rawpy bundles LibRaw (LGPL-2.1 OR CDDL-1.0): https://www.libraw.org/about\n",
        "- lensfunpy bundles lensfun (LGPL-3.0-or-later): https://lensfun.github.io/\n",
        "exiv2.dll inside the exiv2 wheel is the Exiv2 library, GPL-2.0-or-later,\n",
        "and the Python binding is GPL-3.0-or-later.\n",
        "OpenImageIO is Apache-2.0. Apache-2.0 and the permissive licenses below\n",
        "may be combined with GPLv3; this application as a whole stays GPLv3.\n",
        "PySide, Qt, and napari are not included.\n",
        "\n",
        "======== SpektraFilm (GPLv3) ========\n\n",
        app_license,
        "\n\n======== Profile and LUT data (CC BY-SA 4.0) ========\n\n",
        profile_license,
        "\n\n======== CPython (PSF License) ========\n\n",
        cpython_text,
    ]
    site = prefix / "Lib" / "site-packages"
    if site.is_dir():
        for dist in sorted(path for path in site.iterdir() if path.name.endswith(".dist-info")):
            metadata_path = dist / "METADATA"
            meta = (
                _metadata_fields(metadata_path.read_text(encoding="utf-8", errors="replace"))
                if metadata_path.is_file()
                else {}
            )
            name = meta.get("Name", dist.name)
            version = meta.get("Version", "")
            license_name = meta.get("License", meta.get("License-Expression", "(see files)"))
            parts.append(f"\n\n======== {name} {version} ========\nLicense: {license_name}\n")
            files = _license_files(dist)
            if not files:
                parts.append("\n(no license file shipped in the wheel metadata)\n")
            for path in files:
                parts.append(f"\n----- {path.relative_to(dist).as_posix()} -----\n")
                parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "".join(parts)


def directory_usage(path: Path) -> tuple[int, int]:
    files = 0
    size = 0
    for child in path.rglob("*"):
        if child.is_file():
            files += 1
            try:
                size += child.stat().st_size
            except OSError:
                pass
    return files, size


def git_commit(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = completed.stdout.strip()
    return commit or None


def install_locked_packages(prefix: Path, uv: str) -> None:
    python = prefix / "python.exe"
    run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--only-binary",
            ":all:",
            "--require-hashes",
            "-r",
            str(lock_path()),
        ]
    )
    run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            str(repo_root()),
        ]
    )


def assert_package_copied(prefix: Path) -> None:
    package = prefix / "Lib" / "site-packages" / "spektrafilm"
    init = package / "__init__.py"
    profiles = package / "data" / "profiles"
    if not init.is_file() or init.is_symlink():
        raise SystemExit(
            "spektrafilm was not copied into the private runtime. "
            "The installer must not depend on a checkout path."
        )
    if not profiles.is_dir() or not any(profiles.iterdir()):
        raise SystemExit("film profiles are missing from the private runtime")
    for egg in (prefix / "Lib" / "site-packages").glob("*.egg-link"):
        raise SystemExit(f"refusing an editable install link: {egg}")


def write_marker(prefix: Path) -> None:
    root = repo_root()
    marker = {
        "kind": BUNDLE_KIND,
        "python": PYTHON_VERSION,
        "pbs_release": PBS_RELEASE,
        "pbs_asset": PBS_ASSET,
        "platform": PBS_TRIPLE,
        "spektrafilm": _project_version(root),
        "git_commit": git_commit(root),
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (prefix / "BUNDLE.json").write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    (prefix / "README.txt").write_text(
        "Private Python runtime for SpektraFilm on Windows.\n"
        "Do not point this interpreter at a system PATH and do not pip install into it.\n"
        "License notices: THIRD_PARTY_NOTICES.txt, SPEKTRAFILM-GPL-3.0.txt, LICENSE.txt.\n"
        "Profile and LUT data: SPEKTRAFILM_LICENSE.txt (CC BY-SA 4.0).\n",
        encoding="utf-8",
    )


def _project_version(root: Path) -> str | None:
    in_project = False
    for line in (root / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("version") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def verify_imports(prefix: Path) -> None:
    python = prefix / "python.exe"
    snippet = r"""
import json, sys
mods = [
    "numpy", "scipy", "colour", "skimage", "numba", "matplotlib",
    "OpenImageIO", "exiv2", "rawpy", "lensfunpy",
]
failed = []
for name in mods:
    try:
        __import__(name)
    except Exception as exc:
        failed.append(f"{name}: {type(exc).__name__}: {exc}")
if failed:
    print("\n".join(failed), file=sys.stderr)
    raise SystemExit(1)
from spektrafilm.profiles.io import list_profiles, load_profile
films, papers = [], []
for slug in list_profiles():
    info = load_profile(slug).info
    if info.stage == "filming":
        films.append(info.stock or slug)
    elif info.stage == "printing":
        papers.append(info.stock or slug)
if not films or not papers:
    raise SystemExit(f"expected film and print profiles, got {len(films)} and {len(papers)}")
from spektrafilm import init_params
init_params(film_profile=films[0], print_profile=papers[0])
print(json.dumps({
    "ok": True,
    "films": len(films),
    "prints": len(papers),
    "executable": sys.executable,
    "bundled_import": "spektrafilm" in sys.modules,
}))
"""
    env = os.environ.copy()
    env["SPEKTRAFILM_BUNDLED"] = "1"
    env["MPLBACKEND"] = "Agg"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    print("verifying imports in the private runtime", flush=True)
    subprocess.run(
        [str(python), "-I", "-c", snippet],
        check=True,
        env=env,
        cwd=prefix,
    )


def verify_preview(prefix: Path) -> None:
    python = prefix / "python.exe"
    script = repo_root() / "apps" / "windows" / "sidecar" / "server.py"
    env = os.environ.copy()
    env["SPEKTRAFILM_BUNDLED"] = "1"
    env["MPLBACKEND"] = "Agg"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    print("running sidecar self-test (first Numba compile can take several minutes)", flush=True)
    subprocess.run(
        [str(python), "-I", "-u", str(script), "--self-test"],
        check=True,
        env=env,
        cwd=prefix,
    )


def require_windows_x64() -> None:
    if sys.platform != "win32":
        raise SystemExit(
            "bundle_python.py installs a Windows x64 CPython and Windows wheels.\n"
            "Run it on the Windows machine where you will run `tauri build`.\n"
            "`tauri dev` does not need this step."
        )
    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        raise SystemExit(
            f"This runtime is Windows x64 only (this machine reports {platform.machine()}). "
            "ARM64 Windows is not part of this installer."
        )


def build(output: Path, *, skip_verify: bool, with_preview: bool) -> None:
    require_windows_x64()
    problems = check_lock(requirements_path(), lock_path())
    if problems:
        raise SystemExit("requirements lock is out of date:\n" + "\n".join(problems))
    uv = find_uv()
    cache = output.parent / ".cache"
    archive = cache / PBS_ASSET
    download(PBS_URL, archive, PBS_SHA256)

    if output.exists():
        print(f"replacing {output}")
        _rmtree(output)
    staging = output.parent / ".python-extract"
    _rmtree(staging)
    staging.mkdir(parents=True)
    extract_tar(archive, staging)
    extracted = staging / "python"
    if not (extracted / "python.exe").is_file():
        raise SystemExit(f"{PBS_ASSET} did not contain python/python.exe")
    shutil.move(str(extracted), str(output))
    _rmtree(staging)

    install_locked_packages(output, uv)
    assert_package_copied(output)
    removed_files, removed_bytes = slim_prefix(output)
    print(f"removed {removed_files} build/test files ({removed_bytes / 1e6:.1f} MB)")
    assert_package_copied(output)

    root = repo_root()
    app_license = (root / "LICENSE").read_text(encoding="utf-8", errors="replace")
    profile_license = (root / "SPEKTRAFILM_LICENSE.txt").read_text(encoding="utf-8", errors="replace")
    (output / "SPEKTRAFILM-GPL-3.0.txt").write_text(app_license, encoding="utf-8")
    (output / "SPEKTRAFILM_LICENSE.txt").write_text(profile_license, encoding="utf-8")
    (output / "THIRD_PARTY_NOTICES.txt").write_text(
        render_third_party_notices(output, app_license, profile_license),
        encoding="utf-8",
    )
    write_marker(output)

    files, size = directory_usage(output)
    print(f"private runtime: {files} files, {size / 1e6:.0f} MB at {output}")
    if not skip_verify:
        verify_imports(output)
    if with_preview:
        verify_preview(output)
    elif not skip_verify:
        print("import check passed. Run with --with-preview to develop the built-in chart once.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output(),
        help="Prefix to write (default: src-tauri/resources/python)",
    )
    parser.add_argument(
        "--check-lock",
        action="store_true",
        help="Check the Windows lock file and exit. Works on any operating system.",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Do not import the scientific stack after installing it.",
    )
    parser.add_argument(
        "--with-preview",
        action="store_true",
        help="After the import check, run sidecar --self-test (Numba compile).",
    )
    args = parser.parse_args(argv)
    if args.check_lock:
        problems = check_lock(requirements_path(), lock_path())
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 1
        print("requirements lock covers the standalone sidecar dependencies")
        return 0
    build(args.output, skip_verify=args.skip_verify, with_preview=args.with_preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
