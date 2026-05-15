# Task 2: Python AST Extractor

**Part of:** [Python→Rust Frontend](2026-05-15-python-frontend-overview.md) — do Task 1 first.

**Goal:** Create `phase_a_scripts/extract_ast_python.py` — a script that walks a Python source tree with stdlib `ast` and emits a `conversion_manifest.json` with the same schema as the TypeScript extractor.

**Files:**
- Create: `phase_a_scripts/extract_ast_python.py`
- Create: `tests/test_extract_ast_python.py`

---

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extract_ast_python.py`:

```python
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
```

- [ ] **Step 2: Run to confirm they all fail**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
python -m pytest tests/test_extract_ast_python.py -v
```

Expected: ERROR (script doesn't exist yet).

- [ ] **Step 3: Create `phase_a_scripts/extract_ast_python.py`**

```python
#!/usr/bin/env python3
"""Phase A1 for Python sources: extract AST and emit conversion_manifest.json.

Walks all .py files under --source-root, parses with stdlib ast,
emits a manifest with the same schema as extract_ast.ts.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path

# Directory names that are always skipped during tree walk.
_SKIP_DIRS: frozenset[str] = frozenset({
    "__pycache__", "tests", "test", "venv", ".venv", "node_modules",
    "dist", "build", ".git", ".mypy_cache", ".ruff_cache",
})


def _slug(path: str) -> str:
    """Convert a file path to a safe identifier prefix: 'foo/bar_baz.py' → 'bar_baz'."""
    stem = Path(path).stem
    return re.sub(r"[^a-z0-9_]", "_", stem.lower())


def _annotation_str(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _cyclomatic_complexity(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    count = 1
    for node in ast.walk(func_node):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.With,
                              ast.ExceptHandler, ast.AsyncFor, ast.AsyncWith)):
            count += 1
        elif isinstance(node, ast.BoolOp):
            count += len(node.values) - 1
        elif isinstance(node, ast.Match):
            count += len(node.cases)
    return count


def _collect_calls(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    names: list[str] = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.append(node.func.attr)
    return list(dict.fromkeys(names))


def _extract_file(py_path: Path, source_root: Path) -> list[dict]:
    try:
        source_text = py_path.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(py_path))
    except SyntaxError:
        return []

    rel_path = str(py_path.relative_to(source_root))
    file_slug = _slug(rel_path)
    lines = source_text.splitlines()
    nodes: list[dict] = []

    def _source_segment(node: ast.AST) -> str:
        start = getattr(node, "lineno", 1) - 1
        end = getattr(node, "end_lineno", start + 1)
        return "\n".join(lines[start:end])

    def _make_node(node_id, node_kind, ast_node, param_types, return_type,
                   parent_class, complexity, call_deps) -> dict:
        return {
            "node_id": node_id,
            "source_file": rel_path,
            "line_start": getattr(ast_node, "lineno", 1),
            "line_end": getattr(ast_node, "end_lineno", getattr(ast_node, "lineno", 1)),
            "source_text": _source_segment(ast_node),
            "node_kind": node_kind,
            "parameter_types": {k: v or "Any" for k, v in param_types.items()},
            "return_type": return_type,
            "type_dependencies": [],
            "call_dependencies": call_deps,
            "callers": [],
            "parent_class": parent_class,
            "cyclomatic_complexity": complexity,
            "idioms_needed": [],
        }

    def _params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str | None]:
        params: dict[str, str | None] = {}
        for arg in func.args.args:
            if arg.arg == "self":
                continue
            params[arg.arg] = _annotation_str(arg.annotation)
        if func.args.vararg:
            params[f"*{func.args.vararg.arg}"] = _annotation_str(func.args.vararg.annotation)
        if func.args.kwarg:
            params[f"**{func.args.kwarg.arg}"] = _annotation_str(func.args.kwarg.annotation)
        return params

    for top_node in ast.iter_child_nodes(tree):
        if isinstance(top_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nid = f"{file_slug}__{top_node.name}"
            nodes.append(_make_node(
                node_id=nid, node_kind="free_function", ast_node=top_node,
                param_types=_params(top_node),
                return_type=_annotation_str(top_node.returns),
                parent_class=None,
                complexity=_cyclomatic_complexity(top_node),
                call_deps=_collect_calls(top_node),
            ))

        elif isinstance(top_node, ast.ClassDef):
            class_nid = f"{file_slug}__{top_node.name}"
            nodes.append(_make_node(
                node_id=class_nid, node_kind="class", ast_node=top_node,
                param_types={}, return_type=None, parent_class=None,
                complexity=1, call_deps=[],
            ))
            for method in ast.iter_child_nodes(top_node):
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if method.name == "__init__":
                    kind = "constructor"
                else:
                    decorators = [ast.unparse(d) for d in method.decorator_list]
                    if "property" in decorators:
                        kind = "getter"
                    elif any(d.endswith(".setter") for d in decorators):
                        kind = "setter"
                    else:
                        kind = "method"
                nodes.append(_make_node(
                    node_id=f"{class_nid}__{method.name}",
                    node_kind=kind, ast_node=method,
                    param_types=_params(method),
                    return_type=_annotation_str(method.returns),
                    parent_class=class_nid,
                    complexity=_cyclomatic_complexity(method),
                    call_deps=_collect_calls(method),
                ))

    return nodes


def _walk_python_files(source_root: Path):
    for py_file in sorted(source_root.rglob("*.py")):
        parts = py_file.relative_to(source_root).parts[:-1]  # exclude filename
        if any(part in _SKIP_DIRS or part.startswith(".") for part in parts):
            continue
        yield py_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    source_root = Path(args.source_root).resolve()
    out_path = Path(args.out)

    all_nodes: dict[str, dict] = {}
    for py_file in _walk_python_files(source_root):
        for node in _extract_file(py_file, source_root):
            all_nodes[node["node_id"]] = node

    # Resolve call_dependencies to actual node_ids
    known_names: dict[str, str] = {nid.split("__")[-1]: nid for nid in all_nodes}
    for node in all_nodes.values():
        node["call_dependencies"] = [
            known_names[call]
            for call in node["call_dependencies"]
            if call in known_names and known_names[call] != node["node_id"]
        ]

    out_path.write_text(json.dumps({
        "version": "1.0",
        "source_language": "python",
        "source_repo": str(source_root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nodes": all_nodes,
    }, indent=2))
    print(f"Extracted {len(all_nodes)} nodes → {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_extract_ast_python.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add phase_a_scripts/extract_ast_python.py tests/test_extract_ast_python.py
git commit -m "feat: Python AST extractor for Phase A (extract_ast_python.py)"
```

**Next:** [Task 3 — Python idiom detector](2026-05-15-python-frontend-t3-idiom-detector.md)
