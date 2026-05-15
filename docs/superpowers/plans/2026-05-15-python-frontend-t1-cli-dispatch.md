# Task 1: CLI Phase-A Dispatch by Source Language

**Part of:** [Python→Rust Frontend](2026-05-15-python-frontend-overview.md) — do Task 1 before Task 2.

**Goal:** Make `oxidant phase-a` route to the Python extractor scripts when `source_language: "python"` is set in config, and reject unknown languages with a clear error.

**Files:**
- Modify: `src/oxidant/cli.py`
- Modify: `tests/test_cli_phase_a.py`

---

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli_phase_a.py` (file already exists, append). Make sure `import json` is at the top of the file — add it if not:

```python
def test_phase_a_rejects_unknown_language(tmp_path):
    """phase-a should fail fast for unknown source_language."""
    cfg = tmp_path / "oxidant.config.json"
    cfg.write_text(json.dumps({
        "source_language": "cobol",
        "source_repo": str(tmp_path),
        "target_repo": str(tmp_path),
        "model_tiers": {"haiku": "x"},
    }))
    from typer.testing import CliRunner
    from oxidant.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["phase-a", "--config", str(cfg)])
    assert result.exit_code != 0
    assert "cobol" in (result.output + str(result.exception or ""))
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
python -m pytest tests/test_cli_phase_a.py::test_phase_a_rejects_unknown_language -v
```

Expected: FAIL (no language check exists yet).

- [ ] **Step 3: Add language dispatch to cli.py**

In `src/oxidant/cli.py`:

1. Add `import sys` to the imports at the top of the file.
2. Delete **only** the line `tsconfig = cfg["tsconfig"]` (currently near line 33). Do NOT delete `source_root = cfg["source_repo"]` — that line is still needed by both language paths.
3. Replace the A1 and A2 subprocess blocks with:

```python
    source_language = cfg.get("source_language", "typescript")

    if source_language == "typescript":
        tsconfig = cfg.get("tsconfig")
        if not tsconfig:
            typer.echo("Error: 'tsconfig' required in config for TypeScript source.", err=True)
            raise typer.Exit(1)
        # A1: AST extraction
        typer.echo("A1: extracting AST (TypeScript)...")
        subprocess.run(
            ["npx", "tsx", str(_SCRIPTS_DIR / "extract_ast.ts"),
             "--tsconfig", tsconfig,
             "--source-root", source_root,
             "--out", str(manifest_out)],
            check=True,
        )
        # A2: Idiom detection
        typer.echo("A2: detecting idioms (TypeScript)...")
        subprocess.run(
            ["npx", "tsx", str(_SCRIPTS_DIR / "detect_idioms.ts"),
             "--manifest", str(manifest_out)],
            check=True,
        )
    elif source_language == "python":
        # A1: Python AST extraction
        typer.echo("A1: extracting AST (Python)...")
        subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "extract_ast_python.py"),
             "--source-root", source_root,
             "--out", str(manifest_out)],
            check=True,
        )
        # A2: Python idiom detection
        typer.echo("A2: detecting idioms (Python)...")
        subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "detect_idioms_python.py"),
             "--manifest", str(manifest_out)],
            check=True,
        )
    else:
        typer.echo(
            f"Error: unsupported source_language '{source_language}'. "
            f"Supported: typescript, python",
            err=True,
        )
        raise typer.Exit(1)
```

Note: `sys.executable` (not the bare string `"python"`) ensures the same interpreter that runs oxidant is used for the extractor scripts, regardless of PATH.

Also update the A5 skeleton generation call (it already exists in cli.py — just add `config=cfg`):

```python
    # A5: Skeleton generation
    typer.echo("A5: generating Rust skeleton...")
    from oxidant.analysis.generate_skeleton import generate_skeleton
    generate_skeleton(manifest_out, target_repo, config=cfg)
```

Also update the A5 skeleton generation call to pass `config=cfg`:

```python
    # A5: Skeleton generation
    typer.echo("A5: generating Rust skeleton...")
    from oxidant.analysis.generate_skeleton import generate_skeleton
    generate_skeleton(manifest_out, target_repo, config=cfg)
```

- [ ] **Step 4: Run the new test**

```bash
python -m pytest tests/test_cli_phase_a.py::test_phase_a_rejects_unknown_language -v
```

Expected: PASS.

- [ ] **Step 5: Confirm existing TypeScript tests still pass**

```bash
python -m pytest tests/test_cli_phase_a.py -v
```

Expected: all existing tests pass (the TS path is unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/cli.py tests/test_cli_phase_a.py
git commit -m "feat: dispatch phase-a by source_language, validate unknown languages"
```

**Next:** [Task 2 — Python AST extractor](2026-05-15-python-frontend-t2-ast-extractor.md)
