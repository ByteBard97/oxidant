"""Tests for the Python AST extractor script."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "phase_a_scripts" / "extract_ast_python.py"

SAMPLE_PY = '''\
def greet(name: str) -> str:
    return f"Hello, {name}"


class Counter:
    def __init__(self, start: int = 0) -> None:
        self.value = start

    def increment(self, by: int = 1) -> int:
        self.value += by
        return self.value
'''


def _run_extractor(source_root: Path, out: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT),
         "--source-root", str(source_root),
         "--out", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(out.read_text())


def test_free_function_extracted(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text(SAMPLE_PY)
    manifest = _run_extractor(src, tmp_path / "manifest.json")
    assert any("greet" in nid for nid in manifest["nodes"]), list(manifest["nodes"].keys())


def test_free_function_fields(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text(SAMPLE_PY)
    manifest = _run_extractor(src, tmp_path / "manifest.json")
    node = next(n for n in manifest["nodes"].values() if "greet" in n["node_id"])
    assert node["node_kind"] == "free_function"
    assert node["parameter_types"] == {"name": "str"}
    assert node["return_type"] == "str"
    assert node["line_start"] == 1


def test_class_extracted(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text(SAMPLE_PY)
    manifest = _run_extractor(src, tmp_path / "manifest.json")
    assert any("Counter" in nid for nid in manifest["nodes"]), list(manifest["nodes"].keys())


def test_method_extracted(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text(SAMPLE_PY)
    manifest = _run_extractor(src, tmp_path / "manifest.json")
    assert any("increment" in nid for nid in manifest["nodes"]), list(manifest["nodes"].keys())


def test_method_has_parent_class(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text(SAMPLE_PY)
    manifest = _run_extractor(src, tmp_path / "manifest.json")
    method = next(n for n in manifest["nodes"].values() if "increment" in n["node_id"])
    assert method["parent_class"] is not None
    assert "Counter" in method["parent_class"]


def test_manifest_schema_fields(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text(SAMPLE_PY)
    manifest = _run_extractor(src, tmp_path / "manifest.json")
    assert manifest.get("source_language") == "python"
    node = next(iter(manifest["nodes"].values()))
    for field in ("node_id", "source_file", "line_start", "line_end",
                  "source_text", "node_kind", "parameter_types", "return_type",
                  "type_dependencies", "call_dependencies", "callers",
                  "parent_class", "cyclomatic_complexity", "idioms_needed"):
        assert field in node, f"Missing field: {field}"


def test_cyclomatic_complexity_counted(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text('''\
def branchy(x: int) -> int:
    if x > 0:
        if x > 10:
            return 2
        return 1
    elif x < 0:
        return -1
    return 0
''')
    manifest = _run_extractor(src, tmp_path / "manifest.json")
    node = next(iter(manifest["nodes"].values()))
    assert node["cyclomatic_complexity"] >= 3


def test_call_dependency_detected(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text('''\
def helper(x: int) -> int:
    return x + 1

def caller(y: int) -> int:
    return helper(y)
''')
    manifest = _run_extractor(src, tmp_path / "manifest.json")
    caller_node = next(n for n in manifest["nodes"].values() if "caller" in n["node_id"])
    assert any("helper" in dep for dep in caller_node["call_dependencies"])


def test_skips_test_directories(tmp_path):
    """Files inside a 'tests' directory should not be extracted."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text("def real(): pass\n")
    tests_dir = src / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_hello.py").write_text("def test_real(): pass\n")
    manifest = _run_extractor(src, tmp_path / "manifest.json")
    assert not any("test_real" in nid for nid in manifest["nodes"]), list(manifest["nodes"].keys())
