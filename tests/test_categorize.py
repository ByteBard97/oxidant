import pytest
from oxidant.refinement.categorize import WarningTier, categorize_warning
from oxidant.refinement.clippy_runner import ClippyWarning


def _make_warning(lint_code: str, machine_applicable: bool = True) -> ClippyWarning:
    return ClippyWarning(
        lint_code=lint_code,
        level="warning",
        message="test",
        file_name="src/foo.rs",
        line_start=1,
        line_end=1,
        column_start=1,
        column_end=5,
        machine_applicable=machine_applicable,
    )


def test_redundant_clone_is_mechanical():
    assert categorize_warning(_make_warning("clippy::redundant_clone")) == WarningTier.MECHANICAL


def test_needless_return_is_mechanical():
    assert categorize_warning(_make_warning("clippy::needless_return")) == WarningTier.MECHANICAL


def test_unused_imports_is_mechanical():
    assert categorize_warning(_make_warning("unused_imports")) == WarningTier.MECHANICAL


def test_too_many_arguments_is_structural():
    assert categorize_warning(_make_warning("clippy::too_many_arguments", machine_applicable=False)) == WarningTier.STRUCTURAL


def test_unknown_code_is_human():
    assert categorize_warning(_make_warning("clippy::some_unknown_lint", machine_applicable=False)) == WarningTier.HUMAN


def test_mechanical_but_not_machine_applicable_becomes_human():
    """Even a 'mechanical' lint code is HUMAN if the fix is not MachineApplicable."""
    w = _make_warning("clippy::redundant_clone", machine_applicable=False)
    assert categorize_warning(w) == WarningTier.HUMAN


def test_empty_lint_code_is_human():
    assert categorize_warning(_make_warning("")) == WarningTier.HUMAN


def test_needless_pass_is_mechanical():
    assert categorize_warning(_make_warning("clippy::needless_pass_by_value", machine_applicable=True)) == WarningTier.MECHANICAL
