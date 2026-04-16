import json
import subprocess
from pathlib import Path

FIXTURE_DIR = Path("tests/fixtures")
FIXTURE_TSCONFIG = FIXTURE_DIR / "simple_tsconfig.json"
SCRIPT = Path("phase_a_scripts/extract_ast.ts")


def run_extract(out_path: Path) -> dict:
    result = subprocess.run(
        ["npx", "tsx", str(SCRIPT),
         "--tsconfig", str(FIXTURE_TSCONFIG),
         "--source-root", str(FIXTURE_DIR),
         "--out", str(out_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"extract_ast.ts failed:\n{result.stderr}"
    return json.loads(out_path.read_text())


def test_extracts_class_node(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    class_nodes = [nid for nid, n in data["nodes"].items() if n["node_kind"] == "class"]
    assert any("Point" in nid for nid in class_nodes)


def test_extracts_methods(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    method_nodes = {nid: n for nid, n in data["nodes"].items() if n["node_kind"] == "method"}
    add_node = next((n for nid, n in method_nodes.items() if "add" in nid), None)
    assert add_node is not None
    assert "other" in add_node["parameter_types"]
    assert "Point" in (add_node["return_type"] or "")


def test_extracts_free_function(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    fn_nodes = {nid for nid, n in data["nodes"].items() if n["node_kind"] == "free_function"}
    assert any("distance" in nid for nid in fn_nodes)


def test_extracts_interface(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    iface_nodes = [nid for nid, n in data["nodes"].items() if n["node_kind"] == "interface"]
    assert any("Shape" in nid for nid in iface_nodes)


def test_extracts_enum(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    enum_nodes = [nid for nid, n in data["nodes"].items() if n["node_kind"] == "enum"]
    assert any("Color" in nid for nid in enum_nodes)


def test_parent_class_set_on_methods(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    add_nodes = [n for nid, n in data["nodes"].items() if "Point" in nid and "add" in nid]
    assert add_nodes
    assert add_nodes[0]["parent_class"] is not None
    assert "Point" in add_nodes[0]["parent_class"]


def test_manifest_has_metadata(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    assert data["version"] == "1.0"
    assert "generated_at" in data
    assert "source_repo" in data


def test_cyclomatic_complexity_present(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    # clamp() has 2 if-statements → complexity >= 3
    clamp_node = next((n for nid, n in data["nodes"].items() if "clamp" in nid), None)
    assert clamp_node is not None
    assert clamp_node["cyclomatic_complexity"] >= 3
