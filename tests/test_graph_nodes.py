import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from oxidant.graph.state import OxidantState
from oxidant.models.manifest import (
    ConversionNode, Manifest, NodeKind, NodeStatus, TranslationTier,
)


def _make_node(node_id: str, kind=NodeKind.FREE_FUNCTION, **kw) -> ConversionNode:
    return ConversionNode(
        node_id=node_id, source_file="m.ts", line_start=1, line_end=5,
        source_text="function foo() { return 1; }",
        node_kind=kind, tier=TranslationTier.HAIKU, **kw,
    )


def _write_manifest(path: Path, nodes: dict) -> Manifest:
    m = Manifest(source_repo="test", generated_at="2026-04-15", nodes=nodes)
    m.save(path)
    return m


def test_oxidant_state_has_supervisor_fields():
    """OxidantState must contain the three new supervisor/serve fields."""
    state = OxidantState(
        manifest_path="/tmp/m.json",
        target_path="/tmp/t",
        snippets_dir="/tmp/s",
        config={},
        current_node_id=None,
        current_prompt=None,
        current_snippet=None,
        current_tier=None,
        attempt_count=0,
        last_error=None,
        verify_status=None,
        review_queue=[],
        done=False,
        # New fields:
        supervisor_hint=None,
        interrupt_payload=None,
        review_mode="auto",
    )
    assert state["review_mode"] == "auto"
    assert state["supervisor_hint"] is None
    assert state["interrupt_payload"] is None


def _base_state(manifest_path: str, target_path: str = "/nonexistent", **kw) -> OxidantState:
    defaults: dict = {
        "manifest_path": manifest_path,
        "target_path": target_path,
        "snippets_dir": "/tmp/snippets",
        "config": {"crate_inventory": [], "architectural_decisions": {}, "model_tiers": {}},
        "current_node_id": None,
        "current_prompt": None,
        "current_snippet": None,
        "current_tier": None,
        "attempt_count": 0,
        "last_error": None,
        "verify_status": None,
        "review_queue": [],
        "done": False,
        "supervisor_hint": None,
        "interrupt_payload": None,
        "review_mode": "auto",
    }
    defaults.update(kw)
    return OxidantState(**defaults)


# ── pick_next_node ────────────────────────────────────────────────────────────

def test_pick_next_node_selects_eligible(tmp_path):
    from oxidant.graph.nodes import pick_next_node
    path = tmp_path / "manifest.json"
    _write_manifest(path, {"m__foo": _make_node("m__foo")})
    state = _base_state(str(path))
    update = pick_next_node(state)
    assert update["current_node_id"] == "m__foo"
    assert update["done"] is False


def test_pick_next_node_signals_done_when_all_converted(tmp_path):
    from oxidant.graph.nodes import pick_next_node
    path = tmp_path / "manifest.json"
    _write_manifest(path, {
        "m__foo": _make_node("m__foo", status=NodeStatus.CONVERTED)
    })
    state = _base_state(str(path))
    update = pick_next_node(state)
    assert update["done"] is True
    assert update["current_node_id"] is None


def test_pick_next_node_prefers_lower_topological_order(tmp_path):
    from oxidant.graph.nodes import pick_next_node
    path = tmp_path / "manifest.json"
    _write_manifest(path, {
        "m__b": _make_node("m__b", topological_order=5),
        "m__a": _make_node("m__a", topological_order=1),
    })
    state = _base_state(str(path))
    update = pick_next_node(state)
    assert update["current_node_id"] == "m__a"


# ── retry_node and escalate_node ─────────────────────────────────────────────

def test_retry_node_increments_attempt_count():
    from oxidant.graph.nodes import retry_node
    state = _base_state("/dev/null", attempt_count=2)
    update = retry_node(state)
    assert update["attempt_count"] == 3


def test_escalate_node_haiku_to_sonnet():
    from oxidant.graph.nodes import escalate_node
    state = _base_state("/dev/null", current_tier="haiku", attempt_count=3)
    update = escalate_node(state)
    assert update["current_tier"] == "sonnet"
    assert update["attempt_count"] == 0


def test_escalate_node_sonnet_to_opus():
    from oxidant.graph.nodes import escalate_node
    state = _base_state("/dev/null", current_tier="sonnet", attempt_count=4)
    update = escalate_node(state)
    assert update["current_tier"] == "opus"
    assert update["attempt_count"] == 0


# ── route_after_verify ────────────────────────────────────────────────────────

def test_route_pass():
    from oxidant.graph.nodes import route_after_verify
    state = _base_state("/dev/null", verify_status="PASS", attempt_count=0, current_tier="haiku")
    assert route_after_verify(state) == "update_manifest"


def test_route_retry_within_limit():
    from oxidant.graph.nodes import route_after_verify
    state = _base_state("/dev/null", verify_status="STUB", attempt_count=1, current_tier="haiku")
    assert route_after_verify(state) == "retry"


def test_route_escalate_after_haiku_limit():
    from oxidant.graph.nodes import route_after_verify
    # attempt_count=3 means 4th attempt, haiku limit=3
    state = _base_state("/dev/null", verify_status="STUB", attempt_count=3, current_tier="haiku")
    assert route_after_verify(state) == "escalate"


def test_route_human_review_after_opus_limit():
    from oxidant.graph.nodes import route_after_verify
    state = _base_state("/dev/null", verify_status="CARGO", attempt_count=5, current_tier="opus")
    assert route_after_verify(state) == "supervisor"


# ── queue_for_review ──────────────────────────────────────────────────────────

def test_route_after_verify_routes_to_supervisor_at_opus_exhaustion(tmp_path):
    """When opus attempts are exhausted, route to supervisor (not queue_for_review)."""
    from oxidant.graph.nodes import route_after_verify
    from oxidant.verification.verify import VerifyStatus

    state = _base_state(str(tmp_path / "m.json"))
    state["current_tier"] = "opus"
    state["attempt_count"] = 4  # _MAX_ATTEMPTS["opus"] = 5; attempt+1 >= 5
    state["verify_status"] = VerifyStatus.CARGO.value

    result = route_after_verify(state)
    assert result == "supervisor"


def test_route_after_supervisor_to_build_context_when_hint_present(tmp_path):
    from oxidant.graph.nodes import route_after_supervisor

    state = _base_state(str(tmp_path / "m.json"))
    state["supervisor_hint"] = "Use arena allocation."
    assert route_after_supervisor(state) == "build_context"


def test_route_after_supervisor_to_queue_when_hint_none(tmp_path):
    from oxidant.graph.nodes import route_after_supervisor

    state = _base_state(str(tmp_path / "m.json"))
    state["supervisor_hint"] = None
    assert route_after_supervisor(state) == "queue_for_review"


def test_supervisor_node_returns_hint(tmp_path):
    """supervisor_node calls invoke_claude and returns supervisor_hint."""
    from oxidant.graph.nodes import supervisor_node
    from oxidant.models.manifest import ConversionNode, Manifest, NodeKind, TranslationTier
    from unittest.mock import patch

    node = ConversionNode(
        node_id="n1", source_file="f.ts", line_start=1, line_end=3,
        source_text="class Foo {}", node_kind=NodeKind.CLASS, tier=TranslationTier.OPUS,
    )
    manifest = Manifest(source_repo="t", generated_at="2026-01-01", nodes={"n1": node})
    (tmp_path / "m.json").write_text(manifest.model_dump_json(indent=2))

    state = _base_state(str(tmp_path / "m.json"), target_path=str(tmp_path))
    state["current_node_id"] = "n1"
    state["last_error"] = "type mismatch: expected &Node, got NodeId"
    state["review_mode"] = "auto"

    with patch("oxidant.graph.nodes.invoke_claude", return_value="Use NodeId instead of &Node."):
        result = supervisor_node(state)

    assert result["supervisor_hint"] == "Use NodeId instead of &Node."
    assert result["interrupt_payload"] is None


# ── queue_for_review ──────────────────────────────────────────────────────────

def test_queue_for_review_returns_only_new_entry(tmp_path):
    from oxidant.graph.nodes import queue_for_review
    path = tmp_path / "manifest.json"
    _write_manifest(path, {"m__foo": _make_node("m__foo", status=NodeStatus.IN_PROGRESS)})
    state = _base_state(
        str(path),
        current_node_id="m__foo",
        current_tier="opus",
        attempt_count=5,
        last_error="type mismatch",
        review_queue=[],
    )
    update = queue_for_review(state)
    # Must return ONLY the new entry list — not the full accumulated queue
    assert isinstance(update["review_queue"], list)
    assert len(update["review_queue"]) == 1
    assert update["review_queue"][0]["node_id"] == "m__foo"
