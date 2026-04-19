# Phase C — Idiomatic Refinement

Phase C runs after Phase B completes (all nodes converted or in the human review queue). Its goal is idiomaticity — making the output *good* Rust, not just *correct* Rust. It does not change behavior; every change must pass the full test suite.

---

## Approach

Phase B agents are instructed to produce faithful, correct translations. They use `Rc<RefCell<T>>` everywhere, `.clone()` freely, and don't restructure logic. This is intentional — correctness first, style second. Phase C then makes a targeted refinement pass.

Phase C runs:

```sh
cargo clippy --all-targets -- -W clippy::pedantic
```

Warnings are categorized by fix type:

| Category | Examples | Handler |
|----------|---------|---------|
| **Mechanical** | Redundant clones, unnecessary `mut`, simple iterator improvements | Haiku agent auto-fixes |
| **Structural** | Replace `Rc<RefCell<>>` with ownership, arena allocation improvements | Sonnet agent proposes; human approves |
| **Human judgment** | Anything requiring architectural decisions | Surfaced to review queue |

---

## Files

| File | Role |
|------|------|
| `refinement/clippy_runner.py` | Runs `cargo clippy`, captures output |
| `refinement/categorize.py` | Classifies each warning by fix category |
| `refinement/phase_c.py` | Orchestrates the refinement loop |
