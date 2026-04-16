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


@app.command("phase-b")
def phase_b(
    config: Path = typer.Option("oxidant.config.json", "--config", "-c"),
    manifest: Path = typer.Option("conversion_manifest.json", "--manifest"),
    snippets_dir: Path = typer.Option("snippets", "--snippets-dir"),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Print the first node's prompt then exit — no API calls made.",
    ),
) -> None:
    """Run Phase B: translate all nodes in topological order via Claude Code.

    Requires a compiled skeleton from ``oxidant phase-a``.
    Structural nodes (class/interface/enum/type_alias) are auto-converted first.
    Exhausted nodes are written to ``review_queue.json``.
    """
    import json as _json

    from oxidant.assembly.assemble import check_and_assemble
    from oxidant.graph.graph import translation_graph
    from oxidant.graph.nodes import build_context, pick_next_node
    from oxidant.graph.state import OxidantState
    from oxidant.models.manifest import Manifest as _Manifest

    cfg = _json.loads(config.read_text())
    manifest_obj = _Manifest.load(manifest)

    count = manifest_obj.auto_convert_structural_nodes(manifest)
    if count:
        typer.echo(f"Auto-converted {count} structural nodes.")

    snippets_dir.mkdir(parents=True, exist_ok=True)
    target_path = Path(cfg["target_repo"])

    initial_state = OxidantState(
        manifest_path=str(manifest.resolve()),
        target_path=str(target_path.resolve()),
        snippets_dir=str(snippets_dir.resolve()),
        config=cfg,
        current_node_id=None,
        current_prompt=None,
        current_snippet=None,
        current_tier=None,
        attempt_count=0,
        last_error=None,
        verify_status=None,
        review_queue=[],
        done=False,
    )

    if dry_run:
        s = pick_next_node(initial_state)
        if s.get("done"):
            typer.echo("No eligible nodes — all CONVERTED or blocked.")
            return
        # Merge update back into state for build_context
        merged = {**initial_state, **s}
        s2 = build_context(merged)
        node_id = s.get("current_node_id")
        prompt = s2.get("current_prompt", "")
        typer.echo(f"Node: {node_id}")
        typer.echo(f"Prompt length: {len(prompt)} chars")
        typer.echo("\n--- prompt (first 3000 chars) ---")
        typer.echo(prompt[:3000])
        return

    final_state = translation_graph.invoke(initial_state)

    review_queue = final_state.get("review_queue", [])
    if review_queue:
        import json
        rq_path = Path("review_queue.json")
        rq_path.write_text(json.dumps(review_queue, indent=2))
        typer.echo(f"\n{len(review_queue)} nodes queued for human review → {rq_path}")

    manifest_final = _Manifest.load(manifest)
    assembled = check_and_assemble(manifest_final, target_path)
    if assembled:
        typer.echo(f"Assembled {len(assembled)} module(s).")

    typer.echo("\nPhase B complete.")


@app.command("phase-c")
def phase_c(
    config: Path = typer.Option("oxidant.config.json", "--config", "-c"),
    target: Path = typer.Option(
        None, "--target",
        help="Rust project root. Defaults to target_repo from config.",
    ),
) -> None:
    """Run Phase C: auto-fix mechanical Clippy warnings, report structural/human ones.

    Requires a partially or fully translated skeleton from phase-b.
    Writes ``clippy_report.json`` to the target project root.
    """
    import json as _json
    from oxidant.refinement.phase_c import run_phase_c

    cfg = _json.loads(config.read_text())
    target_path = target or Path(cfg["target_repo"])

    typer.echo(f"Phase C: running Clippy refinement on {target_path}...")
    report = run_phase_c(target_path.resolve())

    typer.echo(f"  Auto-fixed:  {report.auto_fixed_count} warnings")
    typer.echo(f"  Remaining:   {report.total_remaining}")
    typer.echo(f"    Mechanical: {report.mechanical_count}")
    typer.echo(f"    Structural: {report.structural_count}")
    typer.echo(f"    Human:      {report.human_count}")
    typer.echo(f"\nReport written to {target_path / 'clippy_report.json'}")


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
