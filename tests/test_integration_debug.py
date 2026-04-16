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
