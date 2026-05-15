# Task 8: End-to-End Smoke Test

**Part of:** [Python→Rust Frontend](2026-05-15-python-frontend-overview.md) — do Tasks 1–7 first.

**Goal:** Validate the full Phase A pipeline on `fit_text_to_cell` — the concrete test target from the agent brief. Does NOT invoke Phase B (requires Claude API). Verifies the manifest is correctly structured for Phase B to consume, then runs the full test suite for regressions.

**Files:**
- Create: `tests/test_python_e2e.py`

---

- [ ] **Step 1: Create `tests/test_python_e2e.py`**

```python
"""End-to-end test: Python extractor + idiom detector → Phase B-ready manifest.

Uses fit_text_to_cell from the agent brief. Does not invoke Phase B.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_EXTRACTOR = Path(__file__).parent.parent / "phase_a_scripts" / "extract_ast_python.py"
_IDIOM_DETECTOR = Path(__file__).parent.parent / "phase_a_scripts" / "detect_idioms_python.py"

FIT_TEXT_SOURCE = '''\
def fit_text_to_cell(
    text: str,
    max_width: float,
    max_height: float,
    base_font_size: float = 10,
    min_font_size: float = 7,
    chars_per_px: float = 0.165,
) -> tuple[list[str], float]:
    """Fit text into a cell by word wrapping and shrinking font if needed."""
    if not text:
        return ([""], base_font_size)
    font_size = base_font_size
    while font_size >= min_font_size:
        scale_factor = font_size / 10.0
        chars_per_line = int(max_width * chars_per_px / scale_factor)
        if chars_per_line < 3:
            chars_per_line = 3
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip() if current_line else word
            if len(test_line) <= chars_per_line:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        line_height = font_size * 1.2
        total_height = len(lines) * line_height
        if total_height <= max_height:
            return (lines, font_size)
        font_size -= 1
    return (lines[:int(max_height / (min_font_size * 1.2))], min_font_size)
'''


@pytest.fixture
def fit_text_manifest(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "title_block.py").write_text(FIT_TEXT_SOURCE)
    manifest_path = tmp_path / "manifest.json"
    subprocess.run(
        [sys.executable, str(_EXTRACTOR),
         "--source-root", str(src), "--out", str(manifest_path)],
        check=True, capture_output=True,
    )
    subprocess.run(
        [sys.executable, str(_IDIOM_DETECTOR), "--manifest", str(manifest_path)],
        check=True, capture_output=True,
    )
    return json.loads(manifest_path.read_text())


def test_node_extracted(fit_text_manifest):
    assert any("fit_text_to_cell" in nid for nid in fit_text_manifest["nodes"]), \
        list(fit_text_manifest["nodes"].keys())


def test_parameter_types(fit_text_manifest):
    node = next(n for n in fit_text_manifest["nodes"].values() if "fit_text_to_cell" in n["node_id"])
    assert node["parameter_types"]["text"] == "str"
    assert node["parameter_types"]["max_width"] == "float"
    assert node["parameter_types"]["max_height"] == "float"


def test_return_type(fit_text_manifest):
    node = next(n for n in fit_text_manifest["nodes"].values() if "fit_text_to_cell" in n["node_id"])
    assert "tuple" in (node["return_type"] or "")


def test_complexity_reflects_branches(fit_text_manifest):
    node = next(n for n in fit_text_manifest["nodes"].values() if "fit_text_to_cell" in n["node_id"])
    # while + multiple if + for = > 4 branch points
    assert node["cyclomatic_complexity"] > 4


def test_idioms_tagged(fit_text_manifest):
    node = next(n for n in fit_text_manifest["nodes"].values() if "fit_text_to_cell" in n["node_id"])
    assert "multiple_return" in node["idioms_needed"]
    assert "format_string" in node["idioms_needed"]


def test_source_language_in_manifest(fit_text_manifest):
    assert fit_text_manifest["source_language"] == "python"


def test_node_id_convention(fit_text_manifest):
    """node_id must follow {file_slug}__{function_name} convention."""
    assert all("__" in nid for nid in fit_text_manifest["nodes"])
```

- [ ] **Step 2: Run the smoke test**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
python -m pytest tests/test_python_e2e.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 3: Run the full test suite for regressions**

```bash
python -m pytest tests/ -v --ignore=tests/test_serve_endpoints.py -x
```

(`test_serve_endpoints.py` requires a running server — skip it here.)

Expected: all tests PASS, no regressions from the TS path.

- [ ] **Step 4: Commit**

```bash
git add tests/test_python_e2e.py
git commit -m "test: end-to-end smoke test for Python extractor on fit_text_to_cell"
```

---

## Done

All 8 tasks complete. The pipeline now supports `source_language: "python"` in `oxidant.config.json`. To run Phase A on the flora-backend corpus:

```json
{
  "source_language": "python",
  "source_repo": "/Users/ceres/Desktop/flora/flora-backend/src/gis/pipeline/svg",
  "target_repo": "/Users/ceres/Desktop/flora/flora-studio/src-tauri",
  "crate_name": "flora-studio",
  "model_tiers": {"haiku": "claude-haiku-4-5-20251001", "sonnet": "claude-sonnet-4-6", "opus": "claude-opus-4-6"},
  "start_tier": "haiku",
  "max_attempts": {"haiku": 1, "sonnet": 1, "opus": 1},
  "review_mode": "auto"
}
```

Then: `oxidant phase-a --config oxidant_flora.config.json`
