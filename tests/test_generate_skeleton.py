import subprocess
from pathlib import Path

import pytest

from oxidant.models.manifest import ConversionNode, Manifest, NodeKind, TranslationTier
from oxidant.analysis.generate_skeleton import map_ts_type, generate_skeleton


# ── Type mapper unit tests ────────────────────────────────────────────────────

def test_map_number():      assert map_ts_type("number") == "f64"
def test_map_string():      assert map_ts_type("string") == "String"
def test_map_bool():        assert map_ts_type("boolean") == "bool"
def test_map_void():        assert map_ts_type("void") == "()"
def test_map_array():       assert map_ts_type("number[]") == "Vec<f64>"
def test_map_generic_array(): assert map_ts_type("Array<string>") == "Vec<String>"
def test_map_nullable():
    assert map_ts_type("string | null") == "Option<String>"
    assert map_ts_type("number | undefined") == "Option<f64>"
def test_map_known_class():
    # When Point is in the known_classes set, it wraps in Rc<RefCell<>>
    assert map_ts_type("Point", known_classes={"Point"}) == "Rc<RefCell<Point>>"

def test_map_unknown_type_falls_back():
    # Unknown PascalCase types not in any manifest map → serde_json::Value
    assert map_ts_type("UnknownType") == "serde_json::Value"
def test_map_map_type():
    assert map_ts_type("Map<string, number>") == "std::collections::HashMap<String, f64>"

def test_map_set_type():
    assert map_ts_type("Set<string>") == "std::collections::HashSet<String>"


# ── Integration: generated skeleton must compile ──────────────────────────────

def _make_manifest() -> Manifest:
    nodes = {
        "simple__Point": ConversionNode(
            node_id="simple__Point", source_file="simple.ts",
            line_start=1, line_end=20, source_text="class Point {}",
            node_kind=NodeKind.CLASS, parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=[], callers=[],
            tier=TranslationTier.HAIKU,
        ),
        "simple__Point__constructor": ConversionNode(
            node_id="simple__Point__constructor", source_file="simple.ts",
            line_start=3, line_end=6,
            source_text="constructor(x: number, y: number) {}",
            node_kind=NodeKind.CONSTRUCTOR,
            parameter_types={"x": "number", "y": "number"}, return_type="Point",
            type_dependencies=["simple__Point"], call_dependencies=[], callers=[],
            parent_class="simple__Point", tier=TranslationTier.HAIKU,
        ),
        "simple__Point__add": ConversionNode(
            node_id="simple__Point__add", source_file="simple.ts",
            line_start=8, line_end=10,
            source_text="add(other: Point): Point { return new Point(0,0); }",
            node_kind=NodeKind.METHOD,
            parameter_types={"other": "Point"}, return_type="Point",
            type_dependencies=["simple__Point"], call_dependencies=[],
            callers=[], parent_class="simple__Point", tier=TranslationTier.HAIKU,
        ),
        "simple__Color": ConversionNode(
            node_id="simple__Color", source_file="simple.ts",
            line_start=25, line_end=29, source_text='enum Color { Red = "RED" }',
            node_kind=NodeKind.ENUM, parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=[], callers=[],
            tier=TranslationTier.HAIKU,
        ),
        "simple__distance": ConversionNode(
            node_id="simple__distance", source_file="simple.ts",
            line_start=32, line_end=37,
            source_text="function distance(a: Point, b: Point): number { return 0; }",
            node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={"a": "Point", "b": "Point"}, return_type="number",
            type_dependencies=["simple__Point"], call_dependencies=[], callers=[],
            tier=TranslationTier.HAIKU,
        ),
    }
    return Manifest(source_repo="tests/fixtures", generated_at="2026-04-15", nodes=nodes)


def test_cargo_build_passes(tmp_path):
    manifest = _make_manifest()
    mpath = tmp_path / "manifest.json"
    manifest.save(mpath)
    target = tmp_path / "msagl-rs"
    generate_skeleton(mpath, target)
    r = subprocess.run(["cargo", "build"], cwd=target, capture_output=True, text=True)
    assert r.returncode == 0, f"cargo build failed:\n{r.stderr}"


def test_todo_markers_present(tmp_path):
    manifest = _make_manifest()
    mpath = tmp_path / "manifest.json"
    manifest.save(mpath)
    target = tmp_path / "msagl-rs"
    generate_skeleton(mpath, target)
    all_rs = "\n".join(f.read_text() for f in target.rglob("*.rs"))
    assert "OXIDANT" in all_rs
