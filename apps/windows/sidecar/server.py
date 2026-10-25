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
SIDECAR_VERSION = "0.1.0"

_PROFILE_SUMMARIES: list[dict] | None = None


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


def preview_cmd(params: dict) -> dict:
    """Run one preview through the existing runtime.

    ``init_params`` plus ``simulate_preview`` are the public entry points.
    ``settings.preview_mode`` is the runtime's own fast-preview switch.
    """
    import time

    film_profile = str(params.get("film_profile") or "kodak_portra_400")
    print_profile = str(params.get("print_profile") or "kodak_portra_endura")
    image_path = params.get("image_path")
    if isinstance(image_path, str):
        image_path = image_path.strip() or None
    elif image_path is not None:
        raise ValueError("image_path must be a string or null")

    max_size = _clamp_int(params.get("max_size"), default=48, lo=16, hi=256)
    exposure = _clamp_float(
        params.get("exposure_compensation_ev"),
        default=0.0,
        lo=-5.0,
        hi=5.0,
    )

    ensure_import_path()
    from spektrafilm import init_params, simulate_preview

    if image_path:
        image = _load_linear_image(image_path)
        source = "path"
        input_color_space = str(params.get("input_color_space") or "ProPhoto RGB")
        input_cctf_decoding = bool(params.get("input_cctf_decoding") or False)
    else:
        image = _builtin_chart()
        source = "builtin-chart"
        input_color_space = "sRGB"
        input_cctf_decoding = False

    runtime_params = init_params(
        film_profile=film_profile,
        print_profile=print_profile,
    )
    runtime_params.settings.preview_mode = True
    runtime_params.settings.preview_max_size = max_size
    runtime_params.camera.exposure_compensation_ev = exposure
    runtime_params.io.input_color_space = input_color_space
    runtime_params.io.input_cctf_decoding = input_cctf_decoding
    runtime_params.io.output_color_space = "sRGB"
    runtime_params.io.output_cctf_encoding = True

    started = time.perf_counter()
    with _silence_stdout():
        result = simulate_preview(image, runtime_params)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    png, width, height = _result_to_png(result)
    return {
        "film_profile": film_profile,
        "print_profile": print_profile,
        "source": source,
        "image_path": image_path,
        "width": width,
        "height": height,
        "mime": "image/png",
        "png_base64": base64.b64encode(png).decode("ascii"),
        "elapsed_ms": elapsed_ms,
        "preview_mode": True,
        "max_size": max_size,
        "exposure_compensation_ev": exposure,
        "input_color_space": input_color_space,
        "output_color_space": "sRGB",
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
