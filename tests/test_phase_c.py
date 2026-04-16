import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from oxidant.refinement.clippy_runner import ClippyWarning
from oxidant.refinement.categorize import WarningTier
from oxidant.refinement.phase_c import ClippyReport, run_phase_c


def _make_warning(code: str, machine_applicable: bool = True) -> ClippyWarning:
    return ClippyWarning(
        lint_code=code, level="warning", message="test",
        file_name="src/foo.rs", line_start=1, line_end=1,
        column_start=1, column_end=5,
        machine_applicable=machine_applicable,
    )


def _fake_run(returncode: int = 0) -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = ""
    mock.stderr = ""
    return mock


def test_run_phase_c_returns_report(tmp_path):
    """run_phase_c returns a ClippyReport with categorized warnings."""
    warnings = [
        _make_warning("clippy::redundant_clone", machine_applicable=True),
        _make_warning("clippy::too_many_arguments", machine_applicable=False),
        _make_warning("clippy::some_custom_lint", machine_applicable=False),
    ]

    with patch("oxidant.refinement.phase_c.subprocess.run", return_value=_fake_run()):
        with patch("oxidant.refinement.phase_c.run_clippy", return_value=warnings):
            report = run_phase_c(tmp_path)

    assert isinstance(report, ClippyReport)
    assert report.total_remaining == 3
    assert report.mechanical_count == 1
    assert report.structural_count == 1
    assert report.human_count == 1


def test_run_phase_c_auto_fix_called_first(tmp_path):
    """cargo fix is invoked before the JSON report pass."""
    fix_calls: list = []

    def capture_run(cmd, **kwargs):
        fix_calls.append(cmd)
        return _fake_run()

    with patch("oxidant.refinement.phase_c.subprocess.run", side_effect=capture_run):
        with patch("oxidant.refinement.phase_c.run_clippy", return_value=[]):
            run_phase_c(tmp_path)

    assert any("fix" in cmd for cmd in fix_calls)


def test_run_phase_c_writes_report_to_disk(tmp_path):
    """run_phase_c writes clippy_report.json to the target directory."""
    warnings = [_make_warning("clippy::needless_return", machine_applicable=True)]

    with patch("oxidant.refinement.phase_c.subprocess.run", return_value=_fake_run()):
        with patch("oxidant.refinement.phase_c.run_clippy", return_value=warnings):
            run_phase_c(tmp_path)

    report_path = tmp_path / "clippy_report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert "total_remaining" in data
    assert "warnings" in data


def test_clippy_report_serializes_to_json():
    """ClippyReport can be serialized to a JSON-compatible dict."""
    report = ClippyReport(
        auto_fixed_count=5,
        total_remaining=1,
        mechanical_count=1,
        structural_count=0,
        human_count=0,
        warnings=[{"lint_code": "clippy::redundant_clone", "tier": "mechanical",
                    "file": "src/foo.rs", "line": 1, "message": "test"}],
    )
    data = report.to_dict()
    assert data["auto_fixed_count"] == 5
    assert len(data["warnings"]) == 1
    # Must be JSON-serializable
    json.dumps(data)
