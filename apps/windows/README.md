# SpektraFilm Windows edition

A desktop shell for Windows: **Tauri 2** hosts a **React** UI and a **Python sidecar**. The sidecar calls the existing runtime in `src/spektrafilm`. It does not reimplement the physical pipeline.

The Qt + napari package `spektrafilm_gui` is still the research GUI (`spektrafilm` on the command line). This tree is the Windows edition path. Both are GPLv3, the same license as the rest of the repository (see `LICENSE` at the repo root). Profiles and LUTs stay CC BY-SA 4.0.

```
apps/windows/
  src/                 React UI (Vite)
  src-tauri/           Tauri 2 / Rust shell
  sidecar/server.py    Python JSON-RPC process
  sidecar/PROTOCOL.md  stdin/stdout protocol
```

On launch the Rust shell starts `python -u sidecar/server.py`, then the UI asks it to list film and print profiles and to run one preview. Requests are newline-delimited JSON. There is no network port.

The image-first layout — film strip, easel, inspector — is described in [`DESIGN.md`](DESIGN.md).

## What this shell does

- Health and version.
- Film stocks (`info.stage == filming`) and print papers (`info.stage == printing`), via `list_profiles` and `load_profile`.
- Preview and scan: `init_params`, then `simulate_preview` or `simulate`. Preview turns on `settings.preview_mode`. Scan leaves it off so grain and the other preview-mode cuts stay available. Both still resize to the size control.
- Exposure compensation, enlarger yellow/magenta filter shifts, and the high-level halation and scatter amount/size controls. Those are existing runtime fields.
- A built-in linear chart, a linear image path (`load_image_oiio`), or a camera RAW. RAW import calls `load_and_process_raw_file` (rawpy) with the same white-balance modes as the Qt GUI: as shot, daylight, tungsten, and custom temperature plus tint. The demosaiced buffer stays in the sidecar and is reused until the file or white balance changes.
- Strip thumbnails (`stock_thumb`, `preview_thumbnails`). Each tile is that same chart developed with `preview_mode` at a 96px long edge, for one film and one paper, at neutral exposure and filters. The sidecar keeps the PNG in memory. The film strip refreshes when the paper changes, and the paper strip refreshes when the film changes. A cold pass is one small preview per pair. It does not rerun when exposure, the filters, or the loaded frame change.

The README at the repo root still shows `create_params`. In this tree the function is `init_params` (see `src/spektrafilm/runtime/params_builder.py`). The sidecar uses `init_params`.

## Prerequisites

Development uses your own Python. The sidecar imports that environment; `tauri dev` does not carry a second copy of NumPy, Numba, or the profiles.

```bash
# Windows, once
conda create -n spektrafilm python=3.13
conda activate spektrafilm
pip install -e .
```

`uv` works too (`uv pip install -e .` against a 3.13 interpreter). Python **3.13** is required by the project. A newer or older interpreter is not a supported sidecar target.

The standalone installer, described below, is the build that embeds a private interpreter. People who only run that installer do not install Python, conda, or this repository.

Then, for the shell itself:

- Node.js 20 or newer (npm).
- Rust stable from [rustup](https://rustup.rs/). Tauri 2.12's crates need Rust 1.90 or newer (`rustup update`).
- [Tauri 2 prerequisites on Windows](https://v2.tauri.app/start/prerequisites/): WebView2 (already present on current Windows 10/11) and the Microsoft C++ build tools.

## Run in development

From `apps/windows`, with the spektrafilm environment active so `python` can `import spektrafilm`:

```bash
npm install
npm run tauri dev
```

The window opens the Vite dev server at `http://localhost:1420` inside the Tauri webview. The Python process starts with the window. Pick a film and a paper, or open a RAW file, then **Develop preview**. RAW demosaic uses the same Python environment as the sidecar. If `rawpy` is missing, the status panel shows that error and the chart path still works.

If `py -3.13` is not the interpreter that has the package, point at it before launching:

```powershell
$env:SPEKTRAFILM_PYTHON = "C:\Users\you\anaconda3\envs\spektrafilm\python.exe"
npm run tauri dev
```

On PowerShell the launcher form is also fine: `$env:SPEKTRAFILM_PYTHON = "py -3.13"`.

`npm run dev` alone serves the layout in a browser. Profile lists and Develop stay disabled there, because only the Tauri process owns the sidecar.

A headless check of the Python side, from the repository root:

```bash
python -u apps/windows/sidecar/server.py --self-test
python -u apps/windows/sidecar/server.py --self-test --skip-preview
```

The full self-test runs a small Portra 400 / Portra Endura preview. The first call compiles Numba kernels and can sit there for a while. `--skip-preview` only checks health, version, and both profile lists.

## Build

On Windows, from `apps/windows`:

```bash
npm run tauri build
```

The bundle targets in `src-tauri/tauri.conf.json` are NSIS and MSI. Installers land under `src-tauri/target/release/bundle/`. The script `sidecar/server.py` is packaged as a resource. This thin build does **not** embed Python. A machine that runs it still needs Python 3.13 and `spektrafilm` on that interpreter.

`SPEKTRAFILM_PYTHON` and `SPEKTRAFILM_SIDECAR` override interpreter and script discovery for that thin build and for `tauri dev`. A standalone install ignores `SPEKTRAFILM_PYTHON` and does not search `PATH`.

## Building the standalone installer

The standalone build installs a private CPython **3.13.17** (python-build-standalone, release `20261021`, Windows x64, `install_only_stripped`) next to the app and installs the sidecar's wheels into that prefix. The shell launches `python.exe -I -u sidecar\server.py`. `-I` ignores `PYTHONPATH` and user site-packages. There is no `python` or `py` lookup.

Chosen approach: a relocatable CPython prefix plus wheels, not a frozen binary.

| Approach | Why it was or was not used |
| --- | --- |
| **python-build-standalone via a pinned tarball, packages installed with uv** | Used. The archive is a normal prefix (`python.exe`, `Lib\`, `DLLs\`, `vcruntime140.dll`) with no `._pth` isolation, so Numba, rawpy, and OpenImageIO keep the layout their wheels were built for. Rebuilding one dependency is a lockfile edit and a reinstall. |
| python.org embeddable zip | Smaller, but `python313._pth` turns site off, pip is not included, and scientific wheels are fussier there. |
| PyInstaller or Nuitka one-dir sidecar | The import graph (Numba, OpenImageIO, colour-science data, package data) is brittle, and a freeze is harder to patch than a prefix. |
| A uv relocatable venv beside a base interpreter | Symlinks and baked paths break when an installer copies the tree. Installing into the prefix avoids that. |

The prefix is produced by `scripts/bundle_python.py` into `src-tauri/resources/python/` (gitignored). `src-tauri/tauri.standalone.json` adds that directory to the bundle resources, so the installer copies it to `python\` beside `SpektraFilm.exe`. On Windows, Tauri's resource directory is the folder that contains the executable. The release shell uses that `python\python.exe` when `BUNDLE.json` is present and does not fall back to a system interpreter. `tauri dev` is a debug build and keeps the system interpreter unless you set `SPEKTRAFILM_USE_BUNDLED=1`.

### What is inside

Direct pins match `pyproject.toml`. The lock file resolves them to exact wheels. Notable pins in `sidecar/requirements-standalone-win.lock` today:

- numpy 2.5.4, scipy 1.18.1, numba 0.68.0, llvmlite 0.50.0
- matplotlib 3.11.2, colour-science 0.4.7, scikit-image 0.26.0
- OpenImageIO 3.1.18.1, exiv2 0.18.1, rawpy 0.26.1, lensfunpy 1.18.0

That set covers list profiles, the built-in chart, `simulate_preview` / `simulate`, linear images through OpenImageIO, and RAW import (`rawpy`, `exiv2`, `lensfunpy`). OpenImageIO and exiv2 are not optional: `init_params` imports `spektrafilm.utils.io`, which imports both at module level. All of them publish `cp313-win_amd64` wheels, which the lock install requires (`--only-binary :all:`).

Not bundled, on purpose:

- PySide6, Qt, napari, qtpy, markdown. The Qt research GUI stays `pip install -e .`.
- pyfftw. Nothing on the preview, scan, or RAW path imports it. Windows wheels exist if a later change needs `fft_gaussian_filter.py`.
- Tk. The sidecar sets `MPLBACKEND=Agg`. The prefix deletes Tcl/Tk to save space.
- pip, headers, and package `tests/` directories.

`spektrafilm` itself is copied into `Lib\site-packages` (not an editable install), including `data/profiles`. Numba's cache is redirected to `%LOCALAPPDATA%\app.spektrafilm.windows\numba-cache` so the install directory does not have to be writable after setup.

### Size

Measured from the Windows wheels plus the CPython archive, after the script's slim step and the ~17 MB `spektrafilm` package:

- Installed private runtime: **about 530 MB** and **about 7,000 files**.
- Compressed inputs: about **170 MB** (the wheels as downloaded, plus the 21 MB CPython archive).
- NSIS installer: expect **roughly 200–400 MB**. zlib is selected in `tauri.standalone.json` because the payload is already compressed binaries and lzma's dictionary is hungry at this size. The exact installer size is whatever `src-tauri/target/release/bundle/nsis/` contains after a Windows build. This change was not packaged on Windows.

The NSIS install is per-user, under `%LOCALAPPDATA%\SpektraFilm`, so it does not need an administrator. Uninstall removes the files the installer copied, including `python\`. The Numba cache is app data and is removed only if the uninstaller is told to delete app data.

### Licenses

The app stays GPLv3. `licenseFile` points the installer at the repository `LICENSE`. The prefix also gets:

- `SPEKTRAFILM-GPL-3.0.txt` and CPython's `LICENSE.txt` (PSF-2.0)
- `SPEKTRAFILM_LICENSE.txt` for the profile and LUT data (CC BY-SA 4.0)
- `THIRD_PARTY_NOTICES.txt`, assembled from each wheel's metadata and license files

Do not strip those files. Apache-2.0 (OpenImageIO) and the BSD/MIT/PSF packages can be combined with GPLv3; the combined work is GPLv3. Two wheels wrap native libraries whose own metadata names the Python binding:

- rawpy (MIT) bundles LibRaw, LGPL-2.1 OR CDDL-1.0
- lensfunpy (MIT) bundles lensfun, LGPL-3.0-or-later
- exiv2 (GPL-3.0-or-later) bundles Exiv2, GPL-2.0-or-later

Those notes are repeated at the top of `THIRD_PARTY_NOTICES.txt`. Corresponding source for SpektraFilm is this repository at the commit recorded in `python\BUNDLE.json`.

### Build machine

64-bit Windows. The script refuses other platforms. You need:

- Network, once, to download CPython and the locked wheels
- [uv](https://docs.astral.sh/uv/) on `PATH` (`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`, then a new terminal)
- A Python that can run `scripts/bundle_python.py` (3.11 or newer is enough; it is not the interpreter that gets shipped)
- The same Node.js, Rust, and Visual Studio C++ build tools as `tauri dev`
- Several gigabytes of free disk during the link

From `apps/windows`:

```powershell
py -3 scripts/bundle_python.py --check-lock
py -3 scripts/bundle_python.py
npm run tauri -- build --config src-tauri/tauri.standalone.json
```

`npm run build:standalone` runs those last two steps. `--check-lock` also runs on Linux and macOS; it only checks that `requirements-standalone-win.lock` still covers `requirements-standalone.in`.

The script prints the file count and the unpacked size. It then imports the scientific stack and calls `init_params` inside the private interpreter. Add `--with-preview` to also run `server.py --self-test` (the first Numba compile is slow). `--skip-verify` skips both.

Regenerate the lock when the ranges in `requirements-standalone.in` change. From any OS, with uv:

```bash
uv pip compile apps/windows/sidecar/requirements-standalone.in \
  --python-version 3.13 \
  --python-platform x86_64-pc-windows-msvc \
  --only-binary :all: \
  --generate-hashes \
  -o apps/windows/sidecar/requirements-standalone-win.lock
```

Installers:

- NSIS (the one to give someone): `src-tauri/target/release/bundle/nsis/`
- MSI as well, because the base config still lists it. If WiX runs out of memory on the file list, build NSIS only:

```powershell
npm run tauri -- build --config src-tauri/tauri.standalone.json --bundles nsis
```

Before packaging, you can point a debug shell at the prefix without installing:

```powershell
$env:SPEKTRAFILM_USE_BUNDLED = "1"
npm run tauri dev
```

Hover the lamp in the header. Its tooltip should include `bundled`, and the Python path should be the private `python.exe`. Unset the variable to go back to the conda or venv interpreter. `tauri dev` without that variable does not look at `resources\python`.

### Smoke-test checklist

On the build machine, after `bundle_python.py`:

1. The script's import check prints `"ok": true` and a film count.
2. Optional: `py -3 scripts/bundle_python.py --with-preview` develops the built-in chart with the private interpreter.
3. `SPEKTRAFILM_USE_BUNDLED=1 npm run tauri dev`: hover the header lamp. The tooltip includes `bundled` and an `executable` under `resources\python\python.exe`.

On a clean 64-bit Windows 10 or 11 user account, with no Python installed (`where.exe python` and `where.exe py` fail):

1. Double-click the NSIS installer. It installs for the current user. WebView2 may download if Windows does not already have it. Python does not.
2. Launch SpektraFilm from the Start menu.
3. Hover the header lamp. The tooltip includes `Python 3.13` and `bundled`, and the path is the installed `python\python.exe`, not a system interpreter.
4. Film and paper lists populate.
5. Develop preview on the built-in chart returns an image. The first one compiles Numba kernels and can sit there for a while.
6. Open a camera RAW. Demosaic should run. If it fails, the message names the missing import; chart preview should still work.
7. Uninstall. `%LOCALAPPDATA%\SpektraFilm` is removed.

`tauri dev` on a developer machine, without `SPEKTRAFILM_USE_BUNDLED`, still uses the environment where you ran `pip install -e .`. The lamp tooltip names that interpreter and does not say `bundled`.

### Known gaps

- Windows x64 only. ARM64 is not in this installer.
- The installer itself has to be built on Windows. This script will not cross-compile the prefix from Linux or macOS.
- The Qt / napari GUI is not in the installer.
- pyfftw is not in the installer.
- Installed size is about 530 MB. A single frozen executable was not the goal.
- The exact NSIS byte size depends on the Windows link step.

## Develop on Linux or macOS

The same `npm run tauri dev` commands run the shell where Tauri's webview dependencies are installed. That is a developer convenience and still uses system Python. Building the NSIS/MSI installers, including the standalone one, is a Windows step. `py -3 scripts/bundle_python.py --check-lock` (or `python3 scripts/bundle_python.py --check-lock`) is safe on any OS.

## License

This shell is a derivative of [spektrafilm](https://github.com/andreavolpato/spektrafilm) by Andrea Volpato. It is free software under the GNU General Public License version 3 only. See `LICENSE` in the repository root. Do not strip the GPL notices when you redistribute it.
