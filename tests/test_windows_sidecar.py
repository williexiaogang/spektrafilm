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
