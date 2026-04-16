# Phase D — Integration Debug Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase D integration verification pipeline that runs `cargo build --release` on the fully-translated Rust project, parses build errors, identifies which translated files need re-translation, and writes `integration_report.json`.

**Architecture:** Two focused modules: `integration_debug.py` owns all logic (build runner, JSON error parser, manifest intersection, report generation); `cli.py` gets a new `phase-d` command. The module mirrors the Phase C pattern exactly — subprocess run → JSON stream parse → categorize → write report. Phase D does not invoke Claude; it only identifies the files that need to be fed back into Phase B.

**Tech Stack:** Python 3.11, `cargo build --release --message-format=json` (Rust toolchain), Pydantic v2 (manifest access via existing `oxidant.models.manifest`).

**Scope note:** The PRD describes three Phase D components: (1) integration debug — built here; (2) WASM equivalence harness (`equivalence_test.js`) — deferred, requires real translation output and `wasm-pack`; (3) proptest generation — deferred, requires a real Rust corpus to generate tests for. This plan covers (1) only.

**Working directory for all commands:** `.worktrees/feat-phase-d/`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/oxidant/integration/__init__.py` | empty package marker |
| Create | `src/oxidant/integration/integration_debug.py` | `BuildError`, `IntegrationReport`, `_parse_build_output()`, `_intersect_with_manifest()`, `run_full_build()`, `run_phase_d()` |
| Modify | `src/oxidant/cli.py` | Add `phase-d` command after `phase-c` |
| Create | `tests/test_integration_debug.py` | 11 tests covering all functions |

---

### Task 1: Build error parser + data classes

**Background:** `cargo build --release --message-format=json 2>&1` emits one JSON object per line (same stream format as `cargo clippy --message-format=json`). We filter for `"reason": "compiler-message"` lines where `message.level == "error"`. The `message.code.code` field has the Rust error code (e.g. `"E0412"`). `message.spans` provides file/line location (same structure as Phase C's clippy parser).

The manifest model is in `oxidant.models.manifest`. `Manifest.load(path)` returns a `Manifest` with a `nodes: dict[str, ConversionNode]`. Each `ConversionNode` has `source_file: str` and `status: NodeStatus`. `NodeStatus.CONVERTED = "converted"`.

**Files:**
- Create: `src/oxidant/integration/__init__.py`
- Create: `src/oxidant/integration/integration_debug.py`
- Create: `tests/test_integration_debug.py`

- [ ] **Step 1: Write failing tests for parser and data classes**

Create `tests/test_integration_debug.py`:

```python
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from oxidant.integration.integration_debug import (
    BuildError,
    IntegrationReport,
    _parse_build_output,
)


def _make_compiler_message(
    code: str = "E0412",
    level: str = "error",
    message: str = "cannot find type `Foo`",
    file_name: str = "src/foo.rs",
    line_start: int = 5,
    column_start: int = 1,
) -> str:
    """Build a single cargo --message-format=json compiler-message line."""
    return json.dumps({
        "reason": "compiler-message",
        "message": {
            "level": level,
            "message": message,
            "code": {"code": code},
            "spans": [{
                "file_name": file_name,
                "line_start": line_start,
                "column_start": column_start,
                "is_primary": True,
            }],
            "children": [],
            "rendered": f"error[{code}]: {message}\n",
        }
    })


def _fake_run(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


# --- _parse_build_output ---

def test_parse_build_output_empty_returns_no_errors():
    assert _parse_build_output("") == []


def test_parse_build_output_extracts_error():
    line = _make_compiler_message(code="E0412", message="cannot find type `Foo`", file_name="src/bar.rs")
    errors = _parse_build_output(line)
    assert len(errors) == 1
    assert errors[0].error_code == "E0412"
    assert errors[0].file_name == "src/bar.rs"
    assert errors[0].message == "cannot find type `Foo`"
    assert errors[0].line_start == 5


def test_parse_build_output_skips_warnings():
    """Level==warning lines must be ignored — those belong to Phase C."""
    line = _make_compiler_message(level="warning", code="unused_imports")
    assert _parse_build_output(line) == []


def test_parse_build_output_skips_non_compiler_message():
    line = json.dumps({"reason": "build-script-executed", "package_id": "foo"})
    assert _parse_build_output(line) == []


def test_parse_build_output_multiple_errors():
    lines = "\n".join([
        _make_compiler_message(code="E0412", file_name="src/a.rs"),
        _make_compiler_message(code="E0308", file_name="src/b.rs"),
    ])
    errors = _parse_build_output(lines)
    assert len(errors) == 2
    assert {e.error_code for e in errors} == {"E0412", "E0308"}


# --- IntegrationReport serialization ---

def test_integration_report_serializes_to_json():
    report = IntegrationReport(
        build_success=False,
        total_errors=2,
        files_with_errors=["src/a.rs"],
        files_needing_retranslation=["src/a.rs"],
        errors=[{"error_code": "E0412", "message": "...", "file": "src/a.rs", "line": 5, "column": 1}],
    )
    data = report.to_dict()
    assert data["build_success"] is False
    assert data["total_errors"] == 2
    assert len(data["errors"]) == 1
    json.dumps(data)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_integration_debug.py -v
```

Expected: `ModuleNotFoundError: No module named 'oxidant.integration'`

- [ ] **Step 3: Create the package marker and implement the module**

Create `src/oxidant/integration/__init__.py` (empty).

Create `src/oxidant/integration/integration_debug.py`:

```python
"""Phase D: full-build integration verification and error isolation.

Sequence:
1. ``run_full_build()`` — ``cargo build --release --message-format=json``.
2. ``_parse_build_output()`` — extract BuildError objects from JSON stream.
3. ``_intersect_with_manifest()`` — find translated files among those with errors.
4. Write ``integration_report.json`` to target_path.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_BUILD_TIMEOUT_SECONDS = 600  # release builds take longer than debug


@dataclass
class BuildError:
    error_code: str       # e.g. "E0412"
    message: str          # short human-readable message
    file_name: str        # e.g. "src/foo.rs"
    line_start: int
    column_start: int


@dataclass
class IntegrationReport:
    build_success: bool
    total_errors: int
    files_with_errors: list[str]
    files_needing_retranslation: list[str]
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "build_success": self.build_success,
            "total_errors": self.total_errors,
            "files_with_errors": self.files_with_errors,
            "files_needing_retranslation": self.files_needing_retranslation,
            "errors": self.errors,
        }


def _parse_build_output(output: str) -> list[BuildError]:
    """Parse ``cargo build --message-format=json`` output into BuildError objects.

    Skips warnings (those are Phase C's domain) and non-compiler-message lines.
    """
    errors: list[BuildError] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("reason") != "compiler-message":
            continue
        msg = obj.get("message", {})
        if msg.get("level") != "error":
            continue

        code_obj = msg.get("code") or {}
        error_code = code_obj.get("code") or ""

        primary_span: dict = {}
        for span in msg.get("spans", []):
            if span.get("is_primary"):
                primary_span = span
                break
        if not primary_span and msg.get("spans"):
            primary_span = msg["spans"][0]

        errors.append(BuildError(
            error_code=error_code,
            message=msg.get("message", ""),
            file_name=primary_span.get("file_name", ""),
            line_start=primary_span.get("line_start", 0),
            column_start=primary_span.get("column_start", 0),
        ))
    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_integration_debug.py -v
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/oxidant/integration/__init__.py src/oxidant/integration/integration_debug.py tests/test_integration_debug.py
git commit -m "feat: Phase D build error parser and data classes"
```

---

### Task 2: Manifest intersection + full build runner

**Background:** The manifest lives at `conversion_manifest.json` (or wherever Phase B wrote it). `Manifest.load(path)` parses it via Pydantic. Nodes with `status == NodeStatus.CONVERTED` are the translated files — those are the candidates for re-translation if their `.rs` file shows up in build errors.

`run_full_build` uses `--message-format=json` so we can parse structured output. Cargo writes JSON to stdout and human-readable progress to stderr. We capture both and concatenate.

**Files:**
- Modify: `src/oxidant/integration/integration_debug.py` (add `_intersect_with_manifest`, `run_full_build`, `_error_to_dict`, `run_phase_d`)
- Modify: `tests/test_integration_debug.py` (add 5 more tests)

- [ ] **Step 1: Write failing tests for intersection + build runner**

Append to `tests/test_integration_debug.py`:

```python
from oxidant.integration.integration_debug import (
    BuildError,
    IntegrationReport,
    _error_to_dict,
    _intersect_with_manifest,
    _parse_build_output,
    run_full_build,
    run_phase_d,
)


# --- _intersect_with_manifest ---

def test_intersect_with_manifest_returns_empty_when_no_manifest(tmp_path):
    result = _intersect_with_manifest(["src/foo.rs"], tmp_path / "nonexistent.json")
    assert result == []


def test_intersect_with_manifest_finds_converted_file(tmp_path):
    manifest = {
        "version": "1.0",
        "source_repo": "../msagljs",
        "generated_at": "2026-04-16T00:00:00",
        "nodes": {
            "Foo::bar": {
                "node_id": "Foo::bar",
                "source_file": "src/foo.rs",
                "line_start": 1, "line_end": 10,
                "source_text": "function bar() {}",
                "node_kind": "method",
                "status": "converted",
            }
        }
    }
    manifest_path = tmp_path / "conversion_manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    result = _intersect_with_manifest(["src/foo.rs", "src/other.rs"], manifest_path)
    assert result == ["src/foo.rs"]


def test_intersect_with_manifest_ignores_non_converted(tmp_path):
    manifest = {
        "version": "1.0",
        "source_repo": "../msagljs",
        "generated_at": "2026-04-16T00:00:00",
        "nodes": {
            "Foo::bar": {
                "node_id": "Foo::bar",
                "source_file": "src/foo.rs",
                "line_start": 1, "line_end": 10,
                "source_text": "function bar() {}",
                "node_kind": "method",
                "status": "not_started",
            }
        }
    }
    manifest_path = tmp_path / "conversion_manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    result = _intersect_with_manifest(["src/foo.rs"], manifest_path)
    assert result == []


# --- run_full_build ---

def test_run_full_build_returns_true_on_success(tmp_path):
    with patch("oxidant.integration.integration_debug.subprocess.run", return_value=_fake_run(0)):
        success, output = run_full_build(tmp_path)
    assert success is True


def test_run_full_build_returns_false_on_failure(tmp_path):
    with patch("oxidant.integration.integration_debug.subprocess.run", return_value=_fake_run(1)):
        success, output = run_full_build(tmp_path)
    assert success is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_integration_debug.py::test_intersect_with_manifest_returns_empty_when_no_manifest tests/test_integration_debug.py::test_run_full_build_returns_true_on_success -v
```

Expected: `ImportError: cannot import name '_intersect_with_manifest'`

- [ ] **Step 3: Add the remaining functions to integration_debug.py**

Append to `src/oxidant/integration/integration_debug.py` (after `_parse_build_output`):

```python
def _intersect_with_manifest(
    files_with_errors: list[str],
    manifest_path: Path,
) -> list[str]:
    """Return files from files_with_errors that have a CONVERTED node in the manifest.

    If manifest_path does not exist, returns an empty list (safe fallback for
    projects that haven't run Phase A/B yet).
    """
    if not manifest_path.exists():
        return []

    from oxidant.models.manifest import Manifest, NodeStatus

    manifest = Manifest.load(manifest_path)
    converted_source_files = {
        node.source_file
        for node in manifest.nodes.values()
        if node.status == NodeStatus.CONVERTED
    }
    return [f for f in files_with_errors if f in converted_source_files]


def run_full_build(target_path: Path) -> tuple[bool, str]:
    """Run ``cargo build --release --message-format=json``.

    Args:
        target_path: Root of the Rust project (contains Cargo.toml).

    Returns:
        (success, combined_output) where success is True iff exit code == 0.

    Raises:
        subprocess.TimeoutExpired: If the build takes longer than 10 minutes.
    """
    result = subprocess.run(
        ["cargo", "build", "--release", "--message-format=json"],
        cwd=target_path,
        capture_output=True,
        text=True,
        timeout=_BUILD_TIMEOUT_SECONDS,
    )
    logger.info("cargo build --release exited %d", result.returncode)
    # cargo writes JSON to stdout; human progress lines go to stderr
    combined = result.stdout + "\n" + result.stderr
    return result.returncode == 0, combined


def _error_to_dict(e: BuildError) -> dict:
    return {
        "error_code": e.error_code,
        "message": e.message,
        "file": e.file_name,
        "line": e.line_start,
        "column": e.column_start,
    }


def run_phase_d(
    target_path: Path,
    manifest_path: Path | None = None,
) -> IntegrationReport:
    """Run the full Phase D integration verification pipeline.

    1. Run ``cargo build --release --message-format=json``.
    2. Parse build errors from JSON stream.
    3. Identify translated files needing re-translation (manifest intersection).
    4. Write ``integration_report.json`` to target_path.

    Args:
        target_path: Root of the Rust project (contains Cargo.toml).
        manifest_path: Path to conversion_manifest.json. When None, the
            files_needing_retranslation list will be empty.

    Returns:
        IntegrationReport with build status and per-error details.
    """
    logger.info("Phase D: running full build on %s...", target_path)
    success, output = run_full_build(target_path)

    errors = _parse_build_output(output)
    files_with_errors = sorted({e.file_name for e in errors if e.file_name})

    files_needing_retranslation: list[str] = []
    if manifest_path is not None:
        files_needing_retranslation = _intersect_with_manifest(
            files_with_errors, manifest_path
        )

    report = IntegrationReport(
        build_success=success,
        total_errors=len(errors),
        files_with_errors=files_with_errors,
        files_needing_retranslation=files_needing_retranslation,
        errors=[_error_to_dict(e) for e in errors],
    )

    report_path = target_path / "integration_report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2))
    logger.info(
        "Phase D complete: build_success=%s, %d errors in %d files (%d needing retranslation)",
        success, len(errors), len(files_with_errors), len(files_needing_retranslation),
    )
    return report
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest tests/test_integration_debug.py -v
```

Expected: 11 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/oxidant/integration/integration_debug.py tests/test_integration_debug.py
git commit -m "feat: manifest intersection, full build runner, and run_phase_d orchestrator"
```

---

### Task 3: End-to-end tests for run_phase_d + CLI command

**Background:** The last three tests exercise the full `run_phase_d()` path (success, failure, with manifest). The CLI command follows the pattern of `phase-c` exactly. The import is deferred inside the command function (same pattern as phase-b and phase-c in `cli.py`) to avoid import-time side effects.

**Files:**
- Modify: `tests/test_integration_debug.py` (add 3 end-to-end tests)
- Modify: `src/oxidant/cli.py` (add `phase-d` command)

- [ ] **Step 1: Write failing end-to-end tests**

Append to `tests/test_integration_debug.py`:

```python
# --- run_phase_d end-to-end ---

def test_run_phase_d_success_writes_report(tmp_path):
    """Successful build produces a report with build_success=True and no errors."""
    with patch("oxidant.integration.integration_debug.subprocess.run", return_value=_fake_run(0)):
        report = run_phase_d(tmp_path)

    assert report.build_success is True
    assert report.total_errors == 0
    report_path = tmp_path / "integration_report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert data["build_success"] is True
    assert "errors" in data


def test_run_phase_d_failure_identifies_files(tmp_path):
    """Failing build populates files_with_errors from parsed error messages."""
    error_line = _make_compiler_message(code="E0412", file_name="src/graph.rs")
    mock = _fake_run(returncode=1, stdout=error_line)

    with patch("oxidant.integration.integration_debug.subprocess.run", return_value=mock):
        report = run_phase_d(tmp_path)

    assert report.build_success is False
    assert report.total_errors == 1
    assert "src/graph.rs" in report.files_with_errors


def test_run_phase_d_intersects_manifest_when_provided(tmp_path):
    """When a manifest is provided, files_needing_retranslation is populated."""
    manifest = {
        "version": "1.0",
        "source_repo": "../msagljs",
        "generated_at": "2026-04-16T00:00:00",
        "nodes": {
            "Graph::layout": {
                "node_id": "Graph::layout",
                "source_file": "src/graph.rs",
                "line_start": 1, "line_end": 50,
                "source_text": "function layout() {}",
                "node_kind": "method",
                "status": "converted",
            }
        }
    }
    manifest_path = tmp_path / "conversion_manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    error_line = _make_compiler_message(code="E0412", file_name="src/graph.rs")
    mock = _fake_run(returncode=1, stdout=error_line)

    with patch("oxidant.integration.integration_debug.subprocess.run", return_value=mock):
        report = run_phase_d(tmp_path, manifest_path=manifest_path)

    assert "src/graph.rs" in report.files_needing_retranslation
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_integration_debug.py::test_run_phase_d_success_writes_report -v
```

Expected: `ImportError: cannot import name 'run_phase_d'` (already imported but not yet in the module from Task 1's stub — verify this fails naturally if running fresh, otherwise they may already pass from Task 2)

Actually these will pass already if Task 2 is complete. Run all 14 tests:

```bash
uv run pytest tests/test_integration_debug.py -v
```

Expected: 14 PASSED

- [ ] **Step 3: Add the phase-d CLI command**

Open `src/oxidant/cli.py`. After the `phase-c` command (ending around line 199), before the `translate` command, add:

```python
@app.command("phase-d")
def phase_d(
    config: Path = typer.Option("oxidant.config.json", "--config", "-c"),
    target: Path = typer.Option(
        None, "--target",
        help="Rust project root. Defaults to target_repo from config.",
    ),
    manifest: Path = typer.Option(
        None, "--manifest",
        help="Path to conversion_manifest.json for retranslation hints.",
    ),
) -> None:
    """Run Phase D: full build verification and integration error isolation.

    Runs ``cargo build --release`` on the target Rust project, parses
    integration errors, and writes ``integration_report.json``.
    Pass ``--manifest`` to also identify which translated files need re-translation.
    """
    import json as _json
    from oxidant.integration.integration_debug import run_phase_d

    cfg = _json.loads(config.read_text())
    target_path = target or Path(cfg["target_repo"])

    typer.echo(f"Phase D: running full build on {target_path}...")
    report = run_phase_d(target_path.resolve(), manifest_path=manifest)

    status = "PASS" if report.build_success else "FAIL"
    typer.echo(f"  Build:       {status}")
    typer.echo(f"  Errors:      {report.total_errors}")
    typer.echo(f"  Files:       {len(report.files_with_errors)}")
    if report.files_needing_retranslation:
        typer.echo(f"  Retranslate: {len(report.files_needing_retranslation)} file(s)")
        for f in report.files_needing_retranslation:
            typer.echo(f"    {f}")
    typer.echo(f"\nReport written to {target_path.resolve() / 'integration_report.json'}")
```

The insertion point is after line 199 (`typer.echo(f"\nReport written to {target_path / 'clippy_report.json'}")`) and before line 202 (`@app.command()`).

- [ ] **Step 4: Run all tests**

```bash
uv run pytest tests/ -q
```

Expected: 112 passed (98 existing + 14 new)

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration_debug.py src/oxidant/cli.py
git commit -m "feat: Phase D end-to-end tests and phase-d CLI command"
```

---

## Self-Review

### Spec coverage

| PRD requirement | Task |
|-----------------|------|
| 5.1 Run `cargo build --release` | Task 2: `run_full_build` |
| 5.1 Parse integration errors | Task 1: `_parse_build_output` |
| 5.1 Identify files needing re-translation | Task 2: `_intersect_with_manifest` |
| 5.1 Write report | Task 2: `run_phase_d` → `integration_report.json` |
| CLI `phase-d` command | Task 3 |
| 5.2 Equivalence testing (WASM harness) | **DEFERRED** — requires real wasm-pack output |
| 5.3 Proptest generation | **DEFERRED** — requires real Rust corpus |

All in-scope requirements have tasks. Deferred items are explicitly flagged.

### Placeholder scan

No TBDs, todos, or "similar to Task N" references found. All code blocks are complete.

### Type consistency

- `BuildError` defined in Task 1, used in Tasks 1 and 2. Fields: `error_code`, `message`, `file_name`, `line_start`, `column_start`. Consistent throughout.
- `IntegrationReport` defined in Task 1. Fields: `build_success`, `total_errors`, `files_with_errors`, `files_needing_retranslation`, `errors`. Used consistently in Tasks 2–3.
- `_error_to_dict(e: BuildError)` defined in Task 2, keys match what test in Task 1 expects (`error_code`, `message`, `file`, `line`, `column`). Consistent.
- `run_full_build` → `tuple[bool, str]` defined and used in Task 2. `run_phase_d` calls it correctly.
- `_intersect_with_manifest(files_with_errors: list[str], manifest_path: Path) -> list[str]` defined and used consistently.
- Import line in tests updated in Task 2 to include `_error_to_dict`, `_intersect_with_manifest`, `run_full_build`, `run_phase_d`. Task 3 tests don't import any new symbols — they use what's already imported.
