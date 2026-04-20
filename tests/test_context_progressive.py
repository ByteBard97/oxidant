"""Tests for Progressive Context Disclosure additions to context.py:
  - JIT Unfurling (_parse_error_modules, _load_unfurled_deps)
  - Transitive dep truncated snippets (_load_transitive_dep_snippets)
  - build_prompt integration: unfurl_section and transitive_section appear correctly
"""
from pathlib import Path

import pytest

from oxidant.agents.context import (
    _parse_error_modules,
    _load_module_snippets,
    _load_unfurled_deps,
    _load_transitive_dep_snippets,
    build_prompt,
)
from oxidant.models.manifest import (
    ConversionNode, Manifest, NodeKind, NodeStatus, TranslationTier,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_node(node_id: str, source_file: str = "simple.ts", **kw) -> ConversionNode:
    return ConversionNode(
        node_id=node_id,
        source_file=source_file,
        line_start=1,
        line_end=10,
        source_text="function foo() { return 1; }",
        node_kind=NodeKind.FREE_FUNCTION,
        tier=TranslationTier.HAIKU,
        **kw,
    )


def _make_manifest(nodes: dict) -> Manifest:
    return Manifest(nodes=nodes, source_repo="test", generated_at="2026-04-20")


def _write_snippet(snippets_dir: Path, module: str, node_id: str, body: str) -> Path:
    d = snippets_dir / module
    d.mkdir(parents=True, exist_ok=True)
    safe_id = node_id.replace("/", "_").replace(":", "_")
    p = d / f"{safe_id}.rs"
    p.write_text(body)
    return p


# ── _parse_error_modules ──────────────────────────────────────────────────────

def test_parse_error_modules_extracts_non_target_files():
    error = (
        "src/sweep_event.rs:42:5: error[E0599]: no method `get_y` on enum `SweepEvent`\n"
        "src/algorithm.rs:17:3: error[E0308]: mismatched types\n"
        "src/sweep_event.rs:50:9: error[E0308]: type mismatch\n"
    )
    modules = _parse_error_modules(error, target_rs_filename="src/algorithm.rs")
    # algorithm.rs is the target — excluded. sweep_event.rs is a dep.
    assert "sweep_event" in modules
    assert "algorithm" not in modules


def test_parse_error_modules_deduplicates():
    error = (
        "src/foo.rs:1:1: error[E0001]: something\n"
        "src/foo.rs:2:2: error[E0002]: something else\n"
    )
    modules = _parse_error_modules(error, target_rs_filename="src/bar.rs")
    assert modules.count("foo") == 1


def test_parse_error_modules_empty_when_only_target_errors():
    error = "src/target.rs:10:5: error[E0308]: type mismatch\n"
    modules = _parse_error_modules(error, target_rs_filename="src/target.rs")
    assert modules == []


def test_parse_error_modules_empty_for_non_cargo_output():
    modules = _parse_error_modules("No errors found.", "src/foo.rs")
    assert modules == []


# ── _load_module_snippets ─────────────────────────────────────────────────────

def test_load_module_snippets_finds_matching_nodes(tmp_path):
    snippets_dir = tmp_path / "snippets"
    node_a = _make_node("sweep_event__open_vertex", source_file="sweep_event.ts",
                        status=NodeStatus.CONVERTED)
    snippet_path = _write_snippet(snippets_dir, "sweep_event",
                                  "sweep_event__open_vertex", "fn open_vertex() { 42 }")
    node_a = node_a.model_copy(update={"snippet_path": str(snippet_path)})

    node_b = _make_node("algorithm__run", source_file="algorithm.ts",
                        status=NodeStatus.CONVERTED)

    manifest = _make_manifest({
        "sweep_event__open_vertex": node_a,
        "algorithm__run": node_b,
    })

    result = _load_module_snippets("sweep_event", manifest, char_budget=5000)
    assert "fn open_vertex() { 42 }" in result
    assert "algorithm__run" not in result


def test_load_module_snippets_respects_char_budget(tmp_path):
    snippets_dir = tmp_path / "snippets"
    body = "x" * 500
    node_a = _make_node("foo__a", source_file="foo.ts", status=NodeStatus.CONVERTED)
    node_b = _make_node("foo__b", source_file="foo.ts", status=NodeStatus.CONVERTED)
    sp_a = _write_snippet(snippets_dir, "foo", "foo__a", body)
    sp_b = _write_snippet(snippets_dir, "foo", "foo__b", body)
    node_a = node_a.model_copy(update={"snippet_path": str(sp_a)})
    node_b = node_b.model_copy(update={"snippet_path": str(sp_b)})

    manifest = _make_manifest({"foo__a": node_a, "foo__b": node_b})

    # budget of 600 fits one entry (~515 chars) but not two
    result = _load_module_snippets("foo", manifest, char_budget=600)
    assert "truncated" in result


def test_load_module_snippets_returns_empty_for_unknown_module(tmp_path):
    manifest = _make_manifest({"simple__foo": _make_node("simple__foo")})
    result = _load_module_snippets("nonexistent_module", manifest, char_budget=1000)
    assert result == ""


# ── _load_unfurled_deps ───────────────────────────────────────────────────────

def test_load_unfurled_deps_injects_snippets_for_error_module(tmp_path):
    snippets_dir = tmp_path / "snippets"
    error_text = "src/sweep_event.rs:42:5: error[E0599]: no method found\n"

    body = "pub enum SweepEvent { OpenVertex, CloseVertex }"
    node = _make_node("sweep_event__SweepEvent", source_file="sweep_event.ts",
                      status=NodeStatus.CONVERTED)
    sp = _write_snippet(snippets_dir, "sweep_event", "sweep_event__SweepEvent", body)
    node = node.model_copy(update={"snippet_path": str(sp)})

    manifest = _make_manifest({"sweep_event__SweepEvent": node})

    result = _load_unfurled_deps(error_text, "algorithm.ts", manifest)
    assert "sweep_event" in result
    assert "pub enum SweepEvent" in result


def test_load_unfurled_deps_empty_when_no_cargo_file_refs():
    manifest = _make_manifest({"foo__bar": _make_node("foo__bar")})
    result = _load_unfurled_deps("something went wrong", "foo.ts", manifest)
    assert result == ""


def test_load_unfurled_deps_excludes_target_module(tmp_path):
    snippets_dir = tmp_path / "snippets"
    error_text = "src/target.rs:10:5: error[E0308]: type mismatch\n"

    body = "fn target_fn() {}"
    node = _make_node("target__target_fn", source_file="target.ts",
                      status=NodeStatus.CONVERTED)
    sp = _write_snippet(snippets_dir, "target", "target__target_fn", body)
    node = node.model_copy(update={"snippet_path": str(sp)})

    manifest = _make_manifest({"target__target_fn": node})

    # Error only mentions the target file — should produce nothing to unfurl
    result = _load_unfurled_deps(error_text, "target.ts", manifest)
    assert result == ""


# ── _load_transitive_dep_snippets ─────────────────────────────────────────────

def test_transitive_deps_loads_2_hop_nodes(tmp_path):
    snippets_dir = tmp_path / "snippets"

    # foo → bar → baz. We're building context for foo.
    # bar is a direct dep; baz is transitive.
    baz_body = "\n".join(f"line_{i}" for i in range(30))  # 30 lines
    baz_node = _make_node("baz__func", source_file="baz.ts", status=NodeStatus.CONVERTED)
    sp_baz = _write_snippet(snippets_dir, "baz", "baz__func", baz_body)
    baz_node = baz_node.model_copy(update={"snippet_path": str(sp_baz)})

    bar_node = _make_node(
        "bar__func",
        source_file="bar.ts",
        status=NodeStatus.CONVERTED,
        call_dependencies=["baz__func"],
    )
    foo_node = _make_node(
        "foo__func",
        source_file="foo.ts",
        call_dependencies=["bar__func"],
    )

    manifest = _make_manifest({
        "baz__func": baz_node,
        "bar__func": bar_node,
        "foo__func": foo_node,
    })

    direct_dep_ids = {"bar__func"}
    result = _load_transitive_dep_snippets(foo_node, manifest, direct_dep_ids)

    assert "baz__func" in result
    assert "bar__func" not in result  # already in direct deps, not repeated


def test_transitive_deps_truncates_long_snippets(tmp_path):
    snippets_dir = tmp_path / "snippets"
    long_body = "\n".join(f"line_{i}" for i in range(50))  # 50 lines

    deep_node = _make_node("deep__fn", source_file="deep.ts", status=NodeStatus.CONVERTED)
    sp = _write_snippet(snippets_dir, "deep", "deep__fn", long_body)
    deep_node = deep_node.model_copy(update={"snippet_path": str(sp)})

    mid_node = _make_node(
        "mid__fn",
        source_file="mid.ts",
        status=NodeStatus.CONVERTED,
        type_dependencies=["deep__fn"],
    )
    target_node = _make_node(
        "target__fn",
        source_file="target.ts",
        call_dependencies=["mid__fn"],
    )

    manifest = _make_manifest({
        "deep__fn": deep_node,
        "mid__fn": mid_node,
        "target__fn": target_node,
    })

    result = _load_transitive_dep_snippets(target_node, manifest, {"mid__fn"})
    assert "more lines" in result  # truncation notice
    # Should have at most 20 lines of the body
    content_lines = [l for l in result.splitlines() if l.startswith("line_")]
    assert len(content_lines) <= 20


def test_transitive_deps_empty_when_no_2_hop_nodes():
    foo_node = _make_node("foo__fn", source_file="foo.ts", call_dependencies=["bar__fn"])
    bar_node = _make_node("bar__fn", source_file="bar.ts", status=NodeStatus.CONVERTED)
    manifest = _make_manifest({"foo__fn": foo_node, "bar__fn": bar_node})

    # bar has no further deps — nothing transitive
    result = _load_transitive_dep_snippets(foo_node, manifest, {"bar__fn"})
    assert result == ""


# ── build_prompt integration ──────────────────────────────────────────────────

def test_build_prompt_no_unfurl_on_first_attempt(tmp_path):
    """unfurl_section must NOT appear on attempt 0 even if error text is set."""
    node = _make_node("simple__foo")
    manifest = _make_manifest({"simple__foo": node})
    config = {"crate_inventory": [], "architectural_decisions": {}}

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config=config,
        target_path=tmp_path,
        snippets_dir=tmp_path / "snippets",
        workspace=tmp_path,
        last_error="src/dep.rs:1:1: error[E0308]: type mismatch",
        attempt_count=0,  # first attempt — no unfurl
    )
    assert "Unfurled Dependencies" not in prompt


def test_build_prompt_includes_unfurl_section_on_retry(tmp_path):
    """On retry with a cargo error naming a dep module, unfurl_section appears."""
    snippets_dir = tmp_path / "snippets"
    dep_body = "pub enum SweepEvent { Open, Close }"
    dep_node = _make_node("sweep_event__SweepEvent", source_file="sweep_event.ts",
                          status=NodeStatus.CONVERTED)
    sp = _write_snippet(snippets_dir, "sweep_event", "sweep_event__SweepEvent", dep_body)
    dep_node = dep_node.model_copy(update={"snippet_path": str(sp)})

    target_node = _make_node("algorithm__run", source_file="algorithm.ts")
    manifest = _make_manifest({
        "sweep_event__SweepEvent": dep_node,
        "algorithm__run": target_node,
    })
    config = {"crate_inventory": [], "architectural_decisions": {}}

    prompt = build_prompt(
        node=target_node,
        manifest=manifest,
        config=config,
        target_path=tmp_path,
        snippets_dir=snippets_dir,
        workspace=tmp_path,
        last_error="src/sweep_event.rs:42:5: error[E0599]: no method `get_y`",
        attempt_count=1,
    )
    assert "Unfurled Dependencies" in prompt
    assert "pub enum SweepEvent" in prompt


def test_build_prompt_includes_transitive_section(tmp_path):
    """Transitive (2-hop) deps appear in the prompt even without a retry."""
    snippets_dir = tmp_path / "snippets"
    baz_body = "fn baz_helper() -> i32 { 42 }"
    baz_node = _make_node("baz__helper", source_file="baz.ts", status=NodeStatus.CONVERTED)
    sp = _write_snippet(snippets_dir, "baz", "baz__helper", baz_body)
    baz_node = baz_node.model_copy(update={"snippet_path": str(sp)})

    bar_node = _make_node("bar__fn", source_file="bar.ts",
                          status=NodeStatus.CONVERTED,
                          call_dependencies=["baz__helper"])
    target_node = _make_node("target__fn", source_file="target.ts",
                             call_dependencies=["bar__fn"])

    manifest = _make_manifest({
        "baz__helper": baz_node,
        "bar__fn": bar_node,
        "target__fn": target_node,
    })
    config = {"crate_inventory": [], "architectural_decisions": {}}

    prompt = build_prompt(
        node=target_node,
        manifest=manifest,
        config=config,
        target_path=tmp_path,
        snippets_dir=snippets_dir,
        workspace=tmp_path,
    )
    assert "Transitive Dependencies" in prompt
    assert "baz__helper" in prompt


def test_build_prompt_no_transitive_section_when_no_2hop(tmp_path):
    """No transitive section when deps have no further deps of their own."""
    snippets_dir = tmp_path / "snippets"
    bar_node = _make_node("bar__fn", source_file="bar.ts", status=NodeStatus.CONVERTED)
    target_node = _make_node("target__fn", source_file="target.ts",
                             call_dependencies=["bar__fn"])
    manifest = _make_manifest({"bar__fn": bar_node, "target__fn": target_node})
    config = {"crate_inventory": [], "architectural_decisions": {}}

    prompt = build_prompt(
        node=target_node,
        manifest=manifest,
        config=config,
        target_path=tmp_path,
        snippets_dir=snippets_dir,
        workspace=tmp_path,
    )
    assert "Transitive Dependencies" not in prompt


# ── summary_text preference in transitive deps ────────────────────────────────

def test_transitive_deps_prefers_summary_over_truncated_snippet(tmp_path):
    """When a transitive dep has summary_text, it is used instead of snippet code."""
    snippets_dir = tmp_path / "snippets"

    # deep node has both a snippet file AND a summary — summary should win
    deep_body = "\n".join(f"line_{i}" for i in range(30))
    deep_node = _make_node("deep__fn", source_file="deep.ts", status=NodeStatus.CONVERTED)
    sp = _write_snippet(snippets_dir, "deep", "deep__fn", deep_body)
    deep_node = deep_node.model_copy(update={
        "snippet_path": str(sp),
        "summary_text": "Computes the deep answer by iterating over all nodes.",
    })

    mid_node = _make_node(
        "mid__fn",
        source_file="mid.ts",
        status=NodeStatus.CONVERTED,
        call_dependencies=["deep__fn"],
    )
    target_node = _make_node("target__fn", source_file="target.ts", call_dependencies=["mid__fn"])

    manifest = _make_manifest({
        "deep__fn": deep_node,
        "mid__fn": mid_node,
        "target__fn": target_node,
    })

    result = _load_transitive_dep_snippets(target_node, manifest, {"mid__fn"})

    assert "deep__fn" in result
    assert "Computes the deep answer" in result
    # Should NOT contain raw snippet code lines when summary is available
    assert "line_0" not in result
    assert "more lines" not in result  # no truncation notice when using summary


def test_transitive_deps_falls_back_to_snippet_when_no_summary(tmp_path):
    """When a transitive dep has no summary_text, the truncated snippet is used."""
    snippets_dir = tmp_path / "snippets"

    deep_body = "\n".join(f"line_{i}" for i in range(25))
    deep_node = _make_node("deep__fn", source_file="deep.ts", status=NodeStatus.CONVERTED)
    sp = _write_snippet(snippets_dir, "deep", "deep__fn", deep_body)
    deep_node = deep_node.model_copy(update={"snippet_path": str(sp)})
    # No summary_text set

    mid_node = _make_node(
        "mid__fn",
        source_file="mid.ts",
        status=NodeStatus.CONVERTED,
        call_dependencies=["deep__fn"],
    )
    target_node = _make_node("target__fn", source_file="target.ts", call_dependencies=["mid__fn"])

    manifest = _make_manifest({
        "deep__fn": deep_node,
        "mid__fn": mid_node,
        "target__fn": target_node,
    })

    result = _load_transitive_dep_snippets(target_node, manifest, {"mid__fn"})

    assert "deep__fn" in result
    assert "line_0" in result  # raw snippet lines present
    assert "more lines" in result  # truncation notice (25 lines > 20)


def test_build_prompt_contains_summary_delimiter_instruction():
    """Prompt template must ask the agent to output ---SUMMARY--- after the snippet."""
    node = _make_node("simple__foo")
    manifest = _make_manifest({"simple__foo": node})
    config = {"crate_inventory": [], "architectural_decisions": {}}
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        prompt = build_prompt(
            node=node,
            manifest=manifest,
            config=config,
            target_path=Path(tmp),
            snippets_dir=Path(tmp) / "snippets",
            workspace=Path(tmp),
        )
    assert "---SUMMARY---" in prompt
