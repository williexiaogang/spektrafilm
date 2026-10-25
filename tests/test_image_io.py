"""Image precision and native write-failure regressions."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile

from spektrafilm.utils import io


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16, np.uint32, np.float32, np.float64])
def test_load_normalizes_integer_formats_and_preserves_hdr_floats(tmp_path, dtype):
    if np.issubdtype(dtype, np.integer):
        maximum = np.iinfo(dtype).max
        pixel = np.array([0, maximum // 2, maximum], dtype=dtype)
        expected = pixel.astype(np.float64) / maximum
    else:
        pixel = np.array([-0.125, 0.123456789123, 4.0], dtype=dtype)
        expected = pixel.astype(np.float64)
    path = tmp_path / "source.tif"
    tifffile.imwrite(path, np.tile(pixel, (2, 2, 1)), photometric="rgb")

    actual = io.load_image_oiio(path)

    assert np.issubdtype(actual.dtype, np.floating)
    np.testing.assert_allclose(actual[0, 0], expected, rtol=1e-7, atol=1e-10)


@pytest.mark.parametrize("failed_stage,close_raises", [("open", False), ("write", False), ("close", False), ("write", True)])
def test_save_reports_native_errors_without_writing_an_unopened_output(monkeypatch, tmp_path, failed_stage, close_raises):
    calls = []

    class Output:
        def open(self, *args):
            calls.append("open")
            return failed_stage != "open"

        def write_image(self, *args):
            assert failed_stage != "open", "An unopened native output must never receive pixels"
            calls.append("write")
            return failed_stage != "write"

        def close(self):
            calls.append("close")
            if close_raises:
                raise RuntimeError("secondary close error")
            return failed_stage != "close"

        def geterror(self):
            return f"native {failed_stage} failure"

    monkeypatch.setattr(io.oiio, "ImageOutput", SimpleNamespace(create=lambda path: Output()))
    with pytest.raises(OSError, match=f"native {failed_stage} failure"):
        io.save_image_oiio(tmp_path / "out.tif", np.ones((2, 2, 3)))
    assert calls == (["open"] if failed_stage == "open" else ["open", "write", "close"])


def test_missing_output_parent_raises_instead_of_crashing_the_process(tmp_path):
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    environment = {**os.environ, "PYTHONPATH": source_root + os.pathsep + os.environ.get("PYTHONPATH", "")}
    code = """
import sys
import numpy as np
from spektrafilm.utils.io import save_image_oiio
try:
    save_image_oiio(sys.argv[1], np.ones((2, 2, 3)))
except OSError:
    print('write failure was reported safely')
else:
    raise AssertionError('The missing directory must not be reported as success')
"""
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", code, str(tmp_path / "missing" / "out.tif")],
        env=environment, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "reported safely" in result.stdout
