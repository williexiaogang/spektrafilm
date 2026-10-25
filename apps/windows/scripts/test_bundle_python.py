# SpektraFilm Windows edition.
# Licensed under the GNU General Public License v3.0 only.
"""Checks for the standalone runtime builder that do not need Windows."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import bundle_python  # noqa: E402


class LockTests(unittest.TestCase):
    def test_committed_lock_covers_direct_requirements(self) -> None:
        problems = bundle_python.check_lock(
            bundle_python.requirements_path(),
            bundle_python.lock_path(),
        )
        self.assertEqual(problems, [])

    def test_missing_direct_dependency_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            requirements = root / "requirements.in"
            lock = root / "lock.txt"
            requirements.write_text("numpy~=2.4\nrawpy~=0.26.1\n", encoding="utf-8")
            lock.write_text(
                "numpy==2.5.4 \\\n    --hash=sha256:" + ("a" * 64) + "\n",
                encoding="utf-8",
            )
            problems = bundle_python.check_lock(requirements, lock)
        self.assertEqual(problems, ["lock is missing rawpy"])


class SlimTests(unittest.TestCase):
    def test_slim_drops_pip_tk_and_package_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            site = prefix / "Lib" / "site-packages"
            (site / "pip").mkdir(parents=True)
            (site / "pip" / "__init__.py").write_text("x", encoding="utf-8")
            (site / "pip-1.0.dist-info").mkdir()
            (site / "numpy" / "tests").mkdir(parents=True)
            (site / "numpy" / "tests" / "test_foo.py").write_text("x", encoding="utf-8")
            (site / "numpy" / "__init__.py").write_text("x", encoding="utf-8")
            (site / "numpy" / "__pycache__").mkdir()
            (site / "numpy" / "__pycache__" / "x.pyc").write_bytes(b"pyc")
            (site / "demo.dist-info").mkdir()
            (site / "demo.dist-info" / "direct_url.json").write_text(
                json.dumps({"url": "file:///C:/Users/build/checkout"}),
                encoding="utf-8",
            )
            (prefix / "tcl" / "tcl8.6").mkdir(parents=True)
            (prefix / "tcl" / "tcl8.6" / "init.tcl").write_text("x", encoding="utf-8")
            (prefix / "Lib" / "tkinter").mkdir(parents=True)
            (prefix / "DLLs").mkdir()
            (prefix / "DLLs" / "_tkinter.pyd").write_bytes(b"dll")
            (prefix / "include").mkdir()
            (prefix / "include" / "Python.h").write_text("x", encoding="utf-8")

            removed_files, removed_bytes = bundle_python.slim_prefix(prefix)
            self.assertGreater(removed_files, 0)
            self.assertGreater(removed_bytes, 0)
            self.assertFalse((site / "pip").exists())
            self.assertFalse((site / "numpy" / "tests").exists())
            self.assertTrue((site / "numpy" / "__init__.py").is_file())
            self.assertFalse((site / "demo.dist-info" / "direct_url.json").exists())
            self.assertFalse((prefix / "tcl").exists())
            self.assertFalse((prefix / "Lib" / "tkinter").exists())
            self.assertFalse((prefix / "DLLs" / "_tkinter.pyd").exists())
            self.assertFalse((prefix / "include").exists())


class NoticeTests(unittest.TestCase):
    def test_notices_include_wheel_license_and_native_libraries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            (prefix / "LICENSE.txt").write_text("PSF LICENSE TEXT", encoding="utf-8")
            dist = prefix / "Lib" / "site-packages" / "rawpy-0.26.1.dist-info"
            licenses = dist / "licenses"
            licenses.mkdir(parents=True)
            (dist / "METADATA").write_text(
                "Metadata-Version: 2.1\nName: rawpy\nVersion: 0.26.1\nLicense: MIT\n\n",
                encoding="utf-8",
            )
            (licenses / "LICENSE").write_text("MIT wrapper text", encoding="utf-8")
            text = bundle_python.render_third_party_notices(
                prefix,
                "GNU GENERAL PUBLIC LICENSE",
                "CC BY-SA 4.0",
            )
        self.assertIn("GNU GENERAL PUBLIC LICENSE", text)
        self.assertIn("CC BY-SA 4.0", text)
        self.assertIn("PSF LICENSE TEXT", text)
        self.assertIn("rawpy 0.26.1", text)
        self.assertIn("MIT wrapper text", text)
        self.assertIn("LibRaw", text)
        self.assertIn("lensfun", text)
        self.assertIn("GPLv3", text)


if __name__ == "__main__":
    unittest.main()
