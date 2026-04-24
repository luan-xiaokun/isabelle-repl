from __future__ import annotations

from pathlib import Path


def test_src_does_not_depend_on_tests_shared_helpers():
    src_root = Path(__file__).resolve().parents[3] / "src"
    forbidden = ("tests.shared", "shared.runtime_env", "shared.repair_fakes")

    for py_file in src_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, (
                f"{py_file} imports forbidden test helper {marker}"
            )
