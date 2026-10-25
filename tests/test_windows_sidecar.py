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
