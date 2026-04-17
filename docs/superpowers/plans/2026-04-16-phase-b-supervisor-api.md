# Phase B Supervisor + FastAPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `supervisor_node` that generates targeted hints at escalation boundaries, wire `interrupt()` for human-in-the-loop review, and expose a FastAPI server (`oxidant serve`) with SSE progress streaming and run controls.

**Architecture:** FastAPI and LangGraph run in the same process (Option A). The graph uses `SqliteSaver` for durable checkpoints. All graph nodes stay synchronous — LangGraph's `astream()` runs them in thread executors so the event loop is never blocked. SSE events are mapped from LangGraph's node-update stream.

**Tech Stack:** LangGraph ≥0.2, langgraph-checkpoint-sqlite, FastAPI ≥0.110, uvicorn, sse-starlette, Typer (existing), pytest-asyncio (existing dev dep), httpx (test client)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `pyproject.toml` | Add fastapi, uvicorn, sse-starlette, langgraph-checkpoint-sqlite, httpx |
| Modify | `oxidant.config.json` | Add `review_mode` field |
| Modify | `src/oxidant/graph/state.py` | Add `supervisor_hint`, `interrupt_payload`, `review_mode` |
| Modify | `src/oxidant/agents/context.py` | Add `supervisor_hint` param to `build_prompt` |
| Modify | `src/oxidant/graph/nodes.py` | Add `supervisor_node`, `route_after_supervisor`; update `route_after_verify`, `build_context` |
| Modify | `src/oxidant/graph/graph.py` | Add supervisor_node; expose `build_graph(checkpointer)`; add `build_checkpointed_graph()` |
| Modify | `src/oxidant/cli.py` | Pass `review_mode` from config into initial state; add `serve` command |
| Create | `src/oxidant/serve/__init__.py` | Empty package marker |
| Create | `src/oxidant/serve/events.py` | SSE event dataclasses and JSON serialization |
| Create | `src/oxidant/serve/run_manager.py` | `RunManager`: manages asyncio Tasks, event queues, run lifecycle |
| Create | `src/oxidant/serve/app.py` | FastAPI app + all REST/SSE endpoints |
| Modify | `tests/test_graph_nodes.py` | Add tests for supervisor_node, updated routing |
| Create | `tests/test_serve_endpoints.py` | FastAPI endpoint integration tests |

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing import test**

```python
# tests/test_serve_endpoints.py  (create this file)
def test_fastapi_importable():
    import fastapi  # noqa: F401
    import sse_starlette  # noqa: F401
    from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: F401
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
uv run pytest tests/test_serve_endpoints.py::test_fastapi_importable -v
```

Expected: `ModuleNotFoundError: No module named 'fastapi'`

- [ ] **Step 3: Add dependencies to pyproject.toml**

In the `[project]` `dependencies` list, add these four entries:

```toml
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "sse-starlette>=1.6",
    "langgraph-checkpoint-sqlite>=0.2",
```

In `[project.optional-dependencies]` `dev` list, add:

```toml
    "httpx>=0.27",
```

- [ ] **Step 4: Install and verify**

```bash
uv sync
uv run pytest tests/test_serve_endpoints.py::test_fastapi_importable -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_serve_endpoints.py
git commit -m "chore: add fastapi, uvicorn, sse-starlette, sqlite checkpointer deps"
```

---

### Task 2: Extend OxidantState + config

**Files:**
- Modify: `src/oxidant/graph/state.py`
- Modify: `oxidant.config.json`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_graph_nodes.py` (after the existing `_base_state` function):

```python
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
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_graph_nodes.py::test_oxidant_state_has_supervisor_fields -v
```

Expected: `TypeError: ... unexpected keyword argument 'supervisor_hint'`

- [ ] **Step 3: Add fields to state.py**

At the bottom of the `OxidantState` class (after `nodes_this_run`), add:

```python
    # ── Supervisor / human-in-the-loop ────────────────────────────────────────
    supervisor_hint: Optional[str]        # hint injected into next build_context call
    interrupt_payload: Optional[dict]     # data surfaced to human reviewer via interrupt()
    review_mode: str                      # "auto" | "interactive" | "supervised"
```

- [ ] **Step 4: Update _base_state helper in test_graph_nodes.py**

The existing `_base_state` helper needs the new fields so it compiles. Replace the `defaults` dict inside `_base_state` with:

```python
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
```

- [ ] **Step 5: Add review_mode to oxidant.config.json**

Add `"review_mode": "auto"` as a top-level key in `oxidant.config.json`:

```json
{
  "source_repo": "corpora/msagljs",
  "target_repo": "corpora/msagl-rs",
  "source_language": "typescript",
  "target_language": "rust",
  "tsconfig": "corpora/msagljs/tsconfig.json",
  "review_mode": "auto",
  ...
}
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_graph_nodes.py -v
```

Expected: all existing tests PASS (the helper change is backward-compatible) + new test PASS

- [ ] **Step 7: Commit**

```bash
git add src/oxidant/graph/state.py oxidant.config.json tests/test_graph_nodes.py
git commit -m "feat: add supervisor_hint, interrupt_payload, review_mode to OxidantState"
```

---

### Task 3: Add supervisor_hint to build_prompt

**Files:**
- Modify: `src/oxidant/agents/context.py`
- Modify: `src/oxidant/graph/nodes.py` (`build_context` only)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_context.py` (or nearest test file for context.py):

```python
def test_build_prompt_includes_supervisor_hint(tmp_path):
    from oxidant.agents.context import build_prompt
    from oxidant.models.manifest import ConversionNode, Manifest, NodeKind, TranslationTier

    node = ConversionNode(
        node_id="foo",
        source_file="foo.ts",
        line_start=1, line_end=3,
        source_text="function foo() {}",
        node_kind=NodeKind.FREE_FUNCTION,
        tier=TranslationTier.HAIKU,
    )
    manifest = Manifest(source_repo="test", generated_at="2026-01-01", nodes={"foo": node})

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config={"crate_inventory": [], "architectural_decisions": {}, "model_tiers": {}},
        target_path=tmp_path,
        snippets_dir=tmp_path,
        workspace=tmp_path,
        supervisor_hint="Use arena allocation instead of Box<dyn Trait>.",
    )
    assert "Supervisor Hint" in prompt
    assert "arena allocation" in prompt
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_context.py::test_build_prompt_includes_supervisor_hint -v
```

Expected: `TypeError: build_prompt() got an unexpected keyword argument 'supervisor_hint'`

- [ ] **Step 3: Update build_prompt signature in context.py**

Change the `build_prompt` function signature from:

```python
def build_prompt(
    node: ConversionNode,
    manifest: Manifest,
    config: dict,
    target_path: Path,
    snippets_dir: Path,
    workspace: Path,
    last_error: str | None = None,
    attempt_count: int = 0,
) -> str:
```

to:

```python
def build_prompt(
    node: ConversionNode,
    manifest: Manifest,
    config: dict,
    target_path: Path,
    snippets_dir: Path,
    workspace: Path,
    last_error: str | None = None,
    attempt_count: int = 0,
    supervisor_hint: str | None = None,
) -> str:
```

- [ ] **Step 4: Add supervisor section to the prompt template and format call**

In `context.py`, find `_PROMPT_TEMPLATE` and add `{supervisor_section}` before the final `Respond with ONLY` line:

```python
_PROMPT_TEMPLATE = """\
...
{deps_section}\
{idiom_section}\
{supervisor_section}\
{retry_section}\
Respond with ONLY the Rust function body. No markdown, no explanation.\
"""
```

At the bottom of `build_prompt`, add the supervisor section builder (before the `return` statement):

```python
    supervisor_section = ""
    if supervisor_hint:
        supervisor_section = (
            f"\n## Supervisor Hint\n"
            f"A supervisor agent has reviewed previous failures and suggests:\n"
            f"{supervisor_hint}\n"
        )

    return _PROMPT_TEMPLATE.format(
        crates=crates,
        arch_decisions=arch_lines,
        node_kind=node.node_kind.value,
        node_id=node.node_id,
        source_text=node.source_text,
        rust_signature=rust_sig,
        deps_section=deps_section,
        idiom_section=idiom_section,
        supervisor_section=supervisor_section,
        retry_section=retry_section,
    )
```

- [ ] **Step 5: Update build_context in nodes.py to pass and clear the hint**

Replace the `build_context` function body:

```python
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
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_context.py -v
```

Expected: all PASS including the new test

- [ ] **Step 7: Commit**

```bash
git add src/oxidant/agents/context.py src/oxidant/graph/nodes.py tests/test_context.py
git commit -m "feat: inject supervisor_hint into build_prompt when present"
```

---

### Task 4: Add supervisor_node + update routing

**Files:**
- Modify: `src/oxidant/graph/nodes.py`

The supervisor node fires when a node has exhausted opus (the path that currently leads to `queue_for_review`). It generates a 2-3 sentence hint via `claude --print` (same auth model as translation), then either returns the hint for an auto-retry or calls `interrupt()` for interactive human review.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_graph_nodes.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_graph_nodes.py -k "supervisor" -v
```

Expected: `ImportError` or `AttributeError` (supervisor_node not yet defined)

- [ ] **Step 3: Update route_after_verify in nodes.py**

Change the final two lines of `route_after_verify`:

```python
    if attempt >= max_attempts:
        if _escalate_tier(tier) is None:
            return "supervisor"   # was: "queue_for_review"
        return "escalate"
    return "retry"
```

- [ ] **Step 4: Add route_after_supervisor and supervisor_node to nodes.py**

Add after `queue_for_review` (at the end of the file):

```python
def route_after_supervisor(state: OxidantState) -> str:
    """If the supervisor provided a hint, retry. If None (human skipped), queue for review."""
    if state.get("supervisor_hint") is not None:
        return "build_context"
    return "queue_for_review"


def supervisor_node(state: OxidantState) -> dict:
    """Generate a targeted hint via Sonnet, then optionally interrupt for human review.

    Fires when a node has exhausted all tiers. Calls claude --print with a focused
    hint-generation prompt (using the same Max subscription auth as translation calls).
    In 'interactive' review_mode, calls interrupt() to pause the graph for human input.
    """
    node_id = state["current_node_id"]
    manifest = Manifest.load(Path(state["manifest_path"]))
    node = manifest.nodes[node_id]

    hint_prompt = (
        f"You are reviewing a failed TypeScript-to-Rust translation.\n\n"
        f"Node: {node_id}\n"
        f"Last error:\n{state.get('last_error', 'unknown')[:500]}\n\n"
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
        hint = ""

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

    return {"supervisor_hint": hint, "interrupt_payload": None}
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_graph_nodes.py -v
```

Expected: all supervisor tests PASS; all existing routing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/graph/nodes.py tests/test_graph_nodes.py
git commit -m "feat: add supervisor_node + route_after_supervisor; re-route opus exhaustion to supervisor"
```

---

### Task 5: Wire supervisor_node into the graph + SqliteSaver

**Files:**
- Modify: `src/oxidant/graph/graph.py`

- [ ] **Step 1: Write a failing test**

Add to `tests/test_graph_nodes.py`:

```python
def test_build_graph_has_supervisor_node():
    from oxidant.graph.graph import build_graph
    g = build_graph()
    assert "supervisor_node" in g.nodes
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_graph_nodes.py::test_build_graph_has_supervisor_node -v
```

Expected: FAIL — supervisor_node not in graph

- [ ] **Step 3: Rewrite graph.py**

Replace the entire file:

```python
"""LangGraph state graph for the Phase B translation loop.

Wires all node functions into a compilable StateGraph. Two compiled graphs are
exposed:
- ``translation_graph``: no checkpointer, for direct CLI use (``oxidant phase-b``)
- ``build_checkpointed_graph(db_path)``: SqliteSaver checkpointer for ``oxidant serve``
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from oxidant.graph.nodes import (
    build_context,
    escalate_node,
    invoke_agent,
    pick_next_node,
    queue_for_review,
    retry_node,
    route_after_supervisor,
    route_after_verify,
    supervisor_node,
    update_manifest,
    verify,
)
from oxidant.graph.state import OxidantState


def _route_pick(state: OxidantState) -> str:
    return "done" if state.get("done") else "continue"


def build_graph(checkpointer=None) -> object:
    """Construct and compile the Phase B LangGraph state graph.

    Args:
        checkpointer: Optional LangGraph checkpointer (e.g. SqliteSaver).
                      Pass None for CLI usage; pass a SqliteSaver for ``oxidant serve``.
    """
    graph: StateGraph = StateGraph(OxidantState)

    graph.add_node("pick_next_node", pick_next_node)
    graph.add_node("build_context", build_context)
    graph.add_node("invoke_agent", invoke_agent)
    graph.add_node("verify", verify)
    graph.add_node("retry_node", retry_node)
    graph.add_node("escalate_node", escalate_node)
    graph.add_node("supervisor_node", supervisor_node)
    graph.add_node("update_manifest", update_manifest)
    graph.add_node("queue_for_review", queue_for_review)

    graph.set_entry_point("pick_next_node")

    graph.add_conditional_edges(
        "pick_next_node",
        _route_pick,
        {"continue": "build_context", "done": END},
    )
    graph.add_edge("build_context", "invoke_agent")
    graph.add_edge("invoke_agent", "verify")
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {
            "update_manifest": "update_manifest",
            "retry": "retry_node",
            "escalate": "escalate_node",
            "supervisor": "supervisor_node",
        },
    )
    graph.add_edge("retry_node", "build_context")
    graph.add_edge("escalate_node", "build_context")
    graph.add_conditional_edges(
        "supervisor_node",
        route_after_supervisor,
        {
            "build_context": "build_context",
            "queue_for_review": "queue_for_review",
        },
    )
    graph.add_edge("update_manifest", "pick_next_node")
    graph.add_edge("queue_for_review", "pick_next_node")

    return graph.compile(checkpointer=checkpointer)


def build_checkpointed_graph(db_path: str) -> object:
    """Build a graph with SqliteSaver for use by ``oxidant serve``.

    Args:
        db_path: Absolute path to the SQLite checkpoint file (created if absent).
    """
    from langgraph.checkpoint.sqlite import SqliteSaver
    checkpointer = SqliteSaver.from_conn_string(db_path)
    return build_graph(checkpointer=checkpointer)


# Compiled graph without checkpointer — used by ``oxidant phase-b`` CLI
translation_graph = build_graph()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_graph_nodes.py -v
uv run pytest tests/ -v --ignore=tests/test_serve_endpoints.py -x
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/oxidant/graph/graph.py tests/test_graph_nodes.py
git commit -m "feat: wire supervisor_node into graph; add build_checkpointed_graph with SqliteSaver"
```

---

### Task 6: Create SSE event schema

**Files:**
- Create: `src/oxidant/serve/__init__.py`
- Create: `src/oxidant/serve/events.py`

- [ ] **Step 1: Create the package marker**

Create `src/oxidant/serve/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_serve_endpoints.py`:

```python
def test_sse_events_serialize_to_json():
    from oxidant.serve.events import NodeStartEvent, NodeCompleteEvent, RunCompleteEvent
    import json

    e = NodeStartEvent(node_id="foo/bar", tier="haiku")
    data = json.loads(e.to_json())
    assert data["event"] == "node_start"
    assert data["node_id"] == "foo/bar"
    assert data["tier"] == "haiku"

    e2 = NodeCompleteEvent(node_id="foo/bar", tier="sonnet", attempts=2)
    data2 = json.loads(e2.to_json())
    assert data2["event"] == "node_complete"
    assert data2["attempts"] == 2

    e3 = RunCompleteEvent(converted=10, needs_review=2)
    data3 = json.loads(e3.to_json())
    assert data3["event"] == "run_complete"
    assert data3["converted"] == 10
```

- [ ] **Step 3: Run to verify it fails**

```bash
uv run pytest tests/test_serve_endpoints.py::test_sse_events_serialize_to_json -v
```

Expected: `ModuleNotFoundError: No module named 'oxidant.serve'`

- [ ] **Step 4: Create src/oxidant/serve/events.py**

```python
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
        # current_node_id is no longer in the update (update_manifest doesn't return it),
        # so we emit a generic status event. The GUI can correlate via node feed.
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
        node_id = update.get("current_node_id", "")  # may not be in update
        hint = update.get("supervisor_hint") or ""
        payload = update.get("interrupt_payload")
        if payload:
            events.append(InterruptEvent(node_id=payload.get("node_id", ""), payload=payload).to_json())
        else:
            events.append(SupervisorEvent(
                node_id=node_id, hint=hint, requires_human=False,
            ).to_json())

    return events
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_serve_endpoints.py::test_sse_events_serialize_to_json -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/serve/__init__.py src/oxidant/serve/events.py tests/test_serve_endpoints.py
git commit -m "feat: add SSE event schema for oxidant serve"
```

---

### Task 7: Create RunManager

**Files:**
- Create: `src/oxidant/serve/run_manager.py`

The RunManager owns the lifecycle of a translation run: starts the `graph.astream()` task, feeds events into a per-run asyncio.Queue, and handles pause (task cancellation with SqliteSaver persistence) and abort.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_serve_endpoints.py`:

```python
import asyncio
import pytest

@pytest.mark.asyncio
async def test_run_manager_lifecycle():
    """RunManager creates a run, can be queried for status, and can be aborted."""
    from oxidant.serve.run_manager import RunManager

    rm = RunManager(db_path=":memory:")  # in-memory SQLite for tests
    assert rm.get_status("nonexistent") is None

    # We can't test a full graph run without real files, but we can test
    # that the RunManager initialises and rejects bad thread IDs cleanly.
    with pytest.raises(KeyError):
        await rm.abort("nonexistent")
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_serve_endpoints.py::test_run_manager_lifecycle -v
```

Expected: `ModuleNotFoundError: No module named 'oxidant.serve.run_manager'`

- [ ] **Step 3: Create src/oxidant/serve/run_manager.py**

```python
"""Manages active Phase B translation runs for the FastAPI serve command.

Each run is identified by a thread_id (str). The RunManager:
- Starts graph.astream() as an asyncio Task
- Feeds LangGraph node-update events into a per-run asyncio.Queue
- Tracks run status
- Handles pause (task cancellation; SqliteSaver persists last node) and abort

Pause vs resume:
  Pause:  POST /pause → cancel the asyncio Task. The SqliteSaver has already
          checkpointed after the last completed node. Resume by calling
          start_run() again with the same thread_id and initial_state — the
          graph will resume from the checkpoint.
  Abort:  POST /abort → cancel the asyncio Task + mark status "aborted".
          No resume.
  Interrupt (interactive review):
          supervisor_node calls LangGraph interrupt(). The Task is suspended
          inside graph.astream() waiting for a Command(resume=...).
          POST /resume sends the Command via graph.astream() continuation.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

RunStatus = Literal["running", "paused", "interrupted", "complete", "aborted", "error"]


@dataclass
class RunState:
    thread_id: str
    status: RunStatus
    event_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None
    final_state: dict | None = None
    error: str | None = None


class RunManager:
    """Manages active Phase B runs."""

    def __init__(self, db_path: str) -> None:
        """
        Args:
            db_path: Path for the SqliteSaver checkpoint DB, or ":memory:" for tests.
        """
        self._db_path = db_path
        self._runs: dict[str, RunState] = {}
        self._graph = None  # lazy-initialised on first run

    def _get_graph(self):
        if self._graph is None:
            from oxidant.graph.graph import build_checkpointed_graph
            self._graph = build_checkpointed_graph(self._db_path)
        return self._graph

    def get_status(self, thread_id: str) -> RunStatus | None:
        run = self._runs.get(thread_id)
        return run.status if run else None

    async def start_run(
        self,
        thread_id: str,
        initial_state: dict[str, Any],
    ) -> None:
        """Start or resume a run. If a checkpoint exists for thread_id, the graph
        resumes from the last checkpoint (initial_state is used only for fresh runs).
        """
        if thread_id in self._runs and self._runs[thread_id].status == "running":
            raise ValueError(f"Run {thread_id} is already running")

        run = RunState(thread_id=thread_id, status="running")
        self._runs[thread_id] = run

        graph = self._get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        async def _stream():
            from oxidant.serve.events import event_from_node_update
            try:
                async for chunk in graph.astream(initial_state, config=config, stream_mode="updates"):
                    for node_name, update in chunk.items():
                        for json_str in event_from_node_update(node_name, update):
                            await run.event_queue.put(json_str)
                run.status = "complete"
                await run.event_queue.put(None)  # sentinel: stream done
            except asyncio.CancelledError:
                # Task cancelled by pause() or abort() — status already set by caller
                await run.event_queue.put(None)
                raise
            except Exception as exc:
                logger.exception("Run %s failed: %s", thread_id, exc)
                run.status = "error"
                run.error = str(exc)
                await run.event_queue.put(None)

        run.task = asyncio.create_task(_stream())

    async def pause(self, thread_id: str) -> None:
        """Cancel the running task. The SqliteSaver has checkpointed the last node.
        Resume by calling start_run() again with the same thread_id.
        """
        run = self._runs.get(thread_id)
        if run is None:
            raise KeyError(f"No run with thread_id={thread_id!r}")
        if run.task and not run.task.done():
            run.status = "paused"
            run.task.cancel()
            try:
                await run.task
            except asyncio.CancelledError:
                pass

    async def abort(self, thread_id: str) -> None:
        """Cancel the running task and mark as aborted (no resume)."""
        run = self._runs.get(thread_id)
        if run is None:
            raise KeyError(f"No run with thread_id={thread_id!r}")
        if run.task and not run.task.done():
            run.status = "aborted"
            run.task.cancel()
            try:
                await run.task
            except asyncio.CancelledError:
                pass

    async def resume_interrupt(
        self,
        thread_id: str,
        human_response: dict[str, Any],
    ) -> None:
        """Resume a graph that is paused at an interrupt() call.

        Sends a LangGraph Command(resume=human_response) to the graph.
        The graph resumes from the interrupt point and continues streaming.
        """
        from langgraph.types import Command

        run = self._runs.get(thread_id)
        if run is None:
            raise KeyError(f"No run with thread_id={thread_id!r}")

        graph = self._get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        # Re-start streaming with the Command — LangGraph resumes from the interrupt
        run.status = "running"
        async def _resume_stream():
            from oxidant.serve.events import event_from_node_update
            try:
                async for chunk in graph.astream(
                    Command(resume=human_response), config=config, stream_mode="updates"
                ):
                    for node_name, update in chunk.items():
                        for json_str in event_from_node_update(node_name, update):
                            await run.event_queue.put(json_str)
                run.status = "complete"
                await run.event_queue.put(None)
            except asyncio.CancelledError:
                await run.event_queue.put(None)
                raise
            except Exception as exc:
                logger.exception("Resumed run %s failed: %s", thread_id, exc)
                run.status = "error"
                run.error = str(exc)
                await run.event_queue.put(None)

        run.task = asyncio.create_task(_resume_stream())

    def get_event_queue(self, thread_id: str) -> asyncio.Queue:
        run = self._runs.get(thread_id)
        if run is None:
            raise KeyError(f"No run with thread_id={thread_id!r}")
        return run.event_queue
```

- [ ] **Step 4: Configure pytest-asyncio**

Check if `pyproject.toml` has `[tool.pytest.ini_options]`. If not, add:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_serve_endpoints.py::test_run_manager_lifecycle -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/serve/run_manager.py pyproject.toml tests/test_serve_endpoints.py
git commit -m "feat: add RunManager for serve run lifecycle (start/pause/abort/resume)"
```

---

### Task 8: Create FastAPI app

**Files:**
- Create: `src/oxidant/serve/app.py`

- [ ] **Step 1: Write failing endpoint tests**

Add to `tests/test_serve_endpoints.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.fixture
def app_with_tmp(tmp_path):
    """Create a FastAPI app with temp paths (no real manifest needed for route tests)."""
    from oxidant.serve.app import create_app
    return create_app(
        db_path=str(tmp_path / "checkpoints.db"),
        gui_dist=None,  # no GUI in tests
    )

@pytest.mark.asyncio
async def test_status_404_for_unknown_thread(app_with_tmp):
    async with AsyncClient(transport=ASGITransport(app=app_with_tmp), base_url="http://test") as client:
        r = await client.get("/status/nonexistent-thread")
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_review_queue_empty_initially(app_with_tmp):
    async with AsyncClient(transport=ASGITransport(app=app_with_tmp), base_url="http://test") as client:
        r = await client.get("/review-queue")
    assert r.status_code == 200
    assert r.json() == []

@pytest.mark.asyncio
async def test_resume_404_for_unknown_thread(app_with_tmp):
    async with AsyncClient(transport=ASGITransport(app=app_with_tmp), base_url="http://test") as client:
        r = await client.post("/resume/nonexistent", json={"hint": "try harder"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_serve_endpoints.py -k "test_status_404 or test_review_queue or test_resume_404" -v
```

Expected: `ModuleNotFoundError: No module named 'oxidant.serve.app'`

- [ ] **Step 3: Create src/oxidant/serve/app.py**

```python
"""FastAPI application for oxidant serve.

Endpoints:
  POST /run                   Start or resume a Phase B run
  GET  /stream/{thread_id}    SSE stream of progress events
  POST /pause/{thread_id}     Pause after current node (cancels task; resumable)
  POST /abort/{thread_id}     Abort run (cancels task; not resumable)
  POST /resume/{thread_id}    Resume a supervisor interrupt() pause
  GET  /review-queue          Nodes awaiting human review
  GET  /status/{thread_id}    Run status snapshot
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from oxidant.serve.run_manager import RunManager

logger = logging.getLogger(__name__)

_review_queue: list[dict] = []  # accumulated across all runs in this process


class StartRunRequest(BaseModel):
    manifest_path: str
    target_path: str
    snippets_dir: str = "snippets"
    review_mode: str = "auto"
    max_nodes: int | None = None
    thread_id: str | None = None  # None → generate new UUID


class ResumeRequest(BaseModel):
    hint: str = ""
    skip: bool = False


def create_app(db_path: str, gui_dist: str | None = None) -> FastAPI:
    """Factory that creates a configured FastAPI app.

    Args:
        db_path: Path to the SqliteSaver checkpoint DB file.
        gui_dist: Path to the built Vue 3 GUI dist/ directory, or None to skip.
    """
    app = FastAPI(title="Oxidant Serve", version="0.1.0")
    run_manager = RunManager(db_path=db_path)

    @app.post("/run")
    async def start_run(req: StartRunRequest) -> JSONResponse:
        """Start or resume a Phase B run. Returns the thread_id."""
        import json as _json

        thread_id = req.thread_id or str(uuid.uuid4())
        config_path = Path(req.manifest_path).parent / "oxidant.config.json"
        cfg: dict[str, Any] = {}
        if config_path.exists():
            cfg = _json.loads(config_path.read_text())

        # review_mode from request overrides config
        cfg["review_mode"] = req.review_mode

        snippets = Path(req.snippets_dir)
        snippets.mkdir(parents=True, exist_ok=True)

        from oxidant.graph.state import OxidantState
        initial_state = OxidantState(
            manifest_path=str(Path(req.manifest_path).resolve()),
            target_path=str(Path(req.target_path).resolve()),
            snippets_dir=str(snippets.resolve()),
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
            max_nodes=req.max_nodes,
            nodes_this_run=0,
            supervisor_hint=None,
            interrupt_payload=None,
            review_mode=req.review_mode,
        )

        await run_manager.start_run(thread_id=thread_id, initial_state=initial_state)
        return JSONResponse({"thread_id": thread_id, "status": "running"})

    @app.get("/stream/{thread_id}")
    async def stream_events(thread_id: str):
        """SSE stream of progress events for a run. Closes when the run completes."""
        if run_manager.get_status(thread_id) is None:
            raise HTTPException(status_code=404, detail=f"No run: {thread_id}")

        queue = run_manager.get_event_queue(thread_id)

        async def event_generator():
            while True:
                item = await queue.get()
                if item is None:  # sentinel: stream is done
                    break
                yield {"data": item}

        return EventSourceResponse(event_generator())

    @app.post("/pause/{thread_id}")
    async def pause_run(thread_id: str) -> JSONResponse:
        """Pause a run after its current node. Resume by calling POST /run with the same thread_id."""
        try:
            await run_manager.pause(thread_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"No run: {thread_id}")
        return JSONResponse({"thread_id": thread_id, "status": "paused"})

    @app.post("/abort/{thread_id}")
    async def abort_run(thread_id: str) -> JSONResponse:
        """Abort a run. Not resumable."""
        try:
            await run_manager.abort(thread_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"No run: {thread_id}")
        return JSONResponse({"thread_id": thread_id, "status": "aborted"})

    @app.post("/resume/{thread_id}")
    async def resume_interrupt(thread_id: str, req: ResumeRequest) -> JSONResponse:
        """Resume a graph paused at a supervisor interrupt().

        Body: {"hint": "...", "skip": false}
        - hint: human-provided translation hint (overrides supervisor hint)
        - skip: if true, skip this node and queue for human review
        """
        if run_manager.get_status(thread_id) is None:
            raise HTTPException(status_code=404, detail=f"No run: {thread_id}")
        try:
            await run_manager.resume_interrupt(
                thread_id=thread_id,
                human_response={"hint": req.hint, "skip": req.skip},
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return JSONResponse({"thread_id": thread_id, "status": "running"})

    @app.get("/review-queue")
    async def get_review_queue() -> JSONResponse:
        """Return nodes that have been queued for human review across all runs."""
        return JSONResponse(_review_queue)

    @app.get("/status/{thread_id}")
    async def get_status(thread_id: str) -> JSONResponse:
        status = run_manager.get_status(thread_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"No run: {thread_id}")
        return JSONResponse({"thread_id": thread_id, "status": status})

    # Serve built Vue GUI at / (must be mounted last so API routes take priority)
    if gui_dist and Path(gui_dist).exists():
        app.mount("/", StaticFiles(directory=gui_dist, html=True), name="gui")

    return app


# Module-level app instance for ``uvicorn oxidant.serve.app:app``
# Uses default paths; the serve CLI command calls create_app() directly.
app = create_app(db_path="oxidant_checkpoints.db")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_serve_endpoints.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/oxidant/serve/app.py tests/test_serve_endpoints.py
git commit -m "feat: add FastAPI serve app with SSE stream, pause/abort/resume endpoints"
```

---

### Task 9: Add serve command to CLI

**Files:**
- Modify: `src/oxidant/cli.py`
- Modify: `src/oxidant/graph/nodes.py` (pass review_mode from config in phase_b)

- [ ] **Step 1: Update phase_b in cli.py to pass review_mode**

In the `phase_b` command, find the `initial_state = OxidantState(...)` block and add the three new fields:

```python
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
        max_nodes=max_nodes,
        nodes_this_run=0,
        supervisor_hint=None,
        interrupt_payload=None,
        review_mode=cfg.get("review_mode", "auto"),
    )
```

- [ ] **Step 2: Add serve command to cli.py**

Add before the `translate` command:

```python
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

    application = create_app(db_path=db_path, gui_dist=gui_dist)
    uvicorn.run(application, host=host, port=port, reload=reload)
```

- [ ] **Step 3: Verify the serve command shows in help**

```bash
uv run oxidant --help
```

Expected output includes `serve` in the command list.

```bash
uv run oxidant serve --help
```

Expected: shows `--host`, `--port`, `--db`, `--gui-dist` options.

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest tests/ -v -x
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/oxidant/cli.py tests/
git commit -m "feat: add 'oxidant serve' command; pass review_mode from config into phase-b state"
```

---

### Task 10: Smoke test serve manually

This task has no automated test — it requires a real manifest. Run it once to verify the server starts and the SSE endpoint responds.

- [ ] **Step 1: Start the server**

```bash
uv run oxidant serve --port 8000
```

Expected output: `Starting oxidant serve on http://127.0.0.1:8000`

- [ ] **Step 2: Verify API docs load**

Open `http://127.0.0.1:8000/docs` in a browser. Expected: FastAPI Swagger UI with all endpoints listed.

- [ ] **Step 3: Verify /review-queue responds**

```bash
curl http://127.0.0.1:8000/review-queue
```

Expected: `[]`

- [ ] **Step 4: Verify /status/nonexistent returns 404**

```bash
curl -w "\nHTTP %{http_code}\n" http://127.0.0.1:8000/status/nonexistent
```

Expected: `HTTP 404`

- [ ] **Step 5: Stop server (Ctrl-C) and commit**

```bash
git add .  # nothing to add, just confirming state
git commit --allow-empty -m "test: manual smoke test of oxidant serve passed"
```

---

## What's not in this plan (deferred to Plan 2)

- Vue 3 GUI (`gui/` directory, Vite, Pinia, components)
- `gui/dist/` static build wired into `oxidant serve --gui-dist`

Those are covered in `2026-04-16-gui-vue3-dashboard.md`.
