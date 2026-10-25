# SpektraFilm Windows edition.
# Licensed under the GNU General Public License v3.0 only.
# See the LICENSE file in the repository root.
# Derivative of spektrafilm by Andrea Volpato.
"""Python sidecar for the SpektraFilm Windows shell.

Speaks newline-delimited JSON on stdin/stdout. The simulation itself stays in
``spektrafilm``; this process only lists profiles and runs a preview.

See ``PROTOCOL.md`` in this directory.
"""

from __future__ import annotations

import base64
import json
import struct
import sys
import traceback
import zlib
from pathlib import Path

PROTOCOL_VERSION = 1
SIDECAR_VERSION = "0.2.0"
_WHITE_BALANCE_MODES = frozenset({"as_shot", "daylight", "tungsten", "custom"})

_PROFILE_SUMMARIES: list[dict] | None = None
_RAW_CACHE: dict | None = None


def repo_root() -> Path | None:
    """Find a checkout that contains the runtime package."""
    starts = [Path(__file__).resolve(), Path.cwd().resolve()]
    seen: set[Path] = set()
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate in seen:
                continue
            seen.add(candidate)
            if (candidate / "pyproject.toml").is_file() and (
                candidate / "src" / "spektrafilm" / "__init__.py"
            ).is_file():
                return candidate
    return None


def ensure_import_path() -> None:
    """Prefer the checkout's ``src/`` so the sidecar matches this tree."""
    root = repo_root()
    if root is None:
        return
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def _silence_stdout():
    """Send library ``print`` calls to stderr so they cannot break the protocol."""

    class _Redirect:
        def __enter__(self):
            self._saved = sys.stdout
            sys.stdout = sys.stderr
            return self

        def __exit__(self, exc_type, exc, tb):
            sys.stdout = self._saved
            return False

    return _Redirect()


def health() -> dict:
    return {
        "status": "ok",
        "sidecar": "spektrafilm-windows",
        "sidecar_version": SIDECAR_VERSION,
        "protocol": PROTOCOL_VERSION,
        "python": sys.version.split()[0],
    }


def _version_from_pyproject() -> str | None:
    root = repo_root()
    if root is None:
        return None
    in_project = False
    for line in (root / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("version") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def version() -> dict:
    spektrafilm_version = None
    try:
        ensure_import_path()
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as package_version

        try:
            spektrafilm_version = package_version("spektrafilm")
        except PackageNotFoundError:
            spektrafilm_version = _version_from_pyproject()
    except Exception:
        spektrafilm_version = _version_from_pyproject()
    return {
        "sidecar": SIDECAR_VERSION,
        "protocol": PROTOCOL_VERSION,
        "spektrafilm": spektrafilm_version,
        "python": sys.version.split()[0],
    }


def _profile_summaries() -> list[dict]:
    global _PROFILE_SUMMARIES
    if _PROFILE_SUMMARIES is not None:
        return _PROFILE_SUMMARIES

    ensure_import_path()
    from spektrafilm.profiles.io import list_profiles, load_profile

    summaries: list[dict] = []
    for slug in list_profiles():
        info = load_profile(slug).info
        summaries.append(
            {
                "id": info.stock or slug,
                "name": info.name or info.stock or slug,
                "stage": info.stage,
                "type": info.type,
                "support": info.support,
                "use": info.use,
                "channel_model": info.channel_model,
                "target_print": info.target_print,
            }
        )
    _PROFILE_SUMMARIES = summaries
    return summaries


def list_profiles_cmd(params: dict) -> dict:
    kind = params.get("kind")
    stage = {"film": "filming", "print": "printing"}.get(kind)
    if stage is None:
        raise ValueError("kind must be 'film' or 'print'")
    profiles = [item for item in _profile_summaries() if item["stage"] == stage]
    profiles.sort(key=lambda item: str(item["name"]).lower())
    return {"kind": kind, "profiles": profiles}


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    if value is None or isinstance(value, bool):
        number = default
    else:
        number = int(value)
    return max(lo, min(hi, number))


def _clamp_float(value, default: float, lo: float, hi: float) -> float:
    if value is None or isinstance(value, bool):
        number = default
    else:
        number = float(value)
    return max(lo, min(hi, number))


def _as_rgb(image):
    import numpy as np

    array = np.asarray(image, dtype=np.float64)
    if array.ndim == 2:
        array = np.repeat(array[..., None], 3, axis=2)
    if array.ndim != 3 or array.shape[2] < 3:
        raise ValueError(f"expected an RGB image, got shape {tuple(array.shape)}")
    return np.ascontiguousarray(array[..., :3])


def _builtin_chart():
    """Small linear sRGB chart. Patches are synthetic, not a measured target."""
    import numpy as np

    patches = (
        (0.02, 0.02, 0.02),
        (0.18, 0.18, 0.18),
        (0.45, 0.45, 0.45),
        (0.90, 0.90, 0.90),
        (0.55, 0.04, 0.04),
        (0.04, 0.40, 0.07),
        (0.03, 0.07, 0.50),
        (0.04, 0.38, 0.42),
        (0.45, 0.05, 0.32),
        (0.62, 0.55, 0.06),
        (0.52, 0.30, 0.20),
        (0.22, 0.16, 0.08),
    )
    patch = 4
    columns = 6
    rows = 2
    width = columns * patch
    ramp_height = patch
    height = rows * patch + ramp_height
    image = np.zeros((height, width, 3), dtype=np.float64)
    for index, rgb in enumerate(patches):
        y, x = divmod(index, columns)
        image[
            y * patch : (y + 1) * patch,
            x * patch : (x + 1) * patch,
            :,
        ] = rgb
    ramp = np.linspace(0.02, 0.95, width, dtype=np.float64)
    image[rows * patch :, :, :] = ramp[None, :, None]
    return image


def _load_linear_image(path: str):
    from spektrafilm.utils.io import load_image_oiio

    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"image not found: {file_path}")
    return _as_rgb(load_image_oiio(str(file_path)))


def encode_png_rgb8(raw: bytes, width: int, height: int) -> bytes:
    """Write an 8-bit RGB PNG. Stdlib only, so the sidecar need not import Pillow."""
    expected = width * height * 3
    if width <= 0 or height <= 0 or len(raw) != expected:
        raise ValueError(f"PNG payload is {len(raw)} bytes, expected {expected}")

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    rows = bytearray()
    stride = width * 3
    for y in range(height):
        rows.append(0)
        rows.extend(raw[y * stride : (y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", ihdr),
            chunk(b"IDAT", zlib.compress(bytes(rows), 9)),
            chunk(b"IEND", b""),
        )
    )


def _result_to_png(result) -> tuple[bytes, int, int]:
    import numpy as np

    array = _as_rgb(result)
    array = np.nan_to_num(array, nan=0.0, posinf=1.0, neginf=0.0)
    array = np.clip(array, 0.0, 1.0)
    u8 = np.rint(array * 255.0).astype(np.uint8)
    height, width = int(u8.shape[0]), int(u8.shape[1])
    return encode_png_rgb8(u8.tobytes(), width, height), width, height


def _optional_path(value, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    return value.strip() or None


def _render_mode(params: dict) -> str:
    mode = params.get("render_mode") or "preview"
    if mode not in ("preview", "scan"):
        raise ValueError("render_mode must be 'preview' or 'scan'")
    return mode


def _white_balance_settings(params: dict) -> dict:
    mode = params.get("white_balance") or "as_shot"
    if mode not in _WHITE_BALANCE_MODES:
        raise ValueError("white_balance must be 'as_shot', 'daylight', 'tungsten', or 'custom'")
    temperature = _clamp_float(params.get("temperature"), default=5500.0, lo=1000.0, hi=15000.0)
    tint = _clamp_float(params.get("tint"), default=1.0, lo=0.0, hi=4.0)
    lens_correction = bool(params.get("lens_correction") or False)
    output_color_space = str(params.get("output_color_space") or "ProPhoto RGB")
    return {
        "white_balance": mode,
        "temperature": temperature if mode == "custom" else None,
        "tint": tint if mode == "custom" else None,
        "lens_correction": lens_correction,
        "output_color_space": output_color_space,
    }


def _raw_fingerprint(path: str, settings: dict) -> tuple:
    return (
        str(Path(path).expanduser().resolve()),
        settings["white_balance"],
        settings["temperature"],
        settings["tint"],
        settings["lens_correction"],
        settings["output_color_space"],
    )


def load_raw_image(path: str, settings: dict):
    """Demosaic a RAW file with the runtime's existing rawpy helper.

    The returned buffer is linear RGB in ``settings['output_color_space']``.
    """
    ensure_import_path()
    try:
        from spektrafilm.utils.raw_file_processor import load_and_process_raw_file
    except ImportError as exc:
        raise RuntimeError(
            "RAW import needs the spektrafilm install "
            "(rawpy, exiv2, lensfunpy, and colour-science). "
            f"{exc}"
        ) from exc

    lens_info: dict[str, str] = {}
    image = load_and_process_raw_file(
        path,
        white_balance=settings["white_balance"],
        temperature=settings["temperature"],
        tint=settings["tint"],
        lens_correction=settings["lens_correction"],
        output_colorspace=settings["output_color_space"],
        output_cctf_encoding=False,
        lens_info_out=lens_info,
    )
    return _as_rgb(image), lens_info.get("summary") or None


def _require_raw_file(path: str) -> Path:
    file_path = Path(path).expanduser()
    if file_path.is_dir():
        raise ValueError(f"expected a RAW file, got a directory: {file_path}")
    if not file_path.is_file():
        raise FileNotFoundError(f"RAW file not found: {file_path}")
    return file_path


def _remember_raw(fingerprint: tuple, image, meta: dict) -> None:
    global _RAW_CACHE
    _RAW_CACHE = {"fingerprint": fingerprint, "image": image, "meta": meta}


def _raw_meta(path: Path, image, settings: dict, lens_summary: str | None) -> dict:
    height, width = int(image.shape[0]), int(image.shape[1])
    return {
        "source": "raw",
        "path": str(path),
        "width": width,
        "height": height,
        "input_color_space": settings["output_color_space"],
        "white_balance": settings["white_balance"],
        "temperature": settings["temperature"],
        "tint": settings["tint"],
        "lens_correction": settings["lens_correction"],
        "lens_summary": lens_summary,
        "lens_applied": bool(lens_summary),
        "cached": True,
    }


def import_raw_cmd(params: dict) -> dict:
    """Load one RAW file into the sidecar cache. The pixels stay in-process."""
    path_text = _optional_path(params.get("path") or params.get("image_path"), field="path")
    if path_text is None:
        raise ValueError("path is required")
    settings = _white_balance_settings(params)
    file_path = _require_raw_file(path_text)
    image, lens_summary = load_raw_image(str(file_path), settings)
    meta = _raw_meta(file_path, image, settings, lens_summary)
    _remember_raw(_raw_fingerprint(str(file_path), settings), image, meta)
    return meta


def _cached_raw(fingerprint: tuple):
    if _RAW_CACHE is None or _RAW_CACHE.get("fingerprint") != fingerprint:
        return None
    return _RAW_CACHE


def _apply_interactive_params(runtime_params, params: dict, *, render_mode: str, max_size: int, exposure: float, input_color_space: str, input_cctf_decoding: bool) -> None:
    """Copy the shell's controls onto runtime fields that already exist."""
    runtime_params.settings.preview_mode = render_mode != "scan"
    runtime_params.settings.preview_max_size = max_size
    runtime_params.camera.exposure_compensation_ev = exposure
    runtime_params.enlarger.y_filter_shift = _clamp_float(
        params.get("y_filter_shift"), default=0.0, lo=-200.0, hi=200.0
    )
    runtime_params.enlarger.m_filter_shift = _clamp_float(
        params.get("m_filter_shift"), default=0.0, lo=-200.0, hi=200.0
    )
    halation = runtime_params.film_render.halation
    if "halation_active" in params and params.get("halation_active") is not None:
        halation.active = bool(params["halation_active"])
    halation.scatter_amount = _clamp_float(params.get("scatter_amount"), default=1.0, lo=0.0, hi=4.0)
    halation.scatter_spatial_scale = _clamp_float(
        params.get("scatter_spatial_scale"), default=1.0, lo=0.0, hi=4.0
    )
    halation.halation_amount = _clamp_float(params.get("halation_amount"), default=1.0, lo=0.0, hi=4.0)
    halation.halation_spatial_scale = _clamp_float(
        params.get("halation_spatial_scale"), default=1.0, lo=0.0, hi=4.0
    )
    runtime_params.io.input_color_space = input_color_space
    runtime_params.io.input_cctf_decoding = input_cctf_decoding
    runtime_params.io.output_color_space = "sRGB"
    runtime_params.io.output_cctf_encoding = True


def run_simulation(image, runtime_params, render_mode: str):
    """Preview keeps the runtime's fast digest. Scan turns that digest off.

    Both modes still respect ``preview_max_size``. A full-resolution RAW scan
    is not what this shell requests.
    """
    from spektrafilm import simulate, simulate_preview

    if render_mode == "scan":
        from spektrafilm.utils.preview import resize_for_preview

        sized = resize_for_preview(image, runtime_params.settings.preview_max_size)
        return simulate(sized, runtime_params)
    return simulate_preview(image, runtime_params)


def _resolve_preview_image(params: dict):
    requested = params.get("source")
    image_path = _optional_path(params.get("image_path"), field="image_path")
    if requested is None:
        requested = "path" if image_path else "builtin-chart"
    if requested not in ("builtin-chart", "path", "raw"):
        raise ValueError("source must be 'builtin-chart', 'path', or 'raw'")

    raw_cache = None
    lens_summary = None
    if requested == "raw":
        if image_path is None:
            raise ValueError("image_path is required when source is 'raw'")
        settings = _white_balance_settings(params)
        file_path = _require_raw_file(image_path)
        fingerprint = _raw_fingerprint(str(file_path), settings)
        cached = _cached_raw(fingerprint)
        if cached is None:
            image, lens_summary = load_raw_image(str(file_path), settings)
            meta = _raw_meta(file_path, image, settings, lens_summary)
            _remember_raw(fingerprint, image, meta)
            raw_cache = "miss"
        else:
            image = cached["image"]
            lens_summary = cached["meta"].get("lens_summary")
            raw_cache = "hit"
        return {
            "image": image,
            "source": "raw",
            "image_path": str(file_path),
            "input_color_space": settings["output_color_space"],
            "input_cctf_decoding": False,
            "raw_cache": raw_cache,
            "lens_summary": lens_summary,
            "white_balance": settings["white_balance"],
        }

    if requested == "path":
        if image_path is None:
            raise ValueError("image_path is required when source is 'path'")
        return {
            "image": _load_linear_image(image_path),
            "source": "path",
            "image_path": image_path,
            "input_color_space": str(params.get("input_color_space") or "ProPhoto RGB"),
            "input_cctf_decoding": bool(params.get("input_cctf_decoding") or False),
            "raw_cache": None,
            "lens_summary": None,
            "white_balance": None,
        }

    return {
        "image": _builtin_chart(),
        "source": "builtin-chart",
        "image_path": None,
        "input_color_space": "sRGB",
        "input_cctf_decoding": False,
        "raw_cache": None,
        "lens_summary": None,
        "white_balance": None,
    }


def preview_cmd(params: dict) -> dict:
    """Run one preview or scan through the existing runtime.

    ``init_params`` plus ``simulate`` / ``simulate_preview`` are the public
    entry points. ``settings.preview_mode`` is the runtime's own fast path
    and is on only for ``render_mode: "preview"``.
    """
    import time

    render_mode = _render_mode(params)
    film_profile = str(params.get("film_profile") or "kodak_portra_400")
    print_profile = str(params.get("print_profile") or "kodak_portra_endura")
    max_size = _clamp_int(params.get("max_size"), default=64, lo=16, hi=256)
    exposure = _clamp_float(
        params.get("exposure_compensation_ev"),
        default=0.0,
        lo=-8.0,
        hi=8.0,
    )
    prepared = _resolve_preview_image(params)
    image = prepared["image"]
    input_height, input_width = int(image.shape[0]), int(image.shape[1])

    ensure_import_path()
    from spektrafilm import init_params

    runtime_params = init_params(
        film_profile=film_profile,
        print_profile=print_profile,
    )
    _apply_interactive_params(
        runtime_params,
        params,
        render_mode=render_mode,
        max_size=max_size,
        exposure=exposure,
        input_color_space=prepared["input_color_space"],
        input_cctf_decoding=prepared["input_cctf_decoding"],
    )

    started = time.perf_counter()
    with _silence_stdout():
        result = run_simulation(image, runtime_params, render_mode)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    png, width, height = _result_to_png(result)
    halation = runtime_params.film_render.halation
    return {
        "film_profile": film_profile,
        "print_profile": print_profile,
        "source": prepared["source"],
        "image_path": prepared["image_path"],
        "input_width": input_width,
        "input_height": input_height,
        "width": width,
        "height": height,
        "mime": "image/png",
        "png_base64": base64.b64encode(png).decode("ascii"),
        "elapsed_ms": elapsed_ms,
        "render_mode": render_mode,
        "preview_mode": runtime_params.settings.preview_mode,
        "max_size": max_size,
        "exposure_compensation_ev": exposure,
        "y_filter_shift": runtime_params.enlarger.y_filter_shift,
        "m_filter_shift": runtime_params.enlarger.m_filter_shift,
        "halation_active": halation.active,
        "scatter_amount": halation.scatter_amount,
        "scatter_spatial_scale": halation.scatter_spatial_scale,
        "halation_amount": halation.halation_amount,
        "halation_spatial_scale": halation.halation_spatial_scale,
        "input_color_space": prepared["input_color_space"],
        "output_color_space": "sRGB",
        "raw_cache": prepared["raw_cache"],
        "white_balance": prepared["white_balance"],
        "lens_summary": prepared["lens_summary"],
    }


def _ok(request_id, result: dict) -> dict:
    return {"id": request_id, "ok": True, "result": result}


def _error(request_id, code: str, message: str) -> dict:
    return {"id": request_id, "ok": False, "error": {"code": code, "message": message}}


def dispatch(request: dict) -> dict:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    if not isinstance(params, dict):
        return _error(request_id, "bad_request", "params must be an object")
    try:
        if method == "health":
            result = health()
        elif method == "version":
            result = version()
        elif method == "list_profiles":
            result = list_profiles_cmd(params)
        elif method == "import_raw":
            result = import_raw_cmd(params)
        elif method == "preview":
            result = preview_cmd(params)
        else:
            return _error(request_id, "unknown_method", f"unknown method {method!r}")
        return _ok(request_id, result)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        return _error(request_id, "runtime_error", f"{type(exc).__name__}: {exc}")


def serve(protocol_out=None) -> None:
    """Read one JSON object per line and write one JSON object per line."""
    if protocol_out is None:
        protocol_out = sys.stdout
    # Library prints must not share the protocol stream.
    saved_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                response = _error(None, "bad_request", "expected a JSON object")
            else:
                if not isinstance(request, dict):
                    response = _error(None, "bad_request", "expected a JSON object")
                else:
                    response = dispatch(request)
            protocol_out.write(json.dumps(response, separators=(",", ":")) + "\n")
            protocol_out.flush()
    finally:
        sys.stdout = saved_stdout


def run_self_test(*, skip_preview: bool = False) -> int:
    failures: list[str] = []

    def check(name: str, request: dict):
        response = dispatch(request)
        if not response.get("ok"):
            message = f"{name}: {response.get('error')}"
            failures.append(message)
            print(f"FAIL {message}", file=sys.stderr)
            return None
        print(f"ok   {name}", file=sys.stderr)
        return response["result"]

    check("health", {"id": 1, "method": "health", "params": {}})
    version_info = check("version", {"id": 2, "method": "version", "params": {}})
    if version_info is not None:
        print(
            f"     spektrafilm {version_info.get('spektrafilm')}  python {version_info.get('python')}",
            file=sys.stderr,
        )
    films = check(
        "list_film",
        {"id": 3, "method": "list_profiles", "params": {"kind": "film"}},
    )
    papers = check(
        "list_print",
        {"id": 4, "method": "list_profiles", "params": {"kind": "print"}},
    )
    if films is not None:
        print(f"     film profiles: {len(films['profiles'])}", file=sys.stderr)
    if papers is not None:
        print(f"     print profiles: {len(papers['profiles'])}", file=sys.stderr)

    if not skip_preview and films and papers:
        film_ids = {item["id"] for item in films["profiles"]}
        paper_ids = {item["id"] for item in papers["profiles"]}
        film_profile = "kodak_portra_400" if "kodak_portra_400" in film_ids else films["profiles"][0]["id"]
        print_profile = (
            "kodak_portra_endura"
            if "kodak_portra_endura" in paper_ids
            else papers["profiles"][0]["id"]
        )
        preview = check(
            "preview",
            {
                "id": 5,
                "method": "preview",
                "params": {
                    "film_profile": film_profile,
                    "print_profile": print_profile,
                    "max_size": 32,
                },
            },
        )
        if preview is not None:
            raw = base64.b64decode(preview["png_base64"])
            if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                failures.append("preview bytes are not a PNG")
                print("FAIL preview bytes are not a PNG", file=sys.stderr)
            else:
                print(
                    f"     preview {preview['width']}x{preview['height']} "
                    f"in {preview['elapsed_ms']} ms ({film_profile} / {print_profile})",
                    file=sys.stderr,
                )

    if failures:
        print(f"{len(failures)} failure(s)", file=sys.stderr)
        return 1
    print("self-test passed", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        return run_self_test(skip_preview="--skip-preview" in args)
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
