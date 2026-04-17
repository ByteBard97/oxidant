"""LangGraph state schema for the Phase B translation loop."""
from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict


class OxidantState(TypedDict):
    # ── Paths and config (set at init, never mutated) ─────────────────────────
    manifest_path: str          # absolute path to conversion_manifest.json
    target_path: str            # absolute path to skeleton project (corpora/msagl-rs)
    snippets_dir: str           # absolute path to snippets output directory
    config: dict                # parsed oxidant.config.json

    # ── Per-node processing (reset by pick_next_node each iteration) ──────────
    current_node_id: Optional[str]
    current_prompt: Optional[str]
    current_snippet: Optional[str]   # raw Rust body text returned by Claude
    current_tier: Optional[str]      # "haiku" | "sonnet" | "opus"
    attempt_count: int               # retries for the current node
    last_error: Optional[str]        # error from last verification or invocation
    verify_status: Optional[str]     # "PASS" | "STUB" | "BRANCH" | "CARGO"

    # ── Accumulating across all iterations (uses add reducer) ─────────────────
    review_queue: Annotated[list[dict], operator.add]

    # ── Loop control ──────────────────────────────────────────────────────────
    done: bool
    max_nodes: Optional[int]     # stop after this many nodes (None = run all)
    nodes_this_run: int          # incremented each time a node completes or is queued

    # ── Supervisor / human-in-the-loop ────────────────────────────────────────
    supervisor_hint: Optional[str]        # hint injected into next build_context call
    interrupt_payload: Optional[dict]     # data surfaced to human reviewer via interrupt()
    review_mode: str                      # "auto" | "interactive" | "supervised"
