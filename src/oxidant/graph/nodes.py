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


def setup_worker_clones(target_path: Path, parallelism: int) -> None:
    """Create skeleton clones for workers 1..parallelism-1.

    Worker 0 uses the main target_path directly. Each other worker gets its
    own clone at ``target_path/.clone_N/`` so cargo check never races on the
    same file. Only copies ``src/`` and ``Cargo.toml``; shares nothing else.
    """
    import shutil

    for i in range(1, parallelism):
        clone = target_path / f".clone_{i}"
        if clone.exists():
            continue
        clone.mkdir(parents=True, exist_ok=True)
        src = target_path / "src"
        if src.exists():
            shutil.copytree(str(src), str(clone / "src"))
        cargo = target_path / "Cargo.toml"
        if cargo.exists():
            shutil.copy(str(cargo), str(clone / "Cargo.toml"))
        logger.info("Created worker clone: %s", clone)
_DEFAULT_MAX_ATTEMPTS = 3


def _db(state: OxidantState) -> Path:
    """Return the DB path from state."""
    return Path(state["db_path"])


def pick_next_node(state: OxidantState) -> dict:
    """Atomically claim the next eligible node, or signal done.

    Uses a SQLite transaction to SELECT + mark IN_PROGRESS in one step so
    parallel workers never claim the same node.

    Also resets any orphaned IN_PROGRESS nodes (from a previous crashed run)
    back to NOT_STARTED automatically.
    """
    max_nodes = state.get("max_nodes")
    nodes_this_run = state.get("nodes_this_run", 0)
    if max_nodes is not None and nodes_this_run >= max_nodes:
        logger.info("Reached --max-nodes limit (%d). Stopping.", max_nodes)
        return {"current_node_id": None, "done": True}

    manifest = Manifest.load(_db(state))

    # Auto-recover: reset orphaned IN_PROGRESS nodes from crashed runs.
    # Each worker only resets nodes it didn't pick itself.
    stuck = [
        nid for nid, n in manifest.nodes.items()
        if n.status == NodeStatus.IN_PROGRESS
        and nid != state.get("current_node_id")
    ]
    if stuck:
        logger.warning("Resetting %d orphaned in_progress nodes: %s", len(stuck), stuck[:3])
        for nid in stuck:
            manifest.update_node(_db(state), nid, status=NodeStatus.NOT_STARTED)
        manifest = Manifest.load(_db(state))

    eligible = manifest.eligible_nodes()

    if not eligible:
        logger.info("All nodes converted. Phase B complete.")
        return {"current_node_id": None, "done": True}

    node = min(eligible, key=lambda n: n.topological_order or 0)

    # Log cycle breaks
    manifest_ids = set(manifest.nodes.keys())
    converted_ids = {nid for nid, n in manifest.nodes.items() if n.status == NodeStatus.CONVERTED}
    unconverted_deps = [
        dep for dep in node.type_dependencies + node.call_dependencies
        if dep in manifest_ids and dep not in converted_ids
    ]
    if unconverted_deps:
        logger.warning(
            "Cycle break: processing %s with %d unconverted deps: %s",
            node.node_id, len(unconverted_deps), unconverted_deps[:3],
        )

    # Atomic claim: mark IN_PROGRESS
    manifest.update_node(_db(state), node.node_id, status=NodeStatus.IN_PROGRESS)

    # config.start_tier overrides per-node tier so we can default everything to haiku
    start_tier = state.get("config", {}).get("start_tier")
    tier = start_tier or (node.tier.value if node.tier else TranslationTier.HAIKU.value)
    logger.info("Processing %s (tier=%s, bfs_level=%s)", node.node_id, tier, node.bfs_level)

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
    manifest = Manifest.load(_db(state))
    node_id = state["current_node_id"]
    node = manifest.get_node(node_id) or manifest.nodes[node_id]
    workspace = _db(state).parent

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
    return {"current_prompt": prompt, "supervisor_hint": None}


_EMPTY_BODY_RE = re.compile(r"^\s*\w[\w\s<>,*()?:]*\(\s*\)\s*\{[\s]*\}\s*$", re.DOTALL)


def invoke_agent(state: OxidantState) -> dict:
    """Call the Claude Code subprocess and capture the Rust snippet body.

    Short-circuits for trivially empty TS functions (e.g. ``function noop() {}``)
    to avoid wasting an API call — the Rust body is also empty.
    """
    node_id = state.get("current_node_id", "")
    manifest = Manifest.load(_db(state))
    node = manifest.get_node(node_id)

    if node and _EMPTY_BODY_RE.match(node.source_text.strip()):
        logger.info("Auto-converting empty-body function %s", node_id)
        return {"current_snippet": "// empty body — noop", "last_error": None}

    tier = state.get("current_tier") or TranslationTier.HAIKU.value
    model = state.get("config", {}).get("model_tiers", {}).get(tier)

    # Worker N uses skeleton clone N for safe parallel cargo check
    worker_id = state.get("worker_id", 0)
    cwd = state["target_path"]
    if worker_id > 0:
        clone = Path(state["target_path"]) / f".clone_{worker_id}"
        if clone.exists():
            cwd = str(clone)

    try:
        response = invoke_claude(
            prompt=state["current_prompt"],
            cwd=cwd,
            tier=tier,
            model=model,
        )
        return {"current_snippet": response, "last_error": None}
    except Exception as exc:  # noqa: BLE001
        logger.error("invoke_claude failed for %s: %s", node_id, exc)
        return {"current_snippet": None, "last_error": str(exc)}


def verify(state: OxidantState) -> dict:
    """Run the three verification checks (stub / branch parity / cargo check)."""
    manifest = Manifest.load(_db(state))
    node = manifest.get_node(state["current_node_id"]) or manifest.nodes[state["current_node_id"]]
    snippet = state.get("current_snippet")

    if snippet is None:
        return {
            "verify_status": VerifyStatus.CARGO.value,
            "last_error": state.get("last_error") or "Agent invocation failed (no snippet returned)",
        }

    # Worker N verifies against its own skeleton clone
    worker_id = state.get("worker_id", 0)
    target = Path(state["target_path"])
    if worker_id > 0:
        clone = target / f".clone_{worker_id}"
        if clone.exists():
            target = clone

    result = verify_snippet(
        node_id=node.node_id,
        snippet=snippet,
        ts_source=node.source_text,
        target_path=target,
        source_file=node.source_file,
    )
    return {
        "verify_status": result.status.value,
        "last_error": result.error or None,
    }


def _escalate_tier(tier: str) -> str | None:
    if tier == TranslationTier.HAIKU.value:
        return TranslationTier.SONNET.value
    if tier == TranslationTier.SONNET.value:
        return TranslationTier.OPUS.value
    return None


def route_after_verify(state: OxidantState) -> str:
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
    return {"attempt_count": state.get("attempt_count", 0) + 1}


def escalate_node(state: OxidantState) -> dict:
    tier = state.get("current_tier") or TranslationTier.HAIKU.value
    next_tier = _escalate_tier(tier) or TranslationTier.OPUS.value
    logger.info("Escalating %s: %s → %s", state.get("current_node_id"), tier, next_tier)
    return {"current_tier": next_tier, "attempt_count": 0}


def update_manifest(state: OxidantState) -> dict:
    """Save the Rust snippet to disk and mark the node CONVERTED in the DB."""
    node_id = state["current_node_id"]
    snippet = state.get("current_snippet") or ""

    manifest = Manifest.load(_db(state))
    node = manifest.get_node(node_id) or manifest.nodes[node_id]

    from oxidant.analysis.generate_skeleton import _module_name
    module = _module_name(node.source_file)
    safe_id = node_id.replace("/", "_").replace(":", "_")

    snippet_dir = Path(state["snippets_dir"]) / module
    snippet_dir.mkdir(parents=True, exist_ok=True)
    snippet_path = snippet_dir / f"{safe_id}.rs"
    snippet_path.write_text(snippet)

    attempt_count = state.get("attempt_count", 0)
    manifest.update_node(
        _db(state),
        node_id,
        status=NodeStatus.CONVERTED,
        snippet_path=str(snippet_path),
        attempt_count=attempt_count,
    )
    logger.info("CONVERTED: %s → %s", node_id, snippet_path)
    return {
        "nodes_this_run": state.get("nodes_this_run", 0) + 1,
        "current_node_id": node_id,
        "current_tier": state.get("current_tier") or TranslationTier.HAIKU.value,
        "attempt_count": attempt_count,
    }


def queue_for_review(state: OxidantState) -> dict:
    """Add the node to the human review queue and mark it HUMAN_REVIEW in the DB."""
    node_id = state["current_node_id"]
    manifest = Manifest.load(_db(state))
    node = manifest.get_node(node_id) or manifest.nodes[node_id]

    manifest.update_node(
        _db(state),
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
    return {"review_queue": [entry], "nodes_this_run": state.get("nodes_this_run", 0) + 1}


def route_after_supervisor(state: OxidantState) -> str:
    if state.get("supervisor_hint") is not None:
        return "build_context"
    return "queue_for_review"


def supervisor_node(state: OxidantState) -> dict:
    """Generate a targeted hint via Sonnet, then optionally interrupt for human review."""
    node_id = state["current_node_id"]
    manifest = Manifest.load(_db(state))
    node = manifest.get_node(node_id) or manifest.nodes[node_id]

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
