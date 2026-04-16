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
    manifest = Manifest(source_repo=".", generated_at="2026-04-15", nodes=nodes)
    eligible = manifest.eligible_nodes()
    assert len(eligible) == 1
    assert eligible[0].node_id == "mod__A"


def test_manifest_json_persistence(tmp_path):
    nodes = {
        "mod__foo": ConversionNode(
            node_id="mod__foo", source_file="a.ts", line_start=1, line_end=3,
            source_text="function foo() {}", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type="void",
            type_dependencies=[], call_dependencies=[], callers=[],
        )
    }
    manifest = Manifest(source_repo=".", generated_at="2026-04-15", nodes=nodes)
    path = tmp_path / "manifest.json"
    manifest.save(path)
    loaded = Manifest.load(path)
    assert loaded.nodes["mod__foo"].source_text == "function foo() {}"
