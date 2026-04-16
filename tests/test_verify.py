import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from oxidant.verification.verify import (
    VerifyResult,
    VerifyStatus,
    verify_snippet,
    _check_stubs,
    _check_branch_parity,
)


# ── Stub check ────────────────────────────────────────────────────────────────

def test_stub_check_rejects_todo():
    result = _check_stubs('todo!("not implemented")')
    assert result is not None
    assert result.status == VerifyStatus.STUB


def test_stub_check_rejects_unimplemented():
    result = _check_stubs("unimplemented!()")
    assert result is not None
    assert result.status == VerifyStatus.STUB


def test_stub_check_passes_clean_code():
    result = _check_stubs("let x = 42; x + 1")
    assert result is None


# ── Branch parity check ───────────────────────────────────────────────────────

def test_branch_parity_passes_simple():
    """A single-branch function passes parity regardless of Rust count."""
    ts = "function foo() { return 1; }"
    rs = "1"
    assert _check_branch_parity(ts, rs) is None


def test_branch_parity_fails_many_ts_branches_no_rust():
    """TS has many branches, Rust has none → BRANCH."""
    ts = "if a { } else if b { } else { } for (x of y) { } while (z) { }"
    rs = "42"
    result = _check_branch_parity(ts, rs)
    assert result is not None
    assert result.status == VerifyStatus.BRANCH


def test_branch_parity_passes_matching_branches():
    ts = "if a { } else if b { } else { } for (x of y) { }"
    rs = "if a { } else if b { } else { } for x in y { }"
    assert _check_branch_parity(ts, rs) is None


# ── Full verify_snippet ───────────────────────────────────────────────────────

def test_verify_snippet_stub_fails_before_cargo(tmp_path):
    """Stub check short-circuits — cargo check is never called."""
    result = verify_snippet(
        node_id="m__foo",
        snippet='todo!("still a stub")',
        ts_source="function foo() {}",
        target_path=tmp_path,
        source_file="m.ts",
    )
    assert result.status == VerifyStatus.STUB


def test_verify_snippet_cargo_check_pass(tmp_path):
    """When cargo check passes, result is PASS."""
    src = tmp_path / "src"
    src.mkdir()
    rs_file = src / "m.rs"
    rs_file.write_text(
        'pub fn foo() {\n'
        '    todo!("OXIDANT: not yet translated — m__foo")\n'
        '}\n'
    )

    fake_cargo = MagicMock()
    fake_cargo.returncode = 0
    fake_cargo.stderr = ""
    fake_cargo.stdout = ""

    with patch("oxidant.verification.verify.subprocess.run", return_value=fake_cargo):
        result = verify_snippet(
            node_id="m__foo",
            snippet="42",
            ts_source="function foo() { return 42; }",
            target_path=tmp_path,
            source_file="m.ts",
        )

    assert result.status == VerifyStatus.PASS
    # Skeleton must be restored to original after check
    assert 'todo!("OXIDANT: not yet translated — m__foo")' in rs_file.read_text()


def test_verify_snippet_cargo_check_fail(tmp_path):
    """When cargo check fails, result is CARGO with error text."""
    src = tmp_path / "src"
    src.mkdir()
    rs_file = src / "m.rs"
    rs_file.write_text(
        'pub fn foo() -> i32 {\n'
        '    todo!("OXIDANT: not yet translated — m__foo")\n'
        '}\n'
    )

    fake_cargo = MagicMock()
    fake_cargo.returncode = 1
    fake_cargo.stderr = "error[E0308]: mismatched types"
    fake_cargo.stdout = ""

    with patch("oxidant.verification.verify.subprocess.run", return_value=fake_cargo):
        result = verify_snippet(
            node_id="m__foo",
            snippet='"hello"',
            ts_source="function foo(): number { return 42; }",
            target_path=tmp_path,
            source_file="m.ts",
        )

    assert result.status == VerifyStatus.CARGO
    assert "E0308" in result.error
    # Skeleton always restored
    assert 'todo!("OXIDANT: not yet translated — m__foo")' in rs_file.read_text()


def test_verify_snippet_restores_skeleton_even_on_exception(tmp_path):
    """Skeleton is restored even if subprocess.run raises an exception."""
    src = tmp_path / "src"
    src.mkdir()
    rs_file = src / "m.rs"
    original = 'pub fn foo() {\n    todo!("OXIDANT: not yet translated — m__foo")\n}\n'
    rs_file.write_text(original)

    with patch("oxidant.verification.verify.subprocess.run", side_effect=OSError("no cargo")):
        result = verify_snippet(
            node_id="m__foo",
            snippet="42",
            ts_source="function foo() {}",
            target_path=tmp_path,
            source_file="m.ts",
        )

    assert result.status == VerifyStatus.CARGO
    assert rs_file.read_text() == original
