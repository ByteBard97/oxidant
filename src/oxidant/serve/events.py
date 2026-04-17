"""SSE event dataclasses for the oxidant serve endpoint.

Every event has a string ``event`` discriminant and a ``to_json()`` method
that returns a compact JSON string suitable for an SSE ``data:`` line.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class NodeStartEvent:
    node_id: str
    tier: str
    event: str = field(default="node_start", init=False)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class NodeCompleteEvent:
    node_id: str
    tier: str
    attempts: int
    event: str = field(default="node_complete", init=False)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class NodeEscalateEvent:
    node_id: str
    from_tier: str
    to_tier: str
    event: str = field(default="node_escalate", init=False)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class SupervisorEvent:
    node_id: str
    hint: str
    requires_human: bool
    event: str = field(default="supervisor", init=False)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class InterruptEvent:
    node_id: str
    payload: dict[str, Any]
    event: str = field(default="interrupt", init=False)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class RunCompleteEvent:
    converted: int
    needs_review: int
    event: str = field(default="run_complete", init=False)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class ErrorEvent:
    node_id: str
    message: str
    event: str = field(default="error", init=False)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class StatusEvent:
    status: str
    message: str = ""
    event: str = field(default="status", init=False)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def event_from_node_update(node_name: str, update: dict) -> list[str]:
    """Convert a LangGraph node-update dict to a list of SSE data strings.

    LangGraph astream(stream_mode='updates') yields {node_name: state_updates}.
    We map known node names to structured events; unknown nodes are skipped.

    Returns a list of JSON strings (one per event) to emit as SSE data lines.
    """
    events: list[str] = []

    if node_name == "pick_next_node":
        node_id = update.get("current_node_id")
        tier = update.get("current_tier", "unknown")
        if node_id:
            events.append(NodeStartEvent(node_id=node_id, tier=tier).to_json())

    elif node_name == "update_manifest":
        events.append(StatusEvent(status="node_converted").to_json())

    elif node_name == "escalate_node":
        pass  # enriched by next pick_next_node event

    elif node_name == "queue_for_review":
        entries = update.get("review_queue", [])
        for entry in entries:
            events.append(ErrorEvent(
                node_id=entry.get("node_id", "unknown"),
                message=entry.get("last_error", "exhausted all retries"),
            ).to_json())

    elif node_name == "supervisor_node":
        node_id = update.get("current_node_id", "")
        hint = update.get("supervisor_hint") or ""
        payload = update.get("interrupt_payload")
        if payload:
            events.append(InterruptEvent(node_id=payload.get("node_id", ""), payload=payload).to_json())
        else:
            events.append(SupervisorEvent(
                node_id=node_id, hint=hint, requires_human=False,
            ).to_json())

    return events
