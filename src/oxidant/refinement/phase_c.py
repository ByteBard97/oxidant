"""Phase C orchestration: auto-fix mechanical warnings, report remaining ones.

Sequence:
1. ``cargo clippy --fix --allow-dirty`` — cargo applies all MachineApplicable
   suggestions in-place. No agent needed.
2. ``run_clippy()`` — parse remaining warnings after auto-fix.
3. Categorize + write ``clippy_report.json`` to target_path.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from oxidant.refinement.categorize import WarningTier, categorize_warning
from oxidant.refinement.clippy_runner import ClippyWarning, run_clippy

logger = logging.getLogger(__name__)

_FIX_TIMEOUT_SECONDS = 300
_CLIPPY_PEDANTIC_FLAGS = [
    "--",
    "-W", "clippy::pedantic",
    "-A", "clippy::module_name_repetitions",
    "-A", "clippy::missing_errors_doc",
    "-A", "clippy::missing_panics_doc",
]


@dataclass
class ClippyReport:
    auto_fixed_count: int
    total_remaining: int
    mechanical_count: int
    structural_count: int
    human_count: int
    warnings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "auto_fixed_count": self.auto_fixed_count,
            "total_remaining": self.total_remaining,
            "mechanical_count": self.mechanical_count,
            "structural_count": self.structural_count,
            "human_count": self.human_count,
            "warnings": self.warnings,
        }


def _run_auto_fix(target_path: Path) -> int:
    """Run ``cargo clippy --fix --allow-dirty`` to apply MachineApplicable clippy suggestions.

    Returns the exit code (0 = success, non-zero = fix failed or no changes).
    The fix may fail on a skeleton with many todo!() stubs — that is expected.
    """
    result = subprocess.run(
        [
            "cargo", "clippy",
            "--fix", "--allow-dirty", "--allow-staged",
            "--all-targets",
        ] + _CLIPPY_PEDANTIC_FLAGS,
        cwd=target_path,
        capture_output=True,
        text=True,
        timeout=_FIX_TIMEOUT_SECONDS,
    )
    logger.info("cargo clippy --fix exited %d", result.returncode)
    return result.returncode


def _warning_to_dict(w: ClippyWarning, tier: WarningTier) -> dict:
    return {
        "lint_code": w.lint_code,
        "tier": tier.value,
        "file": w.file_name,
        "line": w.line_start,
        "message": w.message,
        "machine_applicable": w.machine_applicable,
    }


def run_phase_c(target_path: Path) -> ClippyReport:
    """Run the full Phase C refinement pipeline.

    1. Collect baseline warning count via dry run.
    2. Apply auto-fixes with ``cargo clippy --fix``.
    3. Collect remaining warnings.
    4. Categorize and write ``clippy_report.json``.

    Args:
        target_path: Root of the Rust project (contains Cargo.toml).

    Returns:
        ClippyReport with counts and per-warning details.
    """
    # Baseline: count warnings before auto-fix
    logger.info("Phase C: collecting baseline warnings...")
    baseline_warnings = run_clippy(target_path)
    baseline_count = len(baseline_warnings)
    logger.info("Baseline: %d warnings", baseline_count)

    # Auto-fix pass
    logger.info("Phase C: running cargo clippy --fix...")
    _run_auto_fix(target_path)

    # Report pass: warnings remaining after auto-fix
    logger.info("Phase C: collecting remaining warnings...")
    remaining_warnings = run_clippy(target_path)

    auto_fixed = max(0, baseline_count - len(remaining_warnings))

    # Categorize
    mechanical_count = 0
    structural_count = 0
    human_count = 0
    warning_dicts: list[dict] = []

    for w in remaining_warnings:
        tier = categorize_warning(w)
        if tier == WarningTier.MECHANICAL:
            mechanical_count += 1
        elif tier == WarningTier.STRUCTURAL:
            structural_count += 1
        else:
            human_count += 1
        warning_dicts.append(_warning_to_dict(w, tier))

    report = ClippyReport(
        auto_fixed_count=auto_fixed,
        total_remaining=len(remaining_warnings),
        mechanical_count=mechanical_count,
        structural_count=structural_count,
        human_count=human_count,
        warnings=warning_dicts,
    )

    # Write report
    report_path = target_path / "clippy_report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2))
    logger.info(
        "Phase C complete: %d auto-fixed, %d remaining (%d mechanical, %d structural, %d human)",
        auto_fixed, len(remaining_warnings), mechanical_count, structural_count, human_count,
    )
    return report
