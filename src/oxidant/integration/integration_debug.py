"""Phase D: full-build integration verification and error isolation.

Parses ``cargo build --release --message-format=json`` output into typed
``BuildError`` objects and aggregates them into an ``IntegrationReport``.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_BUILD_TIMEOUT_SECONDS = 600


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

        if not primary_span:
            continue

        errors.append(BuildError(
            error_code=error_code,
            message=msg.get("message", ""),
            file_name=primary_span.get("file_name", ""),
            line_start=primary_span.get("line_start", 0),
            column_start=primary_span.get("column_start", 0),
        ))
    return errors


def _intersect_with_manifest(
    files_with_errors: list[str],
    manifest_path: Path,
) -> list[str]:
    """Return Rust files from files_with_errors that correspond to CONVERTED manifest nodes.

    The manifest stores TypeScript source paths (e.g. ``geomGraph.ts``).
    Cargo reports Rust file paths (e.g. ``src/geom_graph.rs``).
    The correspondence is via stem: ``_module_name("geomGraph.ts") == Path("src/geom_graph.rs").stem``.

    If manifest_path does not exist, returns an empty list (safe fallback for
    projects that haven't run Phase A/B yet).
    """
    if not manifest_path.exists():
        return []

    from oxidant.analysis.generate_skeleton import _module_name
    from oxidant.models.manifest import Manifest, NodeStatus

    manifest = Manifest.load(manifest_path)
    converted_rust_stems: set[str] = {
        _module_name(node.source_file)
        for node in manifest.nodes.values()
        if node.status == NodeStatus.CONVERTED
    }
    return [f for f in files_with_errors if Path(f).stem in converted_rust_stems]


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
