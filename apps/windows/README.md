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

On launch the UI asks the Rust shell to start `python -u sidecar/server.py` and list film and print profiles. Stock thumbnails load in the background; use **Expose** to develop the selected source. Requests are newline-delimited JSON. There is no network port.

All Python requests run off the desktop event thread. A request has a five-minute timeout to allow a cold Numba compilation. A timeout, process exit, or broken protocol ends that process; the next operation starts a fresh one. Ordinary image/parameter errors preserve the cache. **Reconnect** retries a failed startup. Closing the window can stop an in-flight render.

The image-first layout — film strip, easel, inspector — is described in [`DESIGN.md`](DESIGN.md).

## What this shell does

- Health and version.
- Film stocks (`info.stage == filming`) and print papers (`info.stage == printing`), via `list_profiles` and `load_profile`.
- Preview and scan: `init_params`, then `simulate_preview` or `simulate`. Preview turns on `settings.preview_mode`. Scan leaves it off so grain and the other preview-mode cuts stay available. Both still resize to the size control.
- The long-edge choices are **512** and **1024** pixels; the protocol accepts up to 2048. These are working previews, not full-resolution exports. The display uses smooth scaling. Changing controls marks the previous print **Stale** without altering its colors.
- Exposure compensation, enlarger yellow/magenta filter shifts, and the high-level halation and scatter amount/size controls. Those are existing runtime fields.
- A built-in linear chart, a linear image path (`load_image_oiio`), or a camera RAW. In **File** mode, choose the **RGB space** used to export the scene-linear TIFF/EXR (sRGB by default). RAW import calls `load_and_process_raw_file` (rawpy) with the same white-balance modes as the Qt GUI: as shot, daylight, tungsten, and custom temperature plus tint. The demosaiced buffer stays in the sidecar and is reused until the file or white balance changes.
- Strip thumbnails (`stock_thumb`, `preview_thumbnails`). Each tile is that same chart developed with `preview_mode` at a 96px long edge, for one film and one paper, at neutral exposure and filters. The sidecar keeps the PNG in memory. The film strip refreshes when the paper changes, and the paper strip refreshes when the film changes. A cold pass is one small preview per pair. It does not rerun when exposure, the filters, or the loaded frame change.
- Failed thumbnails stop animating, show an error marker, and can be retried with the strip's **Retry** button. Hold the picture or **Hold** button to compare the source converted to display-ready sRGB. Keyboard users can hold Space or Enter on **Hold**; releasing the key or leaving the control ends comparison.

The README at the repo root still shows `create_params`. In this tree the function is `init_params` (see `src/spektrafilm/runtime/params_builder.py`). The sidecar uses `init_params`.

## Prerequisites

Install the Python package first, from the repository root. The sidecar imports that environment; it does not carry its own copy of NumPy, Numba, or the profiles.

```bash
# Windows, once
conda create -n spektrafilm python=3.13
conda activate spektrafilm
pip install -e .
```

`uv` works too (`uv pip install -e .` against a 3.13 interpreter). Python **3.13** is required by the project. A newer or older interpreter is not a supported sidecar target.

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

The bundle targets in `src-tauri/tauri.conf.json` are NSIS and MSI. Installers land under `src-tauri/target/release/bundle/`. The script `sidecar/server.py` is packaged as a resource. Python and the scientific wheels are not. A machine that runs the installed app still needs Python 3.13 and `spektrafilm` on that interpreter (`pip install` of this repo, or the same environment you developed with).

`SPEKTRAFILM_PYTHON` and `SPEKTRAFILM_SIDECAR` override interpreter and script discovery when you need them.

In a checkout, the launcher prefers the root `.venv` interpreter if present, then tries the platform's Python commands. `SPEKTRAFILM_PYTHON` takes precedence. Each candidate must answer a health request before it is selected.

## Regression checks

From `apps/windows`:

```bash
npm run build
npx playwright install chromium
npm run test:ui
cd src-tauri
cargo test --locked --lib
```

The browser tests exercise the real React UI with a simulated native IPC boundary. Rust tests use a small Python subprocess to verify timeout, crash recovery, response IDs, and shutdown during a request. From the repository root, with the Python environment active, run `python -m pytest tests/test_windows_sidecar.py -q` for protocol, rendering, and color conversion tests. No camera RAW sample is required for these checks.

## Develop on Linux or macOS

The same commands run the shell where Tauri's webview dependencies are installed. That is a developer convenience. The packaged targets above are the Windows installers. Building NSIS/MSI is a Windows step.

## License

This shell is a derivative of [spektrafilm](https://github.com/andreavolpato/spektrafilm) by Andrea Volpato. It is free software under the GNU General Public License version 3 only. See `LICENSE` in the repository root. Do not strip the GPL notices when you redistribute it.
