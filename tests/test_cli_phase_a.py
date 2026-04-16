import json
import subprocess
from pathlib import Path


def test_phase_a_smoke(tmp_path):
    """Run `oxidant phase-a` against the simple fixture; verify manifest + skeleton."""
    config = {
        "source_repo": str(Path("tests/fixtures")),
        "target_repo": str(tmp_path / "output-rs"),
        "source_language": "typescript",
        "target_language": "rust",
        "tsconfig": str(Path("tests/fixtures/simple_tsconfig.json")),
        "architectural_decisions": {
            "graph_ownership_strategy": "arena_slotmap",
            "error_handling": "thiserror",
        },
        "crate_inventory": ["thiserror", "serde", "serde_json"],
        "model_tiers": {
            "haiku": "claude-haiku-4-5-20251001",
            "sonnet": "claude-sonnet-4-6",
            "opus": "claude-opus-4-6",
        },
        "max_attempts": {"haiku": 3, "sonnet": 4, "opus": 5},
        "parallelism": 1,
        "subscription_auth": True,
    }
    config_path = tmp_path / "oxidant.config.json"
    config_path.write_text(json.dumps(config))
    manifest_path = tmp_path / "manifest.json"

    result = subprocess.run(
        [
            "uv", "run", "oxidant", "phase-a",
            "--config", str(config_path),
            "--manifest-out", str(manifest_path),
            "--skip-tiers",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"phase-a failed:\n{result.stderr}\n{result.stdout}"

    assert manifest_path.exists(), "manifest.json not written"
    data = json.loads(manifest_path.read_text())
    assert len(data["nodes"]) > 0, "manifest has no nodes"

    rs_dir = tmp_path / "output-rs"
    assert (rs_dir / "Cargo.toml").exists(), "Cargo.toml not generated"
    assert (rs_dir / "src" / "lib.rs").exists(), "lib.rs not generated"
