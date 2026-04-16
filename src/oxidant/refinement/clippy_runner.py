"""Parse `cargo clippy --message-format=json` output into typed ClippyWarning objects.

Cargo emits one JSON object per line to stdout (stderr goes to the terminal by default,
but with ``2>&1`` redirect it appears inline). We only care about lines with
``"reason": "compiler-message"`` and ``message.level == "warning"``.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Shared lint flags used by both the diagnostic pass and the --fix pass.
# Kept here so both callers stay in sync automatically.
PEDANTIC_DENY_FLAGS: list[str] = [
    "-W", "clippy::pedantic",
    "-A", "clippy::module_name_repetitions",   # too noisy for generated code
    "-A", "clippy::missing_errors_doc",        # no docs in skeleton
    "-A", "clippy::missing_panics_doc",
]

_CLIPPY_FLAGS: list[str] = [
    "--message-format=json",
    "--all-targets",
    "--",
] + PEDANTIC_DENY_FLAGS

_CARGO_TIMEOUT_SECONDS = 300


@dataclass
class ClippyWarning:
    lint_code: str                              # e.g. "clippy::redundant_clone"
    level: str                                  # "warning"
    message: str                                # human-readable message
    file_name: str                              # e.g. "src/foo.rs"
    line_start: int
    line_end: int
    column_start: int
    column_end: int
    rendered: str = field(default="")          # full rendered text from cargo
    machine_applicable: bool = field(default=False)
    suggested_replacement: str | None = field(default=None)


def _extract_suggestion(children: list[dict]) -> tuple[bool, str | None]:
    """Return (machine_applicable, suggested_replacement) from message children."""
    for child in children:
        for span in child.get("spans", []):
            applicability = span.get("suggestion_applicability") or ""
            replacement = span.get("suggested_replacement")
            if replacement is not None:
                return applicability == "MachineApplicable", replacement
    return False, None


def _parse_line(line: str) -> ClippyWarning | None:
    """Parse a single JSON line from cargo output. Returns None if not a warning."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None

    if obj.get("reason") != "compiler-message":
        return None

    msg = obj.get("message", {})
    if msg.get("level") != "warning":
        return None

    code_obj = msg.get("code") or {}
    lint_code = code_obj.get("code") or ""

    primary_span: dict = {}
    for span in msg.get("spans", []):
        if span.get("is_primary"):
            primary_span = span
            break
    if not primary_span and msg.get("spans"):
        primary_span = msg["spans"][0]

    machine_applicable, suggested = _extract_suggestion(msg.get("children", []))

    return ClippyWarning(
        lint_code=lint_code,
        level="warning",
        message=msg.get("rendered", "").splitlines()[0] if msg.get("rendered") else "",
        file_name=primary_span.get("file_name", ""),
        line_start=primary_span.get("line_start", 0),
        line_end=primary_span.get("line_end", 0),
        column_start=primary_span.get("column_start", 0),
        column_end=primary_span.get("column_end", 0),
        rendered=msg.get("rendered", ""),
        machine_applicable=machine_applicable,
        suggested_replacement=suggested,
    )


def run_clippy(target_path: Path) -> list[ClippyWarning]:
    """Run ``cargo clippy --message-format=json`` and return parsed warnings.

    Args:
        target_path: Root of the Rust project (directory containing Cargo.toml).

    Returns:
        List of ClippyWarning objects for all warning-level messages.

    Raises:
        subprocess.TimeoutExpired: If clippy takes longer than 5 minutes.
    """
    result = subprocess.run(
        ["cargo", "clippy"] + _CLIPPY_FLAGS,
        cwd=target_path,
        capture_output=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=_CARGO_TIMEOUT_SECONDS,
    )
    logger.debug("cargo clippy exited %d", result.returncode)

    warnings: list[ClippyWarning] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        w = _parse_line(line)
        if w is not None:
            warnings.append(w)

    logger.info("clippy: %d warnings parsed", len(warnings))
    return warnings
