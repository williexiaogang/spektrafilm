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

### `preview`

Runs one preview and returns an 8-bit sRGB PNG.

```json
{
  "id": 3,
  "method": "preview",
  "params": {
    "film_profile": "kodak_portra_400",
    "print_profile": "kodak_portra_endura",
    "image_path": null,
    "max_size": 48,
    "exposure_compensation_ev": 0.0
  }
}
```

| Param                        | Default                 | Notes |
| ---------------------------- | ----------------------- | ----- |
| `film_profile`               | `kodak_portra_400`      | Passed to `init_params`. |
| `print_profile`              | `kodak_portra_endura`   | Passed to `init_params`. |
| `image_path`                 | null                    | Linear image readable by `load_image_oiio`. Null uses a built-in chart. |
| `max_size`                   | `48`                    | Clamped to 16..256. Sets `settings.preview_max_size`. |
| `exposure_compensation_ev`   | `0`                     | Clamped to -5..+5. |
| `input_color_space`          | `ProPhoto RGB` for files | Ignored for the built-in chart, which is linear sRGB. |
| `input_cctf_decoding`        | `false`                 | File inputs only. |

Call sequence inside the sidecar:

1. `init_params(film_profile, print_profile)` from `spektrafilm`.
2. `settings.preview_mode = True` so `digest_params` uses the runtime preview path.
3. Output color space `sRGB` with `output_cctf_encoding = True` (display PNG).
4. `simulate_preview(image, params)`.

The built-in chart is a small synthetic linear ramp, not a measured color target.
File inputs should be scene-referred linear images (16-bit or float TIFF/EXR),
the same expectation as the Qt file loader. The loader is
`spektrafilm.utils.io.load_image_oiio`.

```json
{
  "film_profile": "kodak_portra_400",
  "print_profile": "kodak_portra_endura",
  "source": "builtin-chart",
  "image_path": null,
  "width": 24,
  "height": 12,
  "mime": "image/png",
  "png_base64": "iVBORw0KGgo...",
  "elapsed_ms": 1200,
  "preview_mode": true,
  "max_size": 48,
  "exposure_compensation_ev": 0.0,
  "input_color_space": "sRGB",
  "output_color_space": "sRGB"
}
```

The first preview can take a while: Numba compiles on first use, and the
spectral pipeline is per pixel. Keep `max_size` small.

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
