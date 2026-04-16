import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from oxidant.integration.integration_debug import (
    BuildError,
    IntegrationReport,
    _error_to_dict,
    _intersect_with_manifest,
    _parse_build_output,
    run_full_build,
    run_phase_d,
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


def test_parse_build_output_skips_aborting_summary():
    """Cargo's 'aborting due to N previous errors' has null code and no spans — must be skipped."""
    line = json.dumps({
        "reason": "compiler-message",
        "message": {
            "level": "error",
            "message": "aborting due to 2 previous errors",
            "code": None,
            "spans": [],
            "children": [],
            "rendered": "error: aborting due to 2 previous errors\n",
        }
    })
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
                "source_file": "foo.ts",
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
                "source_file": "foo.ts",
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
