"""Oxidant CLI entry point."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import typer

app = typer.Typer(name="oxidant", help="Agentic TypeScript-to-Rust translation harness.",
                   no_args_is_help=True)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "phase_a_scripts"


@app.command("phase-a")
def phase_a(
    config: Path = typer.Option("oxidant.config.json", "--config", "-c"),
    manifest_out: Path = typer.Option("conversion_manifest.json", "--manifest-out"),
    skip_tiers: bool = typer.Option(False, "--skip-tiers",
                                     help="Skip Haiku tier classification (no API call)"),
) -> None:
    """Run the full Phase A analysis pipeline.

    Steps: A1 extract AST → A2 detect idioms → A3 topology → A4 classify tiers → A5 skeleton.
    """
    cfg = json.loads(config.read_text())
    tsconfig    = cfg["tsconfig"]
    source_root = cfg["source_repo"]
    target_repo = Path(cfg["target_repo"])
    model       = cfg["model_tiers"]["haiku"]

    # A1: AST extraction
    typer.echo("A1: extracting AST...")
    subprocess.run(
        ["npx", "tsx", str(_SCRIPTS_DIR / "extract_ast.ts"),
         "--tsconfig", tsconfig,
         "--source-root", source_root,
         "--out", str(manifest_out)],
        check=True,
    )

    # A2: Idiom detection
    typer.echo("A2: detecting idioms...")
    subprocess.run(
        ["npx", "tsx", str(_SCRIPTS_DIR / "detect_idioms.ts"),
         "--manifest", str(manifest_out)],
        check=True,
    )

    # A3: Topological sort
    typer.echo("A3: computing topological order...")
    from oxidant.models.manifest import Manifest
    manifest = Manifest.load(manifest_out)
    try:
        manifest.compute_topology()
    except ValueError as exc:
        typer.echo(f"Warning: {exc} — continuing without full topology", err=True)
    manifest.save(manifest_out)

    # A4: Tier classification
    if skip_tiers:
        typer.echo("A4: skipped (--skip-tiers)")
    else:
        typer.echo("A4: classifying tiers...")
        from oxidant.analysis.classify_tiers import classify_manifest
        classify_manifest(manifest_out, model=model)

    # A5: Skeleton generation
    typer.echo("A5: generating Rust skeleton...")
    from oxidant.analysis.generate_skeleton import generate_skeleton
    generate_skeleton(manifest_out, target_repo)

    # Verify skeleton compiles
    typer.echo("Verifying skeleton compiles...")
    r = subprocess.run(["cargo", "build"], cwd=target_repo, capture_output=True, text=True)
    if r.returncode != 0:
        typer.echo(f"cargo build FAILED:\n{r.stderr}", err=True)
        raise typer.Exit(1)
    typer.echo("Phase A complete. Skeleton compiles.")

    typer.echo("\nNext step (manual): review idiom_candidates.json and generate idiom_dictionary.md")
    typer.echo("  Run a single Opus call with the detected patterns as input.")


@app.command()
def translate(
    source: str = typer.Argument(..., help="Path to a .ts file"),
    out: str = typer.Option("output/", "--out", "-o"),
) -> None:
    """Translate TypeScript to Rust (Phase B — not yet implemented)."""
    typer.echo("Phase B not yet implemented.")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
