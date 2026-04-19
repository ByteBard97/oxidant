# CLI Reference

Oxidant is invoked via the `oxidant` command (installed via `uv run oxidant` or `pip install -e .`).

---

## Phase A

```sh
# Full Phase A: extract AST, detect idioms, topological sort,
# Haiku tier classification, generate Rust skeleton
oxidant phase-a

# Skip AI tier classification — use heuristic rules instead
oxidant phase-a --heuristic-tiers

# Regenerate the Rust skeleton only (manifest already exists)
oxidant generate-skeleton

# Reclassify tiers on an existing manifest (no re-extraction)
oxidant classify-tiers
oxidant classify-tiers --heuristic
```

## Phase B

```sh
# Translate all nodes
oxidant phase-b

# Stop after N nodes (smoke test)
oxidant phase-b --max-nodes 5

# Print the first node's prompt without making any API calls
oxidant phase-b --dry-run

# Run with parallel workers
oxidant phase-b --parallelism 4
```

## Serve mode

```sh
# Start the FastAPI server (GUI + HTTP API for Phase B)
oxidant serve
oxidant serve --port 8080
```

## Phase C / D

```sh
# Phase C — Clippy-driven idiomatic refinement
oxidant phase-c

# Phase D — Full build + integration error isolation
oxidant phase-d
```
