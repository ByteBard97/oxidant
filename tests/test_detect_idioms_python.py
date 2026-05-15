"""Tests for the Python idiom detector script."""
import json
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "phase_a_scripts" / "detect_idioms_python.py"
_EXTRACTOR = Path(__file__).parent.parent / "phase_a_scripts" / "extract_ast_python.py"


def _extract_and_detect(source: str, tmp_path: Path) -> dict:
    src = tmp_path / "src"
    src.mkdir()
    (src / "sample.py").write_text(source)
    manifest_path = tmp_path / "manifest.json"
    subprocess.run(
        [sys.executable, str(_EXTRACTOR),
         "--source-root", str(src), "--out", str(manifest_path)],
        check=True, capture_output=True,
    )
    subprocess.run(
        [sys.executable, str(_SCRIPT), "--manifest", str(manifest_path)],
        check=True, capture_output=True,
    )
    return json.loads(manifest_path.read_text())


def _idioms(manifest: dict, name_fragment: str) -> list[str]:
    node = next(n for n in manifest["nodes"].values() if name_fragment in n["node_id"])
    return node["idioms_needed"]


def test_list_comprehension_detected(tmp_path):
    manifest = _extract_and_detect(
        "def foo(xs: list[int]) -> list[int]:\n    return [x * 2 for x in xs]\n",
        tmp_path,
    )
    assert "list_comprehension" in _idioms(manifest, "foo")


def test_optional_type_detected(tmp_path):
    manifest = _extract_and_detect(
        "from typing import Optional\ndef foo(x: Optional[int]) -> None:\n    pass\n",
        tmp_path,
    )
    assert "optional_type" in _idioms(manifest, "foo")


def test_optional_union_syntax_detected(tmp_path):
    manifest = _extract_and_detect(
        "def foo(x: int | None) -> None:\n    pass\n",
        tmp_path,
    )
    assert "optional_type" in _idioms(manifest, "foo")


def test_generator_function_detected(tmp_path):
    manifest = _extract_and_detect(
        "def foo():\n    yield 1\n    yield 2\n",
        tmp_path,
    )
    assert "generator_function" in _idioms(manifest, "foo")


def test_format_string_detected(tmp_path):
    manifest = _extract_and_detect(
        'def foo(x: int) -> str:\n    return f"value={x}"\n',
        tmp_path,
    )
    assert "format_string" in _idioms(manifest, "foo")


def test_none_check_detected(tmp_path):
    manifest = _extract_and_detect(
        "def foo(x):\n    if x is None:\n        return 0\n    return x\n",
        tmp_path,
    )
    assert "none_check" in _idioms(manifest, "foo")


def test_isinstance_check_detected(tmp_path):
    manifest = _extract_and_detect(
        "def foo(x):\n    if isinstance(x, int):\n        return x\n    return 0\n",
        tmp_path,
    )
    assert "isinstance_check" in _idioms(manifest, "foo")


def test_multiple_return_detected(tmp_path):
    manifest = _extract_and_detect(
        "def foo(x: int) -> tuple[int, str]:\n    return x, str(x)\n",
        tmp_path,
    )
    assert "multiple_return" in _idioms(manifest, "foo")


def test_no_false_positives_on_simple_fn(tmp_path):
    manifest = _extract_and_detect(
        "def add(a: int, b: int) -> int:\n    return a + b\n",
        tmp_path,
    )
    assert _idioms(manifest, "add") == []


def test_svgwrite_import_detected(tmp_path):
    manifest = _extract_and_detect(
        "import svgwrite\ndef render(dwg) -> None:\n    g = dwg.g(id='layer')\n    dwg.add(g)\n",
        tmp_path,
    )
    assert "svgwrite_buffer" in _idioms(manifest, "render")


def test_svgwrite_from_import_detected(tmp_path):
    # import at module level won't appear in each function's source_text snippet,
    # but attribute calls (dwg.add, dwg.g) in the body will trigger the detector.
    manifest = _extract_and_detect(
        "from svgwrite.container import Group\ndef render(dwg) -> None:\n    g = dwg.g(id='x')\n    dwg.add(g)\n",
        tmp_path,
    )
    assert "svgwrite_buffer" in _idioms(manifest, "render")


def test_svgwrite_method_call_detected(tmp_path):
    manifest = _extract_and_detect(
        "def render(dwg) -> None:\n    g = dwg.g(id='x')\n    dwg.add(g)\n",
        tmp_path,
    )
    assert "svgwrite_buffer" in _idioms(manifest, "render")


def test_svgwrite_not_on_plain_fn(tmp_path):
    manifest = _extract_and_detect(
        "def add(a: int, b: int) -> int:\n    return a + b\n",
        tmp_path,
    )
    assert "svgwrite_buffer" not in _idioms(manifest, "add")
