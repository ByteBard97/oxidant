import pytest
from pathlib import Path
from oxidant.models.manifest import (
    ConversionNode, Manifest, NodeKind, NodeStatus, TranslationTier
)


def _make_node(node_id: str, kind: NodeKind, **kwargs) -> ConversionNode:
    return ConversionNode(
        node_id=node_id,
        source_file="m.ts",
        line_start=1,
        line_end=10,
        source_text="function foo() {}",
        node_kind=kind,
        tier=TranslationTier.HAIKU,
        **kwargs,
    )


def _make_manifest(nodes: dict) -> Manifest:
    """Create an in-memory manifest for testing."""
    return Manifest(nodes=nodes, source_repo="test", generated_at="2026-04-15")


def test_eligible_nodes_ignores_external_deps():
    """A node whose only dep is outside the manifest should still be eligible."""
    manifest = _make_manifest({
        "m__foo": _make_node(
            "m__foo",
            NodeKind.FREE_FUNCTION,
            call_dependencies=["external__missing"],  # not in manifest
        )
    })
    eligible = manifest.eligible_nodes()
    assert len(eligible) == 1
    assert eligible[0].node_id == "m__foo"


def test_eligible_nodes_blocks_on_known_unconverted_dep():
    """A node blocked on a manifest dep that is NOT_STARTED stays ineligible."""
    manifest = _make_manifest({
        "m__A": _make_node("m__A", NodeKind.FREE_FUNCTION),
        "m__B": _make_node("m__B", NodeKind.FREE_FUNCTION, call_dependencies=["m__A"]),
    })
    eligible_ids = {n.node_id for n in manifest.eligible_nodes()}
    assert "m__A" in eligible_ids
    assert "m__B" not in eligible_ids


def test_eligible_nodes_unblocked_after_dep_converted():
    """After m__A is CONVERTED, m__B becomes eligible."""
    manifest = _make_manifest({
        "m__A": _make_node("m__A", NodeKind.FREE_FUNCTION, status=NodeStatus.CONVERTED),
        "m__B": _make_node("m__B", NodeKind.FREE_FUNCTION, call_dependencies=["m__A"]),
    })
    eligible_ids = {n.node_id for n in manifest.eligible_nodes()}
    assert "m__B" in eligible_ids


def test_auto_convert_structural_nodes(tmp_path):
    """CLASS, INTERFACE, ENUM, TYPE_ALIAS → CONVERTED. FREE_FUNCTION stays NOT_STARTED."""
    db_path = tmp_path / "test.db"
    manifest = Manifest(
        db_path,
        source_repo="test",
        generated_at="2026-04-15",
        nodes={
            "m__MyClass": _make_node("m__MyClass", NodeKind.CLASS),
            "m__IShape": _make_node("m__IShape", NodeKind.INTERFACE),
            "m__Color": _make_node("m__Color", NodeKind.ENUM),
            "m__Alias": _make_node("m__Alias", NodeKind.TYPE_ALIAS),
            "m__distance": _make_node("m__distance", NodeKind.FREE_FUNCTION),
        },
    )
    count = manifest.auto_convert_structural_nodes(db_path)

    assert count == 4
    reloaded = Manifest.load(db_path)
    assert reloaded.nodes["m__MyClass"].status == NodeStatus.CONVERTED
    assert reloaded.nodes["m__IShape"].status == NodeStatus.CONVERTED
    assert reloaded.nodes["m__Color"].status == NodeStatus.CONVERTED
    assert reloaded.nodes["m__Alias"].status == NodeStatus.CONVERTED
    assert reloaded.nodes["m__distance"].status == NodeStatus.NOT_STARTED


def test_auto_convert_skips_already_converted(tmp_path):
    """Nodes already CONVERTED are not double-counted."""
    db_path = tmp_path / "test.db"
    manifest = Manifest(
        db_path,
        source_repo="test",
        generated_at="2026-04-15",
        nodes={
            "m__MyClass": _make_node("m__MyClass", NodeKind.CLASS, status=NodeStatus.CONVERTED),
            "m__IShape": _make_node("m__IShape", NodeKind.INTERFACE),
        },
    )
    count = manifest.auto_convert_structural_nodes(db_path)
    assert count == 1
