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

## What the first slice does

- Health and version.
- Film stocks (`info.stage == filming`) and print papers (`info.stage == printing`), via `list_profiles` and `load_profile`.
- One preview: `init_params` + `simulate_preview`, with `settings.preview_mode` turned on. The result is an sRGB PNG the center pane can show.
- A built-in linear chart, or a linear image path passed to `load_image_oiio`.
- Exposure compensation, in EV. Grain, halation, and enlarger filter shifts are visible in the layout and not wired yet.

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

The window opens the Vite dev server at `http://localhost:1420` inside the Tauri webview. The Python process starts with the window. Pick a film and a paper, then **Develop preview**.

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

## Develop on Linux or macOS

The same commands run the shell where Tauri's webview dependencies are installed. That is a developer convenience. The packaged targets above are the Windows installers. Building NSIS/MSI is a Windows step.

## License

This shell is a derivative of [spektrafilm](https://github.com/andreavolpato/spektrafilm) by Andrea Volpato. It is free software under the GNU General Public License version 3 only. See `LICENSE` in the repository root. Do not strip the GPL notices when you redistribute it.
