import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from oxidant.refinement.clippy_runner import ClippyWarning, run_clippy


def _make_compiler_message(
    code: str,
    level: str = "warning",
    message: str = "test warning",
    file_name: str = "src/foo.rs",
    line_start: int = 10,
    applicability: str = "MachineApplicable",
    suggested: str | None = "fixed_code",
) -> str:
    return json.dumps({
        "reason": "compiler-message",
        "message": {
            "rendered": f"{level}[{code}]: {message}\n",
            "level": level,
            "code": {"code": code, "explanation": None},
            "spans": [
                {
                    "file_name": file_name,
                    "line_start": line_start,
                    "line_end": line_start,
                    "column_start": 1,
                    "column_end": 10,
                    "is_primary": True,
                    "suggested_replacement": None,
                    "suggestion_applicability": None,
                }
            ],
            "children": [
                {
                    "message": "try",
                    "level": "help",
                    "spans": [
                        {
                            "file_name": file_name,
                            "line_start": line_start,
                            "line_end": line_start,
                            "column_start": 1,
                            "column_end": 10,
                            "is_primary": True,
                            "suggested_replacement": suggested,
                            "suggestion_applicability": applicability,
                        }
                    ],
                }
            ] if suggested else [],
        },
    })


def _non_warning_line() -> str:
    return json.dumps({"reason": "build-script-executed"})


def _make_cargo_result(lines: list[str], returncode: int = 0) -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = "\n".join(lines) + "\n"
    mock.stderr = ""
    return mock


def test_parses_single_warning(tmp_path):
    """run_clippy returns one ClippyWarning per compiler-message warning line."""
    output = _make_compiler_message("clippy::redundant_clone")
    with patch("oxidant.refinement.clippy_runner.subprocess.run",
               return_value=_make_cargo_result([output])):
        warnings = run_clippy(tmp_path)
    assert len(warnings) == 1
    w = warnings[0]
    assert w.lint_code == "clippy::redundant_clone"
    assert w.level == "warning"
    assert w.file_name == "src/foo.rs"
    assert w.line_start == 10


def test_skips_non_warning_lines(tmp_path):
    """Non compiler-message lines are silently ignored."""
    lines = [
        _non_warning_line(),
        _make_compiler_message("clippy::needless_return"),
        json.dumps({"reason": "build-finished", "success": True}),
    ]
    with patch("oxidant.refinement.clippy_runner.subprocess.run",
               return_value=_make_cargo_result(lines)):
        warnings = run_clippy(tmp_path)
    assert len(warnings) == 1


def test_skips_error_level_messages(tmp_path):
    """Error-level messages (not warnings) are excluded."""
    output = _make_compiler_message("E0308", level="error")
    with patch("oxidant.refinement.clippy_runner.subprocess.run",
               return_value=_make_cargo_result([output])):
        warnings = run_clippy(tmp_path)
    assert len(warnings) == 0


def test_machine_applicable_suggestion_captured(tmp_path):
    """MachineApplicable suggestion text is captured on the warning."""
    output = _make_compiler_message(
        "clippy::redundant_clone",
        suggested="value",
        applicability="MachineApplicable",
    )
    with patch("oxidant.refinement.clippy_runner.subprocess.run",
               return_value=_make_cargo_result([output])):
        warnings = run_clippy(tmp_path)
    assert warnings[0].machine_applicable is True
    assert warnings[0].suggested_replacement == "value"


def test_non_machine_applicable_not_flagged(tmp_path):
    """MaybeIncorrect suggestions are not marked machine_applicable."""
    output = _make_compiler_message(
        "clippy::too_many_arguments",
        suggested="refactor",
        applicability="MaybeIncorrect",
    )
    with patch("oxidant.refinement.clippy_runner.subprocess.run",
               return_value=_make_cargo_result([output])):
        warnings = run_clippy(tmp_path)
    assert warnings[0].machine_applicable is False


def test_handles_malformed_json_lines_gracefully(tmp_path):
    """Malformed lines are skipped without crashing."""
    lines = [
        "not json at all",
        _make_compiler_message("clippy::redundant_clone"),
        "{broken json",
    ]
    with patch("oxidant.refinement.clippy_runner.subprocess.run",
               return_value=_make_cargo_result(lines)):
        warnings = run_clippy(tmp_path)
    assert len(warnings) == 1


def test_no_code_field_warning_included(tmp_path):
    """Warnings without a lint code (e.g. bare 'unused variable') are included with empty code."""
    line = json.dumps({
        "reason": "compiler-message",
        "message": {
            "rendered": "warning: unused variable\n",
            "level": "warning",
            "code": None,
            "spans": [{"file_name": "src/bar.rs", "line_start": 5,
                        "line_end": 5, "column_start": 1, "column_end": 5,
                        "is_primary": True, "suggested_replacement": None,
                        "suggestion_applicability": None}],
            "children": [],
        },
    })
    with patch("oxidant.refinement.clippy_runner.subprocess.run",
               return_value=_make_cargo_result([line])):
        warnings = run_clippy(tmp_path)
    assert len(warnings) == 1
    assert warnings[0].lint_code == ""
