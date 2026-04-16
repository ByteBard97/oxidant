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
