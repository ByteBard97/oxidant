"""Categorize ClippyWarnings into tiers for Phase C handling.

MECHANICAL — machine-applicable fix, safe for auto-apply
STRUCTURAL — architectural change, needs human approval
HUMAN      — everything else
"""
from __future__ import annotations

from enum import Enum

from oxidant.refinement.clippy_runner import ClippyWarning

# Lint codes where auto-fix is safe (MachineApplicable suggestions only)
_MECHANICAL_CODES: frozenset[str] = frozenset({
    # Rustc built-in
    "unused_imports",
    "unused_variables",
    "unused_mut",
    "dead_code",
    "unreachable_code",
    # Clippy mechanical
    "clippy::redundant_clone",
    "clippy::needless_return",
    "clippy::needless_pass_by_value",
    "clippy::useless_conversion",
    "clippy::map_unwrap_or",
    "clippy::unnecessary_unwrap",
    "clippy::bool_comparison",
    "clippy::redundant_pattern_matching",
    "clippy::single_match",
    "clippy::match_like_matches_macro",
    "clippy::if_let_some_result",
    "clippy::option_if_let_else",
    "clippy::cloned_instead_of_copied",
    "clippy::filter_map_identity",
    "clippy::flat_map_identity",
    "clippy::map_identity",
    "clippy::collapsible_if",
    "clippy::collapsible_else_if",
    "clippy::explicit_iter_loop",
    "clippy::explicit_into_iter_loop",
    "clippy::iter_next_loop",
    "clippy::needless_collect",
    "clippy::unnecessary_fold",
    "clippy::len_zero",
    "clippy::len_without_is_empty",
    "clippy::manual_range_contains",
    "clippy::manual_strip",
    "clippy::manual_find_map",
    "clippy::manual_filter_map",
})

# Lint codes that suggest larger architectural changes
_STRUCTURAL_CODES: frozenset[str] = frozenset({
    "clippy::too_many_arguments",
    "clippy::similar_names",
    "clippy::type_complexity",
    "clippy::large_enum_variant",
    "clippy::large_types_passed_by_value",
    "clippy::rc_buffer",
    "clippy::rc_clone_in_vec_init",
    "clippy::box_collection",
    "clippy::linkedlist",
})


class WarningTier(str, Enum):
    MECHANICAL = "mechanical"    # safe to auto-apply
    STRUCTURAL = "structural"    # needs human approval
    HUMAN = "human"             # requires architectural judgment


def categorize_warning(warning: ClippyWarning) -> WarningTier:
    """Return the WarningTier for a ClippyWarning.

    A warning is MECHANICAL only if its lint code is in the mechanical set
    AND the suggestion is MachineApplicable (safe for `cargo fix`).
    """
    code = warning.lint_code
    if not code:
        return WarningTier.HUMAN

    if code in _MECHANICAL_CODES:
        # Only auto-fix if cargo itself marked it MachineApplicable
        return WarningTier.MECHANICAL if warning.machine_applicable else WarningTier.HUMAN

    if code in _STRUCTURAL_CODES:
        return WarningTier.STRUCTURAL

    return WarningTier.HUMAN
