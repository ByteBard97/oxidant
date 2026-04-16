"""Verification pipeline for converted Rust snippets.

Three checks in order of cost (cheapest first):
1. Stub check   — instant: grep for todo!/unimplemented!
2. Branch parity — instant: rough structural comparison
3. Cargo check  — ~5-30 s: inject into skeleton, run cargo check, restore stub
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class VerifyStatus(str, Enum):
    PASS = "PASS"
    STUB = "STUB"        # todo!/unimplemented! found in snippet
    BRANCH = "BRANCH"    # branch parity check failed
    CARGO = "CARGO"      # cargo check compilation failed


@dataclass
class VerifyResult:
    status: VerifyStatus
    error: str = field(default="")


_STUB_RE = re.compile(r'\btodo!\s*\(|\bunimplemented!\s*\(')
_BRANCH_RE_TS = re.compile(r'\bif\b|\belse\b|\bswitch\b|\bcase\b|\bfor\b|\bwhile\b|\?\s')
_BRANCH_RE_RS = re.compile(r'\bif\b|\belse\b|\bmatch\b|\bfor\b|\bwhile\b|\bloop\b')

_BRANCH_MIN_TS_COUNT = 3          # only check parity when TS has >= this many branches
_BRANCH_RATIO_FLOOR = 0.60        # Rust must have >= 60% as many branches as TS
_CARGO_TIMEOUT_SECONDS = 120


def _check_stubs(snippet: str) -> VerifyResult | None:
    if _STUB_RE.search(snippet):
        return VerifyResult(VerifyStatus.STUB, "Snippet contains todo!() or unimplemented!()")
    return None


def _check_branch_parity(ts_source: str, rs_snippet: str) -> VerifyResult | None:
    ts_count = len(_BRANCH_RE_TS.findall(ts_source))
    rs_count = len(_BRANCH_RE_RS.findall(rs_snippet))
    if ts_count >= _BRANCH_MIN_TS_COUNT and rs_count < ts_count * _BRANCH_RATIO_FLOOR:
        return VerifyResult(
            VerifyStatus.BRANCH,
            f"Branch parity: TypeScript={ts_count} branches, Rust={rs_count} "
            f"(below {_BRANCH_RATIO_FLOOR:.0%} floor)",
        )
    return None


def _module_name(source_file: str) -> str:
    from oxidant.analysis.generate_skeleton import _module_name as _gen_module_name
    return _gen_module_name(source_file)


def _inject_and_check_cargo(
    node_id: str,
    snippet: str,
    target_path: Path,
    source_file: str,
) -> VerifyResult | None:
    """Inject snippet into skeleton, run cargo check, always restore original."""
    module = _module_name(source_file)
    rs_path = target_path / "src" / f"{module}.rs"

    marker = f'todo!("OXIDANT: not yet translated — {node_id}")'
    original_content = rs_path.read_text()

    if marker not in original_content:
        return VerifyResult(
            VerifyStatus.CARGO,
            f"todo! marker not found for {node_id} in {module}.rs",
        )

    rs_path.write_text(original_content.replace(marker, snippet, 1))
    try:
        proc = subprocess.run(
            ["cargo", "check", "--message-format=short"],
            cwd=target_path,
            capture_output=True,
            text=True,
            timeout=_CARGO_TIMEOUT_SECONDS,
        )
        if proc.returncode == 0:
            return None
        error_text = proc.stderr[:2000] or proc.stdout[:2000]
        return VerifyResult(VerifyStatus.CARGO, error_text)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return VerifyResult(VerifyStatus.CARGO, str(exc))
    finally:
        rs_path.write_text(original_content)


def verify_snippet(
    node_id: str,
    snippet: str,
    ts_source: str,
    target_path: Path,
    source_file: str,
) -> VerifyResult:
    """Run all three verification checks and return the first failure, or PASS.

    Args:
        node_id: The manifest node ID (used to find the todo! marker).
        snippet: The raw Rust function body text returned by the agent.
        ts_source: The original TypeScript source text (for branch parity).
        target_path: Root of the skeleton Rust project.
        source_file: The node's TypeScript source file path.
    """
    if r := _check_stubs(snippet):
        return r
    if r := _check_branch_parity(ts_source, snippet):
        return r
    if r := _inject_and_check_cargo(node_id, snippet, target_path, source_file):
        return r
    return VerifyResult(VerifyStatus.PASS)
