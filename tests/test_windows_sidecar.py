"""Protocol tests for the Windows Python sidecar.

Profile listing and preview call the real runtime when its dependencies
import. The framing tests always run.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SIDECAR = Path(__file__).resolve().parents[1] / "apps" / "windows" / "sidecar" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("spektrafilm_windows_sidecar", SIDECAR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server = load_server()

@pytest.mark.parametrize("same_size", [False, True])
def test_raw_cache_reloads_replaced_files_but_reuses_unchanged_files(tmp_path, monkeypatch, same_size):
    import os
    import numpy as np

    path = tmp_path / "frame.dng"
    path.write_bytes(b"first")
    loads = []

    def load(path_text, settings):
        content = Path(path_text).read_bytes()
        loads.append(content)
        return np.full((2, 2, 3), len(loads) * 0.1), None

    monkeypatch.setattr(server, "_RAW_CACHE", None)
    monkeypatch.setattr(server, "load_raw_image", load)
    request = {"source": "raw", "image_path": str(path)}
    first = server._resolve_preview_image(request)
    cached = server._resolve_preview_image(request)
    assert first["raw_cache"] == "miss"
    assert cached["raw_cache"] == "hit"
    assert len(loads) == 1

    previous = path.stat()
    path.write_bytes(b"other" if same_size else b"replacement raw contents")
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns + 1_000_000_000))
    replaced = server._resolve_preview_image(request)
    assert replaced["raw_cache"] == "miss"
    assert len(loads) == 2
    assert not np.array_equal(first["image"], replaced["image"])
    assert server._resolve_preview_image(request)["raw_cache"] == "hit"


def test_raw_changed_during_import_is_not_cached_as_the_new_file(tmp_path, monkeypatch):
    import numpy as np

    path = tmp_path / "frame.dng"
    path.write_bytes(b"original")
    loads = []

    def load(path_text, settings):
        loads.append(Path(path_text).read_bytes())
        if len(loads) == 1:
            path.write_bytes(b"replacement written during the decode")
        return np.full((2, 2, 3), len(loads) * 0.1), None

    monkeypatch.setattr(server, "_RAW_CACHE", None)
    monkeypatch.setattr(server, "load_raw_image", load)
    server.import_raw_cmd({"path": str(path)})
    result = server._resolve_preview_image({"source": "raw", "image_path": str(path)})
    assert result["raw_cache"] == "miss"
    assert len(loads) == 2
    assert loads[0] != loads[1]


def test_png_encoder_writes_a_header_and_rejects_a_short_buffer():
    png = server.encode_png_rgb8(bytes([10, 20, 30, 40, 50, 60]), 2, 1)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert png.endswith(b"IEND\xaeB`\x82")
    with pytest.raises(ValueError):
        server.encode_png_rgb8(b"\x00\x00\x00", 2, 1)


def test_dispatch_health_version_and_unknown_method():
    health = server.dispatch({"id": 4, "method": "health", "params": {}})
    assert health["ok"] is True
    assert health["id"] == 4
    assert health["result"]["status"] == "ok"
    assert health["result"]["protocol"] == 1

    version = server.dispatch({"id": "v", "method": "version"})
    assert version["ok"] is True
    assert version["result"]["spektrafilm"]

    unknown = server.dispatch({"id": 5, "method": "nope", "params": {}})
    assert unknown["ok"] is False
    assert unknown["error"]["code"] == "unknown_method"

    bad_kind = server.dispatch({"id": 6, "method": "list_profiles", "params": {"kind": "lens"}})
    assert bad_kind["ok"] is False
    assert bad_kind["error"]["code"] == "runtime_error"


def test_stdio_health_roundtrip():
    proc = subprocess.Popen(
        [sys.executable, "-u", str(SIDECAR)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps({"id": 7, "method": "health", "params": {}}) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    proc.stdin.close()
    stderr = proc.stderr.read() if proc.stderr is not None else ""
    proc.wait(timeout=10)

    payload = json.loads(line)
    assert payload["id"] == 7
    assert payload["ok"] is True
    assert payload["result"]["sidecar"] == "spektrafilm-windows"
    assert "Traceback" not in stderr


def test_list_profiles_and_builtin_preview_against_runtime():
    try:
        server.ensure_import_path()
        import spektrafilm  # noqa: F401
        from spektrafilm.profiles.io import list_profiles
    except Exception as exc:
        pytest.skip(f"spektrafilm runtime dependencies are not installed: {exc}")

    assert list_profiles()

    films = server.dispatch({"id": 1, "method": "list_profiles", "params": {"kind": "film"}})
    papers = server.dispatch({"id": 2, "method": "list_profiles", "params": {"kind": "print"}})
    assert films["ok"] is True, films
    assert papers["ok"] is True, papers
    film_ids = {item["id"] for item in films["result"]["profiles"]}
    paper_ids = {item["id"] for item in papers["result"]["profiles"]}
    assert "kodak_portra_400" in film_ids
    assert "kodak_portra_endura" in paper_ids
    assert all(item["stage"] == "filming" for item in films["result"]["profiles"])
    assert all(item["stage"] == "printing" for item in papers["result"]["profiles"])

    preview = server.dispatch(
        {
            "id": 3,
            "method": "preview",
            "params": {
                "film_profile": "kodak_portra_400",
                "print_profile": "kodak_portra_endura",
                "max_size": 24,
                "exposure_compensation_ev": 0.0,
            },
        }
    )
    assert preview["ok"] is True, preview.get("error")
    result = preview["result"]
    raw = __import__("base64").b64decode(result["png_base64"])
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert result["width"] >= 1 and result["height"] >= 1
    assert result["source"] == "builtin-chart"
    assert result["output_color_space"] == "sRGB"
    assert result["preview_mode"] is True
    assert result["render_mode"] == "preview"
    reference = __import__("base64").b64decode(result["reference_png_base64"])
    assert reference.startswith(b"\x89PNG\r\n\x1a\n")


def test_import_raw_rejects_a_missing_file_and_unknown_white_balance(tmp_path):
    missing = tmp_path / "missing.nef"
    missing_response = server.dispatch(
        {
            "id": 8,
            "method": "import_raw",
            "params": {"path": str(missing), "white_balance": "as_shot"},
        }
    )
    assert missing_response["ok"] is False
    assert missing_response["error"]["code"] == "runtime_error"
    assert "not found" in missing_response["error"]["message"].lower()

    bad_balance = server.dispatch(
        {
            "id": 9,
            "method": "import_raw",
            "params": {"path": str(missing), "white_balance": "flash"},
        }
    )
    assert bad_balance["ok"] is False
    assert "white_balance" in bad_balance["error"]["message"]

    bad_mode = server.dispatch(
        {"id": 10, "method": "preview", "params": {"render_mode": "print"}}
    )
    assert bad_mode["ok"] is False
    assert "render_mode" in bad_mode["error"]["message"]


def test_raw_cache_and_scan_params_when_runtime_imports(tmp_path):
    try:
        server.ensure_import_path()
        from spektrafilm import init_params  # noqa: F401
    except Exception as exc:
        pytest.skip(f"spektrafilm runtime dependencies are not installed: {exc}")

    raw_path = tmp_path / "frame.dng"
    raw_path.write_bytes(b"not-a-real-raw")
    loads = {"count": 0}
    seen = {}

    def fake_load(path, settings):
        loads["count"] += 1
        import numpy as np

        assert path == str(raw_path)
        assert settings["white_balance"] == "custom"
        assert settings["temperature"] == 3200.0
        image = np.full((6, 8, 3), 0.25, dtype=np.float64)
        return image, "Test lens @ 50mm f/2.0"

    def fake_simulate(image, params, render_mode):
        seen["render_mode"] = render_mode
        seen["preview_mode"] = params.settings.preview_mode
        seen["exposure"] = params.camera.exposure_compensation_ev
        seen["y"] = params.enlarger.y_filter_shift
        seen["m"] = params.enlarger.m_filter_shift
        seen["scatter"] = params.film_render.halation.scatter_amount
        seen["scatter_size"] = params.film_render.halation.scatter_spatial_scale
        seen["halation"] = params.film_render.halation.halation_amount
        seen["halation_size"] = params.film_render.halation.halation_spatial_scale
        seen["halation_active"] = params.film_render.halation.active
        seen["input"] = params.io.input_color_space
        return image

    original_load = server.load_raw_image
    original_run = server.run_simulation
    server.load_raw_image = fake_load
    server.run_simulation = fake_simulate
    server._RAW_CACHE = None
    try:
        imported = server.dispatch(
            {
                "id": 1,
                "method": "import_raw",
                "params": {
                    "path": str(raw_path),
                    "white_balance": "custom",
                    "temperature": 3200,
                    "tint": 1.1,
                    "lens_correction": False,
                },
            }
        )
        assert imported["ok"] is True, imported
        assert imported["result"]["width"] == 8
        assert imported["result"]["height"] == 6
        assert imported["result"]["lens_summary"] == "Test lens @ 50mm f/2.0"
        assert imported["result"]["input_color_space"] == "ProPhoto RGB"
        assert loads["count"] == 1

        preview = server.dispatch(
            {
                "id": 2,
                "method": "preview",
                "params": {
                    "source": "raw",
                    "image_path": str(raw_path),
                    "white_balance": "custom",
                    "temperature": 3200,
                    "tint": 1.1,
                    "render_mode": "scan",
                    "film_profile": "kodak_portra_400",
                    "print_profile": "kodak_portra_endura",
                    "exposure_compensation_ev": -0.5,
                    "y_filter_shift": 15,
                    "m_filter_shift": -8,
                    "halation_active": True,
                    "scatter_amount": 0.4,
                    "scatter_spatial_scale": 1.5,
                    "halation_amount": 0.7,
                    "halation_spatial_scale": 1.2,
                    "max_size": 24,
                },
            }
        )
        assert preview["ok"] is True, preview
        assert loads["count"] == 1
        assert preview["result"]["raw_cache"] == "hit"
        assert preview["result"]["render_mode"] == "scan"
        assert preview["result"]["preview_mode"] is False
        assert seen == {
            "render_mode": "scan",
            "preview_mode": False,
            "exposure": -0.5,
            "y": 15.0,
            "m": -8.0,
            "scatter": 0.4,
            "scatter_size": 1.5,
            "halation": 0.7,
            "halation_size": 1.2,
            "halation_active": True,
            "input": "ProPhoto RGB",
        }
        assert preview["result"]["png_base64"]
    finally:
        server.load_raw_image = original_load
        server.run_simulation = original_run
        server._RAW_CACHE = None


def test_stock_thumb_is_cached_and_preview_thumbnails_varies_one_axis():
    try:
        server.ensure_import_path()
        from spektrafilm import init_params  # noqa: F401
    except Exception as exc:
        pytest.skip(f"spektrafilm runtime dependencies are not installed: {exc}")

    calls = {"count": 0}

    def fake_simulate(image, params, render_mode):
        calls["count"] += 1
        assert render_mode == "preview"
        assert params.settings.preview_mode is True
        assert params.camera.exposure_compensation_ev == 0.0
        return image

    original = server.run_simulation
    server.run_simulation = fake_simulate
    server._THUMB_CACHE.clear()
    try:
        bad_kind = server.dispatch(
            {"id": 1, "method": "preview_thumbnails", "params": {"kind": "lens", "ids": ["kodak_portra_400"]}}
        )
        assert bad_kind["ok"] is False
        assert "kind" in bad_kind["error"]["message"]

        missing = server.dispatch(
            {
                "id": 2,
                "method": "stock_thumb",
                "params": {
                    "film_profile": "not_a_stock",
                    "print_profile": "kodak_portra_endura",
                    "max_size": 48,
                },
            }
        )
        assert missing["ok"] is False
        assert calls["count"] == 0

        first = server.dispatch(
            {
                "id": 3,
                "method": "stock_thumb",
                "params": {
                    "film_profile": "kodak_portra_400",
                    "print_profile": "kodak_portra_endura",
                    "max_size": 64,
                },
            }
        )
        assert first["ok"] is True, first
        assert first["result"]["cached"] is False
        assert first["result"]["width"] >= 64
        png = __import__("base64").b64decode(first["result"]["png_base64"])
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert calls["count"] == 1

        again = server.dispatch(
            {
                "id": 4,
                "method": "stock_thumb",
                "params": {
                    "film_profile": "kodak_portra_400",
                    "print_profile": "kodak_portra_endura",
                    "max_size": 64,
                },
            }
        )
        assert again["ok"] is True
        assert again["result"]["cached"] is True
        assert again["result"]["png_base64"] == first["result"]["png_base64"]
        assert calls["count"] == 1

        batch = server.dispatch(
            {
                "id": 5,
                "method": "preview_thumbnails",
                "params": {
                    "kind": "print",
                    "film_profile": "kodak_portra_400",
                    "ids": ["kodak_portra_endura", "kodak_supra_endura"],
                    "max_size": 64,
                },
            }
        )
        assert batch["ok"] is True, batch
        thumbs = batch["result"]["thumbs"]
        assert [item["print_profile"] for item in thumbs] == [
            "kodak_portra_endura",
            "kodak_supra_endura",
        ]
        assert thumbs[0]["cached"] is True
        assert thumbs[1]["cached"] is False
        assert calls["count"] == 2
    finally:
        server.run_simulation = original
        server._THUMB_CACHE.clear()


def test_reference_png_converts_prophoto_primaries_to_srgb():
    import base64
    import colour
    import numpy as np
    from PIL import Image
    from io import BytesIO

    image = np.array([[[0.2, 0.25, 0.3], [0.001, 0.001, 0.001]]])
    encoded = server._reference_png(image, 512, input_color_space="ProPhoto RGB")
    assert encoded is not None
    actual = np.asarray(Image.open(BytesIO(base64.b64decode(encoded))))
    expected = colour.RGB_to_RGB(
        image, "ProPhoto RGB", "sRGB", apply_cctf_decoding=False, apply_cctf_encoding=True
    )
    expected = (np.clip(expected, 0, 1) * 255).astype(np.uint8)
    np.testing.assert_allclose(actual, expected, atol=1)
    old_gamma_only = (np.power(image, 1 / 2.2) * 255).astype(np.uint8)
    assert not np.allclose(actual, old_gamma_only, atol=1)


def test_reference_png_uses_srgb_transfer_and_can_decode_encoded_input():
    import base64
    import numpy as np
    from PIL import Image
    from io import BytesIO

    linear = np.full((2, 2, 3), 0.001)
    result = server._reference_png(linear, 512, input_color_space="sRGB")
    actual = np.asarray(Image.open(BytesIO(base64.b64decode(result))))
    # The sRGB toe is 12.92 * L, not L ** (1 / 2.2).
    np.testing.assert_allclose(actual, 3, atol=1)

    encoded = np.full((2, 2, 3), 0.5)
    result = server._reference_png(
        encoded, 512, input_color_space="sRGB", input_cctf_decoding=True
    )
    actual = np.asarray(Image.open(BytesIO(base64.b64decode(result))))
    np.testing.assert_allclose(actual, 127, atol=1)


def test_linear_file_honors_selected_color_space(monkeypatch):
    import numpy as np

    image = np.full((4, 6, 3), 0.18)
    monkeypatch.setattr(server, "_load_linear_image", lambda path: image)
    prepared = server._resolve_preview_image({
        "source": "path", "image_path": "linear.exr", "input_color_space": "ACEScg",
    })
    assert prepared["image"] is image
    assert prepared["input_color_space"] == "ACEScg"
    assert prepared["input_cctf_decoding"] is False


def test_first_request_in_a_fresh_process_can_open_a_linear_file(tmp_path):
    import numpy as np
    import OpenImageIO as oiio

    path = tmp_path / "linear.tif"
    output = oiio.ImageOutput.create(str(path))
    assert output.open(str(path), oiio.ImageSpec(16, 8, 3, oiio.FLOAT))
    assert output.write_image(np.full((8, 16, 3), 0.18, dtype=np.float32))
    output.close()
    request = {"id": 1, "method": "preview", "params": {
        "source": "path", "image_path": str(path), "input_color_space": "sRGB", "max_size": 16,
    }}
    # No preceding version/list_profiles request may prepare sys.path for us.
    process = subprocess.run(
        [sys.executable, "-u", str(SIDECAR)], input=json.dumps(request) + "\n",
        capture_output=True, text=True, cwd=tmp_path, timeout=90,
    )
    assert process.returncode == 0, process.stderr
    response = json.loads(process.stdout)
    assert response["ok"], response
    assert response["result"]["source"] == "path"
    assert response["result"]["input_color_space"] == "sRGB"


def test_preview_preserves_larger_size_and_reference_color_space(monkeypatch):
    import numpy as np
    from spektrafilm import init_params  # noqa: F401

    image = np.full((16, 1024, 3), 0.18)
    monkeypatch.setattr(server, "_resolve_preview_image", lambda params: {
        "image": image, "source": "path", "image_path": "linear.exr",
        "input_color_space": "ACEScg", "input_cctf_decoding": False,
        "raw_cache": None, "white_balance": None, "lens_summary": None,
    })
    monkeypatch.setattr(server, "run_simulation", lambda image, params, mode: image)
    seen = {}

    def reference(image, size, **kwargs):
        seen.update({"size": size, **kwargs})
        return "reference"

    monkeypatch.setattr(server, "_reference_png", reference)
    result = server.preview_cmd({"max_size": 1024})
    assert result["max_size"] == 1024
    assert seen == {"size": 1024, "input_color_space": "ACEScg", "input_cctf_decoding": False}
    assert server.preview_cmd({})["max_size"] == 512
    assert server.preview_cmd({"max_size": 100000})["max_size"] == 2048
