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
                                     help="Skip tier classification entirely."),
    heuristic_tiers: bool = typer.Option(False, "--heuristic-tiers",
                                          help="Use deterministic heuristic tiers (no API call)."),
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
    elif heuristic_tiers:
        typer.echo("A4: classifying tiers (heuristic, no API call)...")
        from oxidant.analysis.classify_tiers import classify_manifest_heuristic
        classify_manifest_heuristic(manifest_out)
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


@app.command("classify-tiers")
def classify_tiers(
    manifest: Path = typer.Option("conversion_manifest.json", "--manifest"),
    heuristic: bool = typer.Option(False, "--heuristic",
                                    help="Use deterministic rules (no API call)."),
    config: Path = typer.Option("oxidant.config.json", "--config", "-c"),
) -> None:
    """Run tier classification (A4) on an existing manifest without re-running Phase A.

    By default uses Claude Haiku (requires ANTHROPIC_API_KEY). Pass --heuristic to
    use deterministic rules instead.
    """
    from oxidant.analysis.classify_tiers import classify_manifest, classify_manifest_heuristic

    if heuristic:
        typer.echo("Classifying tiers (heuristic, no API call)...")
        classify_manifest_heuristic(manifest)
    else:
        cfg = json.loads(config.read_text())
        model = cfg["model_tiers"]["haiku"]
        typer.echo(f"Classifying tiers with {model}...")
        classify_manifest(manifest, model=model)

    import json as _json
    with open(manifest) as f:
        m = _json.load(f)
    nodes = m["nodes"]
    from collections import Counter
    tier_counts = Counter(n.get("tier") for n in nodes.values())
    total = len(nodes)
    typer.echo(f"Done. {total} nodes:")
    for tier, count in sorted(tier_counts.items(), key=lambda x: x[0] or ""):
        typer.echo(f"  {tier or 'None':8s}  {count}")


@app.command("import-manifest")
def import_manifest(
    manifest: Path = typer.Argument(..., help="Path to conversion_manifest.json"),
    db: Path = typer.Option("oxidant.db", "--db", help="Output SQLite DB path."),
) -> None:
    """Import a JSON conversion manifest into SQLite.

    One-time migration: reads conversion_manifest.json, creates oxidant.db,
    and bulk-inserts all nodes. Phase A keeps writing JSON; run this once to
    seed the DB before starting Phase B.
    """
    import json as _json
    from oxidant.models.db import NodeRecord, ManifestMeta
    from oxidant.models.manifest import ConversionNode, _get_engine
    from sqlmodel import Session, SQLModel

    if not manifest.exists():
        typer.echo(f"Error: {manifest} not found.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Reading {manifest}...")
    data = _json.loads(manifest.read_text())
    nodes_raw = data.get("nodes", {})

    engine = _get_engine(db)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # Upsert manifest meta
        meta = session.get(ManifestMeta, 1)
        if meta is None:
            meta = ManifestMeta(
                id=1,
                version=data.get("version", "1.0"),
                source_repo=data.get("source_repo", ""),
                generated_at=data.get("generated_at", ""),
            )
        else:
            meta.version = data.get("version", meta.version)
            meta.source_repo = data.get("source_repo", meta.source_repo)
            meta.generated_at = data.get("generated_at", meta.generated_at)
        session.add(meta)

        # Upsert all nodes
        inserted = updated = 0
        for node_id, raw in nodes_raw.items():
            raw["node_id"] = raw.get("node_id") or node_id
            node = ConversionNode.model_validate(raw)
            row = session.get(NodeRecord, node_id)
            if row is None:
                session.add(NodeRecord.from_conversion_node(node))
                inserted += 1
            else:
                # Preserve Phase B progress (status, snippet_path, attempt_count)
                # but refresh everything else from JSON
                new_row = NodeRecord.from_conversion_node(node)
                new_row.status = row.status
                new_row.snippet_path = row.snippet_path
                new_row.attempt_count = row.attempt_count
                new_row.last_error = row.last_error
                session.add(new_row)
                updated += 1
        session.commit()

    typer.echo(f"Done. {db}: {inserted} inserted, {updated} updated ({len(nodes_raw)} total).")


@app.command("phase-b")
def phase_b(
    config: Path = typer.Option("oxidant.config.json", "--config", "-c"),
    db: Path = typer.Option("oxidant.db", "--db", help="Path to oxidant SQLite manifest DB."),
    snippets_dir: Path = typer.Option("snippets", "--snippets-dir"),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Print the first node's prompt then exit — no API calls made.",
    ),
    max_nodes: int = typer.Option(
        None, "--max-nodes",
        help="Stop after translating this many nodes. Useful for smoke tests.",
    ),
) -> None:
    """Run Phase B: translate all nodes in topological order via Claude Code.

    Requires a compiled skeleton from ``oxidant phase-a`` and an oxidant.db
    seeded by ``oxidant import-manifest``.
    Structural nodes (class/interface/enum/type_alias) are auto-converted first.
    Exhausted nodes are written to ``review_queue.json``.
    """
    import json as _json

    from oxidant.assembly.assemble import check_and_assemble
    from oxidant.graph.nodes import build_context, pick_next_node
    from oxidant.graph.state import OxidantState
    from oxidant.models.manifest import Manifest as _Manifest

    if not db.exists():
        typer.echo(
            f"Error: {db} not found. Run `oxidant import-manifest conversion_manifest.json` first.",
            err=True,
        )
        raise typer.Exit(1)

    cfg = _json.loads(config.read_text())
    manifest_obj = _Manifest.load(db)

    count = manifest_obj.auto_convert_structural_nodes(db)
    if count:
        typer.echo(f"Auto-converted {count} structural nodes.")

    snippets_dir.mkdir(parents=True, exist_ok=True)
    target_path = Path(cfg["target_repo"])

    initial_state = OxidantState(
        db_path=str(db.resolve()),
        target_path=str(target_path.resolve()),
        snippets_dir=str(snippets_dir.resolve()),
        config=cfg,
        worker_id=0,
        current_node_id=None,
        current_prompt=None,
        current_snippet=None,
        current_tier=None,
        attempt_count=0,
        last_error=None,
        verify_status=None,
        review_queue=[],
        done=False,
        max_nodes=max_nodes,
        nodes_this_run=0,
        supervisor_hint=None,
        interrupt_payload=None,
        review_mode=cfg.get("review_mode", "auto"),
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

    parallelism = cfg.get("parallelism", 1)

    if parallelism > 1:
        import asyncio
        from oxidant.graph.graph import build_graph
        from oxidant.graph.nodes import setup_worker_clones

        typer.echo(f"Parallel mode: {parallelism} workers")
        setup_worker_clones(target_path, parallelism)

        async def run_parallel() -> list[dict]:
            graphs = [build_graph() for _ in range(parallelism)]
            coros = [
                g.ainvoke({**initial_state, "worker_id": i})
                for i, g in enumerate(graphs)
            ]
            return list(await asyncio.gather(*coros))

        results = asyncio.run(run_parallel())
        # Merge review queues from all workers
        review_queue: list[dict] = []
        for r in results:
            review_queue.extend(r.get("review_queue", []))
    else:
        from oxidant.graph.graph import translation_graph
        final_state = translation_graph.invoke(initial_state)
        review_queue = final_state.get("review_queue", [])

    if review_queue:
        import json
        rq_path = Path("review_queue.json")
        rq_path.write_text(json.dumps(review_queue, indent=2))
        typer.echo(f"\n{len(review_queue)} nodes queued for human review → {rq_path}")

    manifest_final = _Manifest.load(db)
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


@app.command("phase-d")
def phase_d(
    config: Path = typer.Option("oxidant.config.json", "--config", "-c"),
    target: Path = typer.Option(
        None, "--target",
        help="Rust project root. Defaults to target_repo from config.",
    ),
    manifest: Path = typer.Option(
        None, "--manifest",
        help="Path to conversion_manifest.json for retranslation hints.",
    ),
) -> None:
    """Run Phase D: full build verification and integration error isolation.

    Runs ``cargo build --release`` on the target Rust project, parses
    integration errors, and writes ``integration_report.json``.
    Pass ``--manifest`` to also identify which translated files need re-translation.
    """
    import json as _json
    from oxidant.integration.integration_debug import run_phase_d

    cfg = _json.loads(config.read_text())
    target_path = target or Path(cfg["target_repo"])

    typer.echo(f"Phase D: running full build on {target_path}...")
    report = run_phase_d(target_path.resolve(), manifest_path=manifest)

    status = "PASS" if report.build_success else "FAIL"
    typer.echo(f"  Build:       {status}")
    typer.echo(f"  Errors:      {report.total_errors}")
    typer.echo(f"  Files:       {len(report.files_with_errors)}")
    if report.files_needing_retranslation:
        typer.echo(f"  Retranslate: {len(report.files_needing_retranslation)} file(s)")
        for f in report.files_needing_retranslation:
            typer.echo(f"    {f}")
    typer.echo(f"\nReport written to {target_path.resolve() / 'integration_report.json'}")


@app.command("serve")
def serve(
    config: Path = typer.Option("oxidant.config.json", "--config", "-c"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    db_path: str = typer.Option("oxidant_checkpoints.db", "--db",
                                 help="Path to SqliteSaver checkpoint DB"),
    gui_dist: str = typer.Option(None, "--gui-dist",
                                  help="Path to built Vue GUI dist/ directory"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (dev only)"),
) -> None:
    """Start the FastAPI server for Phase B monitoring and control.

    Opens the oxidant dashboard at http://<host>:<port>/
    Start a run with: POST /run  {manifest_path, target_path, ...}
    Stream progress with: GET /stream/{thread_id}
    """
    import uvicorn
    from oxidant.serve.app import create_app

    typer.echo(f"Starting oxidant serve on http://{host}:{port}")
    if gui_dist:
        typer.echo(f"Serving GUI from {gui_dist}")
    else:
        typer.echo("No GUI dist provided. API-only mode. Pass --gui-dist to serve the dashboard.")

    application = create_app(db_path=db_path, gui_dist=gui_dist, config_path=str(config.resolve()))
    uvicorn.run(application, host=host, port=port, reload=reload)


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
