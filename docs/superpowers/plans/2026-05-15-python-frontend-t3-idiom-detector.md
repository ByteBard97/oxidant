# Task 3: Python Idiom Detector

**Part of:** [Python→Rust Frontend](2026-05-15-python-frontend-overview.md) — do Task 2 first.

**Goal:** Create `phase_a_scripts/detect_idioms_python.py` — tags each manifest node with Python-specific idiom names that require special Rust thought. Updates `idioms_needed` in the manifest in-place.

**Files:**
- Create: `phase_a_scripts/detect_idioms_python.py`
- Create: `tests/test_detect_idioms_python.py`

---

- [ ] **Step 1: Write the failing tests**

Create `tests/test_detect_idioms_python.py`:

```python
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
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
python -m pytest tests/test_detect_idioms_python.py -v
```

Expected: ERROR (script doesn't exist yet).

- [ ] **Step 3: Create `phase_a_scripts/detect_idioms_python.py`**

```python
#!/usr/bin/env python3
"""Phase A2 for Python sources: tag idioms on an existing manifest.

Reads conversion_manifest.json, walks each node's source_text with ast,
appends detected idioms to idioms_needed, writes manifest back in place.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def _detect_idioms(source_text: str, param_types: dict) -> list[str]:
    """Return list of idiom tags for a single node's source text."""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return []

    idioms: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)):
            idioms.add("list_comprehension")
        if isinstance(node, (ast.GeneratorExp, ast.Yield, ast.YieldFrom)):
            idioms.add("generator_function")
        if isinstance(node, ast.JoinedStr):
            idioms.add("format_string")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "isinstance":
                idioms.add("isinstance_check")
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(comp, ast.Constant) and comp.value is None:
                    idioms.add("none_check")

    for t in list(param_types.values()) + [source_text]:
        if t and ("Optional[" in t or "| None" in t or "None |" in t):
            idioms.add("optional_type")

    if "-> tuple[" in source_text or "-> Tuple[" in source_text:
        idioms.add("multiple_return")

    return sorted(idioms)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())
    nodes = manifest.get("nodes", {})

    tagged = 0
    for node in nodes.values():
        existing = set(node.get("idioms_needed", []))
        detected = _detect_idioms(node.get("source_text", ""), node.get("parameter_types", {}))
        node["idioms_needed"] = sorted(existing | set(detected))
        if detected:
            tagged += 1

    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Tagged idioms on {tagged}/{len(nodes)} nodes → {manifest_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_detect_idioms_python.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add phase_a_scripts/detect_idioms_python.py tests/test_detect_idioms_python.py
git commit -m "feat: Python idiom detector for Phase A (detect_idioms_python.py)"
```

**Next:** [Task 4 — Python type mapper](2026-05-15-python-frontend-t4-type-mapper.md)
