from pathlib import Path
import pytest
from oxidant.models.manifest import (
    ConversionNode, Manifest, NodeKind, NodeStatus, TranslationTier,
)
from oxidant.assembly.assemble import assemble_module, check_and_assemble


def _make_node(node_id: str, kind: NodeKind, **kw) -> ConversionNode:
    return ConversionNode(
        node_id=node_id, source_file="m.ts", line_start=1, line_end=5,
        source_text="function foo() {}", node_kind=kind,
        tier=TranslationTier.HAIKU, **kw,
    )


def test_assemble_module_writes_rs_file(tmp_path):
    """assemble_module writes a .rs file with snippet contents."""
    snippets_dir = tmp_path / "snippets" / "m"
    snippets_dir.mkdir(parents=True)

    snippet_path = snippets_dir / "m__foo.rs"
    snippet_path.write_text("42")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "m.rs").write_text(
        '#![allow(dead_code)]\npub fn foo() {\n    todo!("OXIDANT: m__foo")\n}\n'
    )

    nodes = [
        _make_node("m__foo", NodeKind.FREE_FUNCTION,
                   status=NodeStatus.CONVERTED, snippet_path=str(snippet_path)),
    ]
    result = assemble_module("m", nodes, tmp_path)
    assert result is True
    content = (src_dir / "m.rs").read_text()
    assert "42" in content
    assert "m__foo" in content


def test_assemble_module_returns_false_when_not_all_converted(tmp_path):
    """Returns False if any functional node is not yet CONVERTED."""
    (tmp_path / "src").mkdir()
    nodes = [
        _make_node("m__foo", NodeKind.FREE_FUNCTION, status=NodeStatus.NOT_STARTED),
    ]
    result = assemble_module("m", nodes, tmp_path)
    assert result is False


def test_assemble_module_skips_structural_nodes(tmp_path):
    """Structural nodes don't need snippets — module assembles from functional ones only."""
    snippets_dir = tmp_path / "snippets" / "m"
    snippets_dir.mkdir(parents=True)
    snippet_path = snippets_dir / "m__foo.rs"
    snippet_path.write_text("99")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "m.rs").write_text("// skeleton\n")

    nodes = [
        _make_node("m__MyClass", NodeKind.CLASS, status=NodeStatus.CONVERTED),
        _make_node("m__foo", NodeKind.FREE_FUNCTION,
                   status=NodeStatus.CONVERTED, snippet_path=str(snippet_path)),
    ]
    result = assemble_module("m", nodes, tmp_path)
    assert result is True


def test_check_and_assemble_returns_assembled_modules(tmp_path):
    """check_and_assemble returns names of modules that were assembled."""
    snippets_dir = tmp_path / "snippets" / "m"
    snippets_dir.mkdir(parents=True)
    sp = snippets_dir / "m__foo.rs"
    sp.write_text("42")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "m.rs").write_text("// stub\n")

    manifest = Manifest(
        source_repo="t", generated_at="2026-04-15",
        nodes={
            "m__foo": _make_node(
                "m__foo", NodeKind.FREE_FUNCTION,
                status=NodeStatus.CONVERTED, snippet_path=str(sp),
            ),
        },
    )
    assembled = check_and_assemble(manifest, tmp_path)
    assert "m" in assembled
