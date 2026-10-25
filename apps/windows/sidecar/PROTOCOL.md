# SpektraFilm Windows sidecar protocol

The Windows shell does not link the simulation into Rust. A Python process
wraps the existing runtime and speaks **newline-delimited JSON** on
stdin/stdout (JSON-RPC shaped, one object per line). There is no listening
socket.

The Tauri shell is the only client. It starts the process, writes requests,
and reads responses. Requests are handled one at a time.

## Framing

- Request and response bodies are UTF-8 JSON objects.
- Each message is a single line terminated by `\n`.
- The sidecar writes protocol bytes only to stdout. Runtime `print` output is
  redirected to stderr. The shell also skips stray stdout lines that do not
  start with `{`.
- Launch Python with `-u` (the shell does this) so stdout is unbuffered.
- Stdin EOF ends the process.

## Request

```json
{"id": 1, "method": "health", "params": {}}
```

| Field    | Meaning                                      |
| -------- | -------------------------------------------- |
| `id`     | Caller-chosen id, echoed in the response.   |
| `method` | Command name.                                |
| `params` | Object of arguments. Omit or use `{}`.      |

## Response

```json
{"id": 1, "ok": true, "result": {"status": "ok"}}
```

```json
{"id": 1, "ok": false, "error": {"code": "runtime_error", "message": "..."}}
```

Error codes: `bad_request`, `unknown_method`, `runtime_error`.

## Methods

### `health`

No runtime import. Use this to confirm the process is speaking the protocol.

```json
{"id": 1, "method": "health", "params": {}}
```

```json
{
  "status": "ok",
  "sidecar": "spektrafilm-windows",
  "sidecar_version": "0.1.0",
  "protocol": 1,
  "python": "3.13.0"
}
```

### `version`

Reports the sidecar protocol and, when metadata is available, the installed
`spektrafilm` distribution version (or the checkout `pyproject.toml` version).

### `list_profiles`

```json
{"id": 2, "method": "list_profiles", "params": {"kind": "film"}}
```

`kind` is `film` or `print`.

The handler calls `spektrafilm.profiles.io.list_profiles` and `load_profile`,
then keeps stocks whose `info.stage` is `filming` (film) or `printing` (print).

```json
{
  "kind": "film",
  "profiles": [
    {
      "id": "kodak_portra_400",
      "name": "Kodak Portra 400",
      "stage": "filming",
      "type": "negative",
      "support": "film",
      "use": "still",
      "channel_model": "color",
      "target_print": "kodak_portra_endura"
    }
  ]
}
```

Summaries are cached for the life of the process.

### `import_raw`

Demosaic one camera RAW into a linear RGB buffer and keep it in the sidecar.
The pixels are not returned on the wire. A later `preview` with `source: "raw"`
reuses the buffer when the path and white-balance settings match.

The loader is `spektrafilm.utils.raw_file_processor.load_and_process_raw_file`
(rawpy demosaic, the same white-balance modes as the Qt GUI). `rawpy`,
`exiv2`, and `lensfunpy` come from the existing package install. If they are
missing, the response is `runtime_error` and names that dependency.

```json
{
  "id": 3,
  "method": "import_raw",
  "params": {
    "path": "C:\\photos\\frame.nef",
    "white_balance": "custom",
    "temperature": 5200,
    "tint": 1.0,
    "lens_correction": false,
    "output_color_space": "ProPhoto RGB"
  }
}
```

| Param | Default | Notes |
| ----- | ------- | ----- |
| `path` | required | Also accepted as `image_path`. |
| `white_balance` | `as_shot` | `as_shot`, `daylight`, `tungsten`, or `custom`. |
| `temperature` | `5500` | Kelvin. Used only for `custom`. Clamped to 1000..15000. |
| `tint` | `1` | Green multiplier. Used only for `custom`. Clamped to 0..4. |
| `lens_correction` | `false` | lensfun, same flag the Qt importer passes. |
| `output_color_space` | `ProPhoto RGB` | Linear. This becomes the simulation input color space. |

```json
{
  "source": "raw",
  "path": "C:\\photos\\frame.nef",
  "width": 6000,
  "height": 4000,
  "input_color_space": "ProPhoto RGB",
  "white_balance": "as_shot",
  "temperature": null,
  "tint": null,
  "lens_correction": false,
  "lens_summary": null,
  "lens_applied": false,
  "cached": true
}
```

`lens_summary` is set when lensfun identified a lens. An empty summary with
`lens_correction: true` means the correction was requested and not applied.

### `preview`

Runs one preview or a scan-mode pass and returns an 8-bit sRGB PNG.

`render_mode: "preview"` sets `settings.preview_mode` and calls
`simulate_preview` (the runtime drops grain and several blurs).
`render_mode: "scan"` leaves `preview_mode` off and calls `simulate`, so those
effects stay available. Both modes still resize to `max_size` before the
pipeline. This shell does not request a full-resolution scan.

```json
{
  "id": 4,
  "method": "preview",
  "params": {
    "film_profile": "kodak_portra_400",
    "print_profile": "kodak_portra_endura",
    "source": "raw",
    "image_path": "C:\\photos\\frame.nef",
    "white_balance": "as_shot",
    "render_mode": "preview",
    "max_size": 64,
    "exposure_compensation_ev": 0.0,
    "y_filter_shift": 10,
    "m_filter_shift": -5,
    "halation_active": true,
    "scatter_amount": 1.0,
    "scatter_spatial_scale": 1.0,
    "halation_amount": 1.0,
    "halation_spatial_scale": 1.0
  }
}
```

| Param | Default | Notes |
| ----- | ------- | ----- |
| `film_profile` | `kodak_portra_400` | Passed to `init_params`. |
| `print_profile` | `kodak_portra_endura` | Passed to `init_params`. |
| `source` | `builtin-chart`, or `path` when `image_path` is set | `builtin-chart`, `path`, or `raw`. |
| `image_path` | null | Linear file for `path` (`load_image_oiio`). RAW path for `raw`. |
| `render_mode` | `preview` | `preview` or `scan`. |
| `max_size` | `512` | Clamped to 16..2048. Sets `settings.preview_max_size`. The shell offers 512 and 1024. |
| `exposure_compensation_ev` | `0` | Clamped to -8..+8. Bias on `camera.exposure_compensation_ev`. |
| `y_filter_shift` | `0` | `enlarger.y_filter_shift`, Kodak CC steps, clamped to -200..200. |
| `m_filter_shift` | `0` | `enlarger.m_filter_shift`, same clamp. |
| `halation_active` | model default (`true`) | `film_render.halation.active`. |
| `scatter_amount` | `1` | `film_render.halation.scatter_amount`, clamped to 0..4. |
| `scatter_spatial_scale` | `1` | `film_render.halation.scatter_spatial_scale`, clamped to 0..4. |
| `halation_amount` | `1` | `film_render.halation.halation_amount`, clamped to 0..4. |
| `halation_spatial_scale` | `1` | `film_render.halation.halation_spatial_scale`, clamped to 0..4. |
| `input_color_space` | `ProPhoto RGB` for linear files | Ignored for the chart (linear sRGB) and for RAW (uses the import color space). |
| `input_cctf_decoding` | `false` | Linear-file inputs only. |
| `white_balance`, `temperature`, `tint`, `lens_correction` | same as `import_raw` | Used when `source` is `raw`. A cache miss re-imports. |

White-balance fields on a RAW preview use the same rules as `import_raw`.

Call sequence inside the sidecar:

1. Resolve the image: built-in chart, `load_image_oiio`, or the RAW cache.
2. `init_params(film_profile, print_profile)` from `spektrafilm`.
3. Copy the controls above onto the runtime parameter object.
4. Output color space `sRGB` with `output_cctf_encoding = True` (display PNG).
5. `simulate_preview` or `simulate`.

The built-in chart is a small synthetic linear ramp, not a measured color target.
Linear files should be scene-referred (16-bit or float TIFF/EXR), the same
expectation as the Qt file loader.

```json
{
  "film_profile": "kodak_portra_400",
  "print_profile": "kodak_portra_endura",
  "source": "raw",
  "image_path": "C:\\photos\\frame.nef",
  "input_width": 6000,
  "input_height": 4000,
  "width": 64,
  "height": 43,
  "mime": "image/png",
  "png_base64": "iVBORw0KGgo...",
  "elapsed_ms": 1200,
  "render_mode": "preview",
  "preview_mode": true,
  "max_size": 64,
  "exposure_compensation_ev": 0.0,
  "y_filter_shift": 10,
  "m_filter_shift": -5,
  "halation_active": true,
  "scatter_amount": 1.0,
  "scatter_spatial_scale": 1.0,
  "halation_amount": 1.0,
  "halation_spatial_scale": 1.0,
  "input_color_space": "ProPhoto RGB",
  "output_color_space": "sRGB",
  "raw_cache": "hit",
  "white_balance": "as_shot",
  "lens_summary": null
}
```

`raw_cache` is `hit`, `miss`, or `null` (not a RAW source).

RAW cache identity includes the resolved path, file size and modification/change
timestamps, plus white balance, lens settings, and working color space. Replacing
or modifying a RAW at the same path invalidates its decoded image on the next
request. A file changed during import is not treated as the newer file's cache.

`reference_png_base64` is the same frame before simulation, resized to `max_size`, transformed from the input RGB space/white point to sRGB, and encoded with the sRGB transfer function so the shell can hold-to-compare. `input_cctf_decoding` is respected. This includes conversion from ProPhoto RGB for the default RAW import. It is not a second print. It is `null` if that view could not be encoded.

The first preview can take a while: Numba compiles on first use, and the
spectral pipeline is per pixel. Keep `max_size` small. RAW demosaic is a
separate cost and happens on import or on a cache miss.

### `stock_thumb`

One developed thumbnail of the built-in linear chart for a film and a paper.
Exposure and the enlarger filters stay neutral. `settings.preview_mode` is on.
The long edge defaults to 96 and is clamped to 32–160. The chart is scaled
with nearest neighbors up to that edge so the patches stay flat.

```json
{"id": 11, "method": "stock_thumb", "params": {"film_profile": "kodak_portra_400", "print_profile": "kodak_portra_endura", "max_size": 96}}
```

The result carries `film_profile`, `print_profile`, `width`, `height`, `mime`,
`png_base64`, and `cached`. A repeated pair with the same `max_size` is served
from memory and does not call `simulate` again.

### `preview_thumbnails`

The same render, for a strip.

- `kind: "film"` holds `print_profile` and varies each film id.
- `kind: "print"` holds `film_profile` and varies each paper id.
- `ids` is optional. Omit it to use every profile of that kind.

```json
{"id": 12, "method": "preview_thumbnails", "params": {"kind": "film", "print_profile": "kodak_portra_endura", "ids": ["kodak_portra_400", "kodak_gold_200"], "max_size": 96}}
```

The result is `{kind, print_profile or film_profile, max_size, thumbs: [...]}`.
Each thumb has the `stock_thumb` fields. The shell asks for one thumb at a
time so the strip can fill in as each frame finishes. Requests are still
serialized. A cold catalog is one preview-mode chart per pair. Changing the
paper rebuilds the film strip; changing the film rebuilds the paper strip.
Exposure, filters, halation, and the loaded frame do not invalidate the cache.

## Manual check

From the repository root, with Python 3.13 and the package installed
(`pip install -e .`):

```bash
python -u apps/windows/sidecar/server.py --self-test
```

`--skip-preview` lists profiles and skips the simulation. Without flags the
process waits on stdin:

```bash
printf '%s\n' '{"id":1,"method":"health","params":{}}' | python -u apps/windows/sidecar/server.py
```
