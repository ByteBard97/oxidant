import json
from pathlib import Path
from unittest.mock import patch

import pytest

from oxidant.agents.context import build_prompt, _extract_rust_signature
from oxidant.models.manifest import (
    ConversionNode, Manifest, NodeKind, NodeStatus, TranslationTier,
)


def _make_node(node_id: str, kind: NodeKind = NodeKind.FREE_FUNCTION, **kw) -> ConversionNode:
    return ConversionNode(
        node_id=node_id,
        source_file="simple.ts",
        line_start=1,
        line_end=5,
        source_text="function foo(x: number): number { return x + 1; }",
        node_kind=kind,
        tier=TranslationTier.HAIKU,
        **kw,
    )


def _make_manifest(nodes: dict) -> Manifest:
    return Manifest(nodes=nodes, source_repo="test", generated_at="2026-04-15")


def test_build_prompt_contains_source():
    """Prompt must include the TypeScript source text."""
    node = _make_node("simple__foo")
    manifest = _make_manifest({"simple__foo": node})
    config = {"crate_inventory": ["serde"], "architectural_decisions": {}}

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config=config,
        target_path=Path("/nonexistent"),
        snippets_dir=Path("/nonexistent/snippets"),
        workspace=Path("/nonexistent"),
    )

    assert "function foo(x: number): number { return x + 1; }" in prompt


def test_build_prompt_contains_crates():
    """Prompt must list the approved crates from config."""
    node = _make_node("simple__foo")
    manifest = _make_manifest({"simple__foo": node})
    config = {"crate_inventory": ["slotmap", "petgraph"], "architectural_decisions": {}}

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config=config,
        target_path=Path("/nonexistent"),
        snippets_dir=Path("/nonexistent/snippets"),
        workspace=Path("/nonexistent"),
    )

    assert "slotmap" in prompt
    assert "petgraph" in prompt


def test_build_prompt_contains_retry_context():
    """On retry, prompt must include the previous error."""
    node = _make_node("simple__foo")
    manifest = _make_manifest({"simple__foo": node})
    config = {"crate_inventory": [], "architectural_decisions": {}}

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config=config,
        target_path=Path("/nonexistent"),
        snippets_dir=Path("/nonexistent/snippets"),
        workspace=Path("/nonexistent"),
        last_error="error[E0308]: type mismatch",
        attempt_count=1,
    )

    assert "error[E0308]" in prompt
    assert "attempt" in prompt.lower()


def test_build_prompt_includes_dep_snippet(tmp_path):
    """When a dep has a snippet on disk, it appears in the prompt."""
    snippets_dir = tmp_path / "snippets" / "simple"
    snippets_dir.mkdir(parents=True)
    dep_snippet = snippets_dir / "simple__bar.rs"
    dep_snippet.write_text("let result = bar_impl();")

    dep_node = _make_node("simple__bar", status=NodeStatus.CONVERTED,
                          snippet_path=str(dep_snippet))
    foo_node = _make_node("simple__foo", call_dependencies=["simple__bar"])

    manifest = _make_manifest({"simple__bar": dep_node, "simple__foo": foo_node})
    config = {"crate_inventory": [], "architectural_decisions": {}}

    prompt = build_prompt(
        node=foo_node,
        manifest=manifest,
        config=config,
        target_path=Path("/nonexistent"),
        snippets_dir=tmp_path / "snippets",
        workspace=tmp_path,
    )

    assert "let result = bar_impl();" in prompt


def test_extract_rust_signature_from_skeleton(tmp_path):
    """Extracts the pub fn line above a todo! marker."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    rs_file = src_dir / "simple.rs"
    rs_file.write_text(
        '#![allow(dead_code)]\n'
        'pub fn distance(a: f64, b: f64) -> f64 {\n'
        '    todo!("OXIDANT: not yet translated — simple__distance")\n'
        '}\n'
    )

    sig = _extract_rust_signature("simple__distance", tmp_path, "simple.ts")
    assert "pub fn distance" in sig
    assert "f64" in sig


def test_extract_rust_signature_missing_returns_comment(tmp_path):
    """Returns a comment when the node_id is not found in the skeleton."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "simple.rs").write_text("// empty\n")

    sig = _extract_rust_signature("simple__nonexistent", tmp_path, "simple.ts")
    assert sig.startswith("//")


def test_build_prompt_includes_supervisor_hint(tmp_path):
    """When supervisor_hint is provided, it appears in the prompt."""
    node = _make_node("foo")
    manifest = _make_manifest({"foo": node})
    config = {"crate_inventory": [], "architectural_decisions": {}}

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config=config,
        target_path=tmp_path,
        snippets_dir=tmp_path,
        workspace=tmp_path,
        supervisor_hint="Use arena allocation instead of Box<dyn Trait>.",
    )
    assert "Supervisor Hint" in prompt
    assert "arena allocation" in prompt


def test_prompt_uses_python_language(tmp_path):
    """build_prompt with source_language=python should not mention TypeScript."""
    from oxidant.agents.context import build_prompt
    from oxidant.models.manifest import ConversionNode, Manifest, NodeKind

    db = tmp_path / "test.db"
    manifest = Manifest.load(db)
    node = ConversionNode(
        node_id="sample__foo",
        source_file="sample.py",
        line_start=1, line_end=5,
        source_text="def foo(): pass",
        node_kind=NodeKind.FREE_FUNCTION,
    )
    manifest.nodes["sample__foo"] = node

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config={
            "source_language": "python",
            "source_repo": ".",
            "crate_inventory": [],
            "architectural_decisions": {},
        },
        target_path=tmp_path,
        snippets_dir=tmp_path,
        workspace=tmp_path,
    )
    assert "TypeScript" not in prompt, "Prompt still contains 'TypeScript'"
    assert "Python" in prompt
    assert "## Python Source" in prompt


def test_prompt_defaults_to_typescript(tmp_path):
    """build_prompt without source_language should still say TypeScript."""
    from oxidant.agents.context import build_prompt
    from oxidant.models.manifest import ConversionNode, Manifest, NodeKind

    db = tmp_path / "test2.db"
    manifest = Manifest.load(db)
    node = ConversionNode(
        node_id="sample__bar",
        source_file="sample.ts",
        line_start=1, line_end=3,
        source_text="function bar() {}",
        node_kind=NodeKind.FREE_FUNCTION,
    )
    manifest.nodes["sample__bar"] = node

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config={"source_repo": ".", "crate_inventory": [], "architectural_decisions": {}},
        target_path=tmp_path,
        snippets_dir=tmp_path,
        workspace=tmp_path,
    )
    assert "TypeScript" in prompt
