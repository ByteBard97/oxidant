import json
import subprocess
from pathlib import Path

FIXTURE_DIR   = Path("tests/fixtures")
EXTRACT       = Path("phase_a_scripts/extract_ast.ts")
DETECT_IDIOMS = Path("phase_a_scripts/detect_idioms.ts")


def run_pipeline(tmp_path: Path, tsconfig: str, source_root: str) -> dict:
    mpath = tmp_path / "manifest.json"
    r1 = subprocess.run(
        ["npx", "tsx", str(EXTRACT),
         "--tsconfig", tsconfig,
         "--source-root", source_root,
         "--out", str(mpath)],
        capture_output=True, text=True,
    )
    assert r1.returncode == 0, r1.stderr
    r2 = subprocess.run(
        ["npx", "tsx", str(DETECT_IDIOMS), "--manifest", str(mpath)],
        capture_output=True, text=True,
    )
    assert r2.returncode == 0, r2.stderr
    return json.loads(mpath.read_text())


def test_optional_chaining_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "getFirstItem" in nid), None)
    assert node and "optional_chaining" in node["idioms_needed"]


def test_null_undefined_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "getName" in nid), None)
    assert node and "null_undefined" in node["idioms_needed"]


def test_array_method_chain_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "getDoubled" in nid), None)
    assert node and "array_method_chain" in node["idioms_needed"]


def test_closure_capture_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "makeAdder" in nid), None)
    assert node and "closure_capture" in node["idioms_needed"]


def test_map_usage_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "buildIndex" in nid), None)
    assert node and "map_usage" in node["idioms_needed"]


def test_async_await_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "fetchData" in nid), None)
    assert node and "async_await" in node["idioms_needed"]
