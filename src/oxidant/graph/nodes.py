"""LangGraph node functions for the Phase B translation loop.

Each function receives the full OxidantState and returns ONLY the keys it modifies.
Never return {**state, ...} — that would cause the operator.add reducer on
review_queue to double-accumulate existing entries.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from oxidant.agents.context import build_prompt
from oxidant.agents.invoke import invoke_claude
from oxidant.graph.state import OxidantState
from oxidant.models.manifest import Manifest, NodeStatus, TranslationTier
from oxidant.verification.verify import VerifyStatus, verify_snippet

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS: dict[str, int] = {"haiku": 3, "sonnet": 4, "opus": 5}
_DEFAULT_MAX_ATTEMPTS = 3


def pick_next_node(state: OxidantState) -> dict:
    """Select the lowest-topological-order eligible node, or signal done."""
    max_nodes = state.get("max_nodes")
    nodes_this_run = state.get("nodes_this_run", 0)
    if max_nodes is not None and nodes_this_run >= max_nodes:
        logger.info("Reached --max-nodes limit (%d). Stopping.", max_nodes)
        return {"current_node_id": None, "done": True}

    manifest = Manifest.load(Path(state["manifest_path"]))
    eligible = manifest.eligible_nodes()

    if not eligible:
        logger.info("All nodes converted. Phase B complete.")
        return {"current_node_id": None, "done": True}

    node = min(eligible, key=lambda n: n.topological_order or 0)

    # Log when breaking a dependency cycle (node has unconverted in-manifest deps)
    manifest_ids = set(manifest.nodes.keys())
    converted_ids = {
        nid for nid, n in manifest.nodes.items()
        if n.status == NodeStatus.CONVERTED
    }
    unconverted_deps = [
        dep for dep in node.type_dependencies + node.call_dependencies
        if dep in manifest_ids and dep not in converted_ids
    ]
    if unconverted_deps:
        logger.warning(
            "Cycle break: processing %s with %d unconverted deps: %s",
            node.node_id, len(unconverted_deps), unconverted_deps[:3],
        )
    manifest.update_node(
        Path(state["manifest_path"]), node.node_id, status=NodeStatus.IN_PROGRESS
    )

    # config.start_tier overrides per-node tier — lets us default everything to haiku
    start_tier = state.get("config", {}).get("start_tier")
    tier = start_tier or (node.tier.value if node.tier else TranslationTier.HAIKU.value)
    logger.info(
        "Processing %s (tier=%s, bfs_level=%s)", node.node_id, tier, node.bfs_level
    )

    return {
        "current_node_id": node.node_id,
        "current_tier": tier,
        "current_prompt": None,
        "current_snippet": None,
        "attempt_count": 0,
        "last_error": None,
        "verify_status": None,
        "done": False,
    }


def build_context(state: OxidantState) -> dict:
    """Assemble the Claude conversion prompt for the current node."""
    manifest = Manifest.load(Path(state["manifest_path"]))
    node = manifest.nodes[state["current_node_id"]]
    workspace = Path(state["manifest_path"]).parent

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config=state["config"],
        target_path=Path(state["target_path"]),
        snippets_dir=Path(state["snippets_dir"]),
        workspace=workspace,
        last_error=state.get("last_error"),
        attempt_count=state.get("attempt_count", 0),
        supervisor_hint=state.get("supervisor_hint"),
    )
    # Clear the hint so it isn't re-injected on subsequent retries
    return {"current_prompt": prompt, "supervisor_hint": None}


_EMPTY_BODY_RE = re.compile(r"^\s*\w[\w\s<>,*()?:]*\(\s*\)\s*\{[\s]*\}\s*$", re.DOTALL)


def invoke_agent(state: OxidantState) -> dict:
    """Call the Claude Code subprocess and capture the Rust snippet body.

    Short-circuits for trivially empty TS functions (e.g. ``function noop() {}``)
    to avoid wasting an API call — the Rust body is also empty.
    """
    node_id = state.get("current_node_id", "")
    manifest = Manifest.load(Path(state["manifest_path"]))
    node = manifest.nodes.get(node_id)

    # Auto-convert empty-body functions without calling the model
    if node and _EMPTY_BODY_RE.match(node.source_text.strip()):
        logger.info("Auto-converting empty-body function %s", node_id)
        return {"current_snippet": "// empty body — noop", "last_error": None}

    tier = state.get("current_tier") or TranslationTier.HAIKU.value
    model = state.get("config", {}).get("model_tiers", {}).get(tier)
    try:
        response = invoke_claude(
            prompt=state["current_prompt"],
            cwd=state["target_path"],
            tier=tier,
            model=model,
        )
        return {"current_snippet": response, "last_error": None}
    except Exception as exc:  # noqa: BLE001
        logger.error("invoke_claude failed for %s: %s", state.get("current_node_id"), exc)
        return {"current_snippet": None, "last_error": str(exc)}


def verify(state: OxidantState) -> dict:
    """Run the three verification checks (stub / branch parity / cargo check)."""
    manifest = Manifest.load(Path(state["manifest_path"]))
    node = manifest.nodes[state["current_node_id"]]
    snippet = state.get("current_snippet")
    if snippet is None:
        # invoke_agent failed — short-circuit without running cargo check
        return {
            "verify_status": VerifyStatus.CARGO.value,
            "last_error": state.get("last_error") or "Agent invocation failed (no snippet returned)",
        }

    result = verify_snippet(
        node_id=node.node_id,
        snippet=snippet,
        ts_source=node.source_text,
        target_path=Path(state["target_path"]),
        source_file=node.source_file,
    )
    return {
        "verify_status": result.status.value,
        "last_error": result.error or None,
    }


def _escalate_tier(tier: str) -> str | None:
    """Return the next-higher tier, or None if already at opus."""
    if tier == TranslationTier.HAIKU.value:
        return TranslationTier.SONNET.value
    if tier == TranslationTier.SONNET.value:
        return TranslationTier.OPUS.value
    return None


def route_after_verify(state: OxidantState) -> str:
    """Routing function: returns edge name based on verify_status and retry state."""
    if state["verify_status"] == VerifyStatus.PASS:
        return "update_manifest"

    tier = state.get("current_tier") or TranslationTier.HAIKU.value
    attempt = state.get("attempt_count", 0) + 1
    max_attempts = _MAX_ATTEMPTS.get(tier, _DEFAULT_MAX_ATTEMPTS)

    if attempt >= max_attempts:
        if _escalate_tier(tier) is None:
            return "supervisor"
        return "escalate"
    return "retry"


def retry_node(state: OxidantState) -> dict:
    """Increment attempt counter before looping back to build_context."""
    return {"attempt_count": state.get("attempt_count", 0) + 1}


def escalate_node(state: OxidantState) -> dict:
    """Move to next tier and reset attempt counter."""
    tier = state.get("current_tier") or TranslationTier.HAIKU.value
    next_tier = _escalate_tier(tier) or TranslationTier.OPUS.value
    logger.info(
        "Escalating %s: %s → %s", state.get("current_node_id"), tier, next_tier
    )
    return {"current_tier": next_tier, "attempt_count": 0}


def update_manifest(state: OxidantState) -> dict:
    """Save the Rust snippet to disk and mark the node CONVERTED in the manifest."""
    node_id = state["current_node_id"]
    snippet = state.get("current_snippet") or ""

    manifest = Manifest.load(Path(state["manifest_path"]))
    node = manifest.nodes[node_id]

    from oxidant.analysis.generate_skeleton import _module_name
    module = _module_name(node.source_file)
    safe_id = node_id.replace("/", "_").replace(":", "_")

    snippet_dir = Path(state["snippets_dir"]) / module
    snippet_dir.mkdir(parents=True, exist_ok=True)
    snippet_path = snippet_dir / f"{safe_id}.rs"
    snippet_path.write_text(snippet)

    attempt_count = state.get("attempt_count", 0)
    manifest.update_node(
        Path(state["manifest_path"]),
        node_id,
        status=NodeStatus.CONVERTED,
        snippet_path=str(snippet_path),
        attempt_count=attempt_count,
    )
    logger.info("CONVERTED: %s → %s", node_id, snippet_path)
    return {
        "nodes_this_run": state.get("nodes_this_run", 0) + 1,
        # Pass through for SSE event emission — same values already in state
        "current_node_id": node_id,
        "current_tier": state.get("current_tier") or TranslationTier.HAIKU.value,
        "attempt_count": attempt_count,
    }


def queue_for_review(state: OxidantState) -> dict:
    """Add the node to the human review queue and mark it HUMAN_REVIEW."""
    node_id = state["current_node_id"]
    manifest = Manifest.load(Path(state["manifest_path"]))
    node = manifest.nodes[node_id]

    manifest.update_node(
        Path(state["manifest_path"]),
        node_id,
        status=NodeStatus.HUMAN_REVIEW,
        attempt_count=state.get("attempt_count", 0),
        last_error=state.get("last_error"),
    )

    entry = {
        "node_id": node_id,
        "tier": state.get("current_tier"),
        "attempts": state.get("attempt_count", 0),
        "last_error": state.get("last_error", ""),
        "source_text_preview": node.source_text[:300],
    }
    logger.warning("HUMAN_REVIEW: %s (exhausted all retries)", node_id)
    # Return only the NEW entry — the operator.add reducer accumulates it
    return {"review_queue": [entry], "nodes_this_run": state.get("nodes_this_run", 0) + 1}


def route_after_supervisor(state: OxidantState) -> str:
    """If the supervisor provided a hint, retry. If None (human skipped), queue for review."""
    if state.get("supervisor_hint") is not None:
        return "build_context"
    return "queue_for_review"


def supervisor_node(state: OxidantState) -> dict:
    """Generate a targeted hint via Sonnet, then optionally interrupt for human review.

    Fires when a node has exhausted all tiers. Calls invoke_claude with a focused
    hint-generation prompt. In 'interactive' review_mode, calls interrupt() to pause
    the graph for human input.
    """
    node_id = state["current_node_id"]
    manifest = Manifest.load(Path(state["manifest_path"]))
    node = manifest.nodes[node_id]

    hint_prompt = (
        f"You are reviewing a failed TypeScript-to-Rust translation.\n\n"
        f"Node: {node_id}\n"
        f"Last error:\n{(state.get('last_error') or 'unknown')[:500]}\n\n"
        f"TypeScript source:\n```typescript\n{node.source_text[:600]}\n```\n\n"
        f"Generate a 2-3 sentence concrete hint for the translator's next attempt. "
        f"Focus on the specific error and what to do differently. Be concrete, not generic."
    )

    try:
        hint = invoke_claude(
            prompt=hint_prompt,
            cwd=state["target_path"],
            tier="sonnet",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("supervisor_node hint generation failed for %s: %s", node_id, exc)
        hint = None

    review_mode = state.get("review_mode", "auto")
    if review_mode == "interactive":
        from langgraph.types import interrupt as lg_interrupt
        payload = {
            "node_id": node_id,
            "error": state.get("last_error", ""),
            "supervisor_hint": hint,
            "source_preview": node.source_text[:500],
        }
        human_response = lg_interrupt(payload)
        if isinstance(human_response, dict):
            if human_response.get("skip"):
                return {"supervisor_hint": None, "interrupt_payload": None}
            if human_response.get("hint"):
                hint = str(human_response["hint"])

    if hint is not None:
        return {"supervisor_hint": hint, "interrupt_payload": None, "attempt_count": 0}
    return {"supervisor_hint": None, "interrupt_payload": None}
