import pytest
from pathlib import Path
from oxidant.models.manifest import (
    ConversionNode, Manifest, NodeKind, NodeStatus, TranslationTier
)


def test_node_roundtrip():
    node = ConversionNode(
        node_id="simple__Point__add",
        source_file="simple.ts",
        line_start=8,
        line_end=10,
        source_text="add(other: Point): Point { return new Point(this.x + other.x, this.y + other.y); }",
        node_kind=NodeKind.METHOD,
        parameter_types={"other": "Point"},
        return_type="Point",
        type_dependencies=["simple__Point"],
        call_dependencies=[],
        callers=["simple__distance"],
        parent_class="simple__Point",
    )
    assert node.status == NodeStatus.NOT_STARTED
    assert node.tier is None
    assert node.snippet_path is None
    data = node.model_dump()
    node2 = ConversionNode(**data)
    assert node2.node_id == node.node_id


def _make_manifest(nodes: dict) -> Manifest:
    """Create an in-memory manifest for testing."""
    return Manifest(nodes=nodes, source_repo=".", generated_at="2026-04-15")


def test_manifest_eligible_nodes_respects_deps():
    nodes = {
        "mod__A": ConversionNode(
            node_id="mod__A", source_file="a.ts", line_start=1, line_end=5,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type="void",
            type_dependencies=[], call_dependencies=[], callers=["mod__B"],
        ),
        "mod__B": ConversionNode(
            node_id="mod__B", source_file="a.ts", line_start=7, line_end=12,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type="void",
            type_dependencies=[], call_dependencies=["mod__A"], callers=[],
        ),
    }
    manifest = _make_manifest(nodes)
    eligible = manifest.eligible_nodes()
    assert len(eligible) == 1
    assert eligible[0].node_id == "mod__A"


def test_manifest_persistence(tmp_path):
    """Nodes written to a file-backed manifest are readable after Manifest.load()."""
    db_path = tmp_path / "test.db"
    nodes = {
        "mod__foo": ConversionNode(
            node_id="mod__foo", source_file="a.ts", line_start=1, line_end=3,
            source_text="function foo() {}", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type="void",
            type_dependencies=[], call_dependencies=[], callers=[],
        )
    }
    Manifest(db_path, source_repo=".", generated_at="2026-04-15", nodes=nodes)
    loaded = Manifest.load(db_path)
    assert loaded.nodes["mod__foo"].source_text == "function foo() {}"


def test_topological_sort_chain():
    # A → B → C (A has no deps; C depends on B; B depends on A)
    nodes = {
        "m__A": ConversionNode(
            node_id="m__A", source_file="x.ts", line_start=1, line_end=2,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=[], callers=["m__B"],
        ),
        "m__B": ConversionNode(
            node_id="m__B", source_file="x.ts", line_start=3, line_end=4,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=["m__A"], callers=["m__C"],
        ),
        "m__C": ConversionNode(
            node_id="m__C", source_file="x.ts", line_start=5, line_end=6,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=["m__B"], call_dependencies=[], callers=[],
        ),
    }
    manifest = _make_manifest(nodes)
    manifest.compute_topology()
    assert manifest.nodes["m__A"].topological_order == 0
    assert manifest.nodes["m__B"].topological_order == 1
    assert manifest.nodes["m__C"].topological_order == 2
    assert manifest.nodes["m__A"].bfs_level == 0
    assert manifest.nodes["m__B"].bfs_level == 1
    assert manifest.nodes["m__C"].bfs_level == 2


def test_topological_sort_parallel_nodes():
    # A and B are both leaves; C depends on both → A and B are level 0, C is level 1
    nodes = {
        "m__A": ConversionNode(
            node_id="m__A", source_file="x.ts", line_start=1, line_end=2,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=[], callers=["m__C"],
        ),
        "m__B": ConversionNode(
            node_id="m__B", source_file="x.ts", line_start=3, line_end=4,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=[], callers=["m__C"],
        ),
        "m__C": ConversionNode(
            node_id="m__C", source_file="x.ts", line_start=5, line_end=6,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=["m__A", "m__B"], call_dependencies=[], callers=[],
        ),
    }
    manifest = _make_manifest(nodes)
    manifest.compute_topology()
    assert manifest.nodes["m__A"].bfs_level == 0
    assert manifest.nodes["m__B"].bfs_level == 0
    assert manifest.nodes["m__C"].bfs_level == 1


def test_topological_sort_cycle_gets_fallback_order():
    """Cycles don't raise — both nodes get distinct fallback topological orders."""
    nodes = {
        "m__A": ConversionNode(
            node_id="m__A", source_file="x.ts", line_start=1, line_end=2,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=["m__B"], call_dependencies=[], callers=[],
        ),
        "m__B": ConversionNode(
            node_id="m__B", source_file="x.ts", line_start=3, line_end=4,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=["m__A"], call_dependencies=[], callers=[],
        ),
    }
    manifest = _make_manifest(nodes)
    manifest.compute_topology()  # must not raise
    result = manifest.nodes
    assert result["m__A"].topological_order is not None
    assert result["m__B"].topological_order is not None
    assert result["m__A"].topological_order != result["m__B"].topological_order
