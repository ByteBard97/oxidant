# Phase B — Translation Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LangGraph-based agentic translation loop that iterates over `conversion_manifest.json` in topological order, invokes Claude Code as a subprocess per node, verifies each Rust snippet, and updates the manifest until all translatable nodes are `CONVERTED` or sent to a human-review queue.

**Architecture:** A `StateGraph(OxidantState)` with eight nodes: `pick_next_node → build_context → invoke_agent → verify`, then conditional routing to `update_manifest` (PASS) or `retry_node`/`escalate_node`/`queue_for_review` (failures). Structural nodes (CLASS, INTERFACE, ENUM, TYPE_ALIAS) are auto-converted before the loop starts. Snippets are raw Rust function bodies stored in `snippets/<module>/<node_id>.rs`. The `cargo check` verification step injects the snippet into the skeleton, checks, then restores the stub — keeping the skeleton always compilable.

**Tech Stack:** Python 3.11, LangGraph ≥0.2 (already in pyproject.toml), Pydantic v2, `claude --print --output-format json` subprocess (ANTHROPIC_API_KEY stripped), `cargo check --message-format=short`.

**Working directory for all commands:** `.worktrees/feat-phase-b/`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/oxidant/models/manifest.py` | Fix `eligible_nodes` (ignore external deps); add `auto_convert_structural_nodes` |
| Create | `src/oxidant/graph/state.py` | `OxidantState` TypedDict for LangGraph |
| Create | `src/oxidant/agents/invoke.py` | `invoke_claude` subprocess wrapper (strips API key) |
| Create | `src/oxidant/agents/context.py` | `build_prompt` — assembles the conversion prompt |
| Create | `src/oxidant/verification/__init__.py` | empty |
| Create | `src/oxidant/verification/verify.py` | `verify_snippet` → `VerifyResult` (stub / branch / cargo checks) |
| Create | `src/oxidant/graph/nodes.py` | All eight LangGraph node functions + routing function |
| Create | `src/oxidant/graph/graph.py` | Graph wiring + `build_graph()` + module-level `translation_graph` |
| Create | `src/oxidant/assembly/__init__.py` | empty |
| Create | `src/oxidant/assembly/assemble.py` | `assemble_module` + `check_and_assemble` |
| Modify | `src/oxidant/cli.py` | Add `phase-b` command |
| Create | `tests/test_manifest_phase_b.py` | Tests for eligible_nodes fix and auto_convert |
| Create | `tests/test_invoke.py` | Tests for Claude subprocess wrapper |
| Create | `tests/test_context.py` | Tests for prompt assembly |
| Create | `tests/test_verify.py` | Tests for verification checks |
| Create | `tests/test_graph_nodes.py` | Tests for LangGraph node functions |
| Create | `tests/test_assemble.py` | Tests for module assembly |

---

### Task 1: Fix `eligible_nodes` and add `auto_convert_structural_nodes`

**Background:** The current `eligible_nodes()` method checks `dep in converted` for all deps. If a dep is not in `manifest.nodes` (e.g., it was from an unexported file not extracted by Phase A), `dep in converted` is always `False`, permanently blocking the node. Fix: only check deps that are actually in the manifest. Also: CLASS/INTERFACE/ENUM/TYPE_ALIAS nodes have no function body — the skeleton already handles them. Mark them CONVERTED before Phase B starts.

**Files:**
- Modify: `src/oxidant/models/manifest.py`
- Create: `tests/test_manifest_phase_b.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_manifest_phase_b.py`:

```python
import pytest
from pathlib import Path
from oxidant.models.manifest import (
    ConversionNode, Manifest, NodeKind, NodeStatus, TranslationTier
)


def _make_node(node_id: str, kind: NodeKind, **kwargs) -> ConversionNode:
    return ConversionNode(
        node_id=node_id,
        source_file="m.ts",
        line_start=1,
        line_end=10,
        source_text="function foo() {}",
        node_kind=kind,
        tier=TranslationTier.HAIKU,
        **kwargs,
    )


def test_eligible_nodes_ignores_external_deps():
    """A node whose only dep is outside the manifest should still be eligible."""
    manifest = Manifest(
        source_repo="test",
        generated_at="2026-04-15",
        nodes={
            "m__foo": _make_node(
                "m__foo",
                NodeKind.FREE_FUNCTION,
                call_dependencies=["external__missing"],  # not in manifest
            )
        },
    )
    eligible = manifest.eligible_nodes()
    assert len(eligible) == 1
    assert eligible[0].node_id == "m__foo"


def test_eligible_nodes_blocks_on_known_unconverted_dep():
    """A node blocked on a manifest dep that is NOT_STARTED stays ineligible."""
    manifest = Manifest(
        source_repo="test",
        generated_at="2026-04-15",
        nodes={
            "m__A": _make_node("m__A", NodeKind.FREE_FUNCTION),
            "m__B": _make_node(
                "m__B",
                NodeKind.FREE_FUNCTION,
                call_dependencies=["m__A"],
            ),
        },
    )
    eligible_ids = {n.node_id for n in manifest.eligible_nodes()}
    assert "m__A" in eligible_ids
    assert "m__B" not in eligible_ids


def test_eligible_nodes_unblocked_after_dep_converted():
    """After m__A is CONVERTED, m__B becomes eligible."""
    manifest = Manifest(
        source_repo="test",
        generated_at="2026-04-15",
        nodes={
            "m__A": _make_node("m__A", NodeKind.FREE_FUNCTION, status=NodeStatus.CONVERTED),
            "m__B": _make_node(
                "m__B",
                NodeKind.FREE_FUNCTION,
                call_dependencies=["m__A"],
            ),
        },
    )
    eligible_ids = {n.node_id for n in manifest.eligible_nodes()}
    assert "m__B" in eligible_ids


def test_auto_convert_structural_nodes(tmp_path):
    """CLASS, INTERFACE, ENUM, TYPE_ALIAS → CONVERTED. FREE_FUNCTION stays NOT_STARTED."""
    manifest = Manifest(
        source_repo="test",
        generated_at="2026-04-15",
        nodes={
            "m__MyClass": _make_node("m__MyClass", NodeKind.CLASS),
            "m__IShape": _make_node("m__IShape", NodeKind.INTERFACE),
            "m__Color": _make_node("m__Color", NodeKind.ENUM),
            "m__Alias": _make_node("m__Alias", NodeKind.TYPE_ALIAS),
            "m__distance": _make_node("m__distance", NodeKind.FREE_FUNCTION),
        },
    )
    path = tmp_path / "manifest.json"
    manifest.save(path)

    count = manifest.auto_convert_structural_nodes(path)

    assert count == 4
    reloaded = Manifest.load(path)
    assert reloaded.nodes["m__MyClass"].status == NodeStatus.CONVERTED
    assert reloaded.nodes["m__IShape"].status == NodeStatus.CONVERTED
    assert reloaded.nodes["m__Color"].status == NodeStatus.CONVERTED
    assert reloaded.nodes["m__Alias"].status == NodeStatus.CONVERTED
    assert reloaded.nodes["m__distance"].status == NodeStatus.NOT_STARTED


def test_auto_convert_skips_already_converted(tmp_path):
    """Nodes already CONVERTED are not double-counted."""
    manifest = Manifest(
        source_repo="test",
        generated_at="2026-04-15",
        nodes={
            "m__MyClass": _make_node("m__MyClass", NodeKind.CLASS, status=NodeStatus.CONVERTED),
            "m__IShape": _make_node("m__IShape", NodeKind.INTERFACE),
        },
    )
    path = tmp_path / "manifest.json"
    manifest.save(path)
    count = manifest.auto_convert_structural_nodes(path)
    assert count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_manifest_phase_b.py -v 2>&1 | tail -20
```

Expected: `test_eligible_nodes_ignores_external_deps` FAILS (returns empty list), `test_auto_convert_structural_nodes` FAILS (AttributeError).

- [ ] **Step 3: Fix `eligible_nodes` and add `auto_convert_structural_nodes` in `manifest.py`**

In `src/oxidant/models/manifest.py`, replace the `eligible_nodes` method and add the new one. The full additions to the `Manifest` class (add after the existing `eligible_nodes` method):

Replace existing `eligible_nodes`:
```python
def eligible_nodes(self) -> list[ConversionNode]:
    """NOT_STARTED nodes whose every in-manifest dependency is CONVERTED.

    Dependencies that reference node IDs outside this manifest are ignored —
    they represent unexported or cross-repo code that Phase A did not extract.
    """
    manifest_ids = set(self.nodes.keys())
    converted = {
        nid for nid, node in self.nodes.items()
        if node.status == NodeStatus.CONVERTED
    }
    return [
        node for node in self.nodes.values()
        if node.status == NodeStatus.NOT_STARTED
        and all(
            dep in converted
            for dep in node.type_dependencies
            if dep in manifest_ids
        )
        and all(
            dep in converted
            for dep in node.call_dependencies
            if dep in manifest_ids
        )
    ]
```

Add after `eligible_nodes`:
```python
_STRUCTURAL_KINDS: frozenset[NodeKind] = frozenset({
    NodeKind.CLASS, NodeKind.INTERFACE, NodeKind.ENUM, NodeKind.TYPE_ALIAS,
})


def auto_convert_structural_nodes(self, path: Path) -> int:
    """Mark all structural nodes (no function body to translate) as CONVERTED.

    CLASS, INTERFACE, ENUM, and TYPE_ALIAS nodes are fully represented by the
    skeleton — they require no agent invocation. Returns the count converted.
    """
    count = 0
    for node_id, node in self.nodes.items():
        if node.node_kind in _STRUCTURAL_KINDS and node.status == NodeStatus.NOT_STARTED:
            self.nodes[node_id] = node.model_copy(
                update={"status": NodeStatus.CONVERTED}
            )
            count += 1
    if count:
        self.save(path)
    return count
```

Note: `_STRUCTURAL_KINDS` is a module-level constant — place it just before the `Manifest` class, not inside it.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_manifest_phase_b.py -v 2>&1 | tail -15
```

Expected: 5 passed.

- [ ] **Step 5: Run full suite to verify no regressions**

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: 42 passed (37 existing + 5 new).

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/models/manifest.py tests/test_manifest_phase_b.py
git commit -m "feat: fix eligible_nodes for external deps, add auto_convert_structural_nodes"
```

---

### Task 2: OxidantState TypedDict

**Background:** LangGraph requires a `TypedDict` as the state schema. Fields updated by a node replace the old value unless annotated with a reducer. `review_queue` uses `operator.add` so each node returns only the _new_ entries it's adding — the graph accumulates them. All other fields are plain replacement.

**Files:**
- Create: `src/oxidant/graph/state.py`

No test file needed — the state type is structural and exercised by the node tests in Task 6.

- [ ] **Step 1: Create `src/oxidant/graph/state.py`**

```python
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
```

- [ ] **Step 2: Verify the file imports cleanly**

```bash
.venv/bin/python -c "from oxidant.graph.state import OxidantState; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/oxidant/graph/state.py
git commit -m "feat: add OxidantState TypedDict for LangGraph phase-b loop"
```

---

### Task 3: Claude Code subprocess invocation

**Background:** Claude Code must be invoked via `claude --print --output-format json`. `ANTHROPIC_API_KEY` MUST be stripped from the environment before calling — if it is present, Claude Code bills to the API account rather than the user's Max subscription, which has caused accidental charges of $1,800+ for other users. The JSON response has the shape `{"result": "...", "cost_usd": ..., ...}` — we extract `result`.

**Files:**
- Create: `src/oxidant/agents/invoke.py`
- Create: `tests/test_invoke.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_invoke.py`:

```python
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from oxidant.agents.invoke import invoke_claude


def _fake_run(returncode: int, stdout: str, stderr: str = ""):
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


def test_strips_api_key(monkeypatch, tmp_path):
    """ANTHROPIC_API_KEY must be absent from the subprocess environment."""
    captured_env: dict = {}

    def fake_run(cmd, *, env, **kwargs):
        captured_env.update(env)
        return _fake_run(0, '{"result": "fn foo() { 42 }"}')

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    with patch("oxidant.agents.invoke.subprocess.run", side_effect=fake_run):
        result = invoke_claude("convert this", cwd=str(tmp_path))

    assert "ANTHROPIC_API_KEY" not in captured_env
    assert result == "fn foo() { 42 }"


def test_returns_result_field(tmp_path):
    """Extracts the 'result' field from the JSON response."""
    response_json = '{"result": "let x = 1;", "cost_usd": 0.001, "is_error": false}'
    with patch("oxidant.agents.invoke.subprocess.run",
               return_value=_fake_run(0, response_json)):
        result = invoke_claude("prompt", cwd=str(tmp_path))
    assert result == "let x = 1;"


def test_raises_on_nonzero_exit(tmp_path):
    """RuntimeError raised when claude exits non-zero."""
    with patch("oxidant.agents.invoke.subprocess.run",
               return_value=_fake_run(1, "", "error message")):
        with pytest.raises(RuntimeError, match="exited 1"):
            invoke_claude("prompt", cwd=str(tmp_path))


def test_raises_on_non_json_output(tmp_path):
    """RuntimeError raised when output is not valid JSON."""
    with patch("oxidant.agents.invoke.subprocess.run",
               return_value=_fake_run(0, "not json")):
        with pytest.raises(RuntimeError, match="non-JSON"):
            invoke_claude("prompt", cwd=str(tmp_path))


def test_raises_on_missing_result_key(tmp_path):
    """RuntimeError raised when JSON is valid but missing 'result'."""
    with patch("oxidant.agents.invoke.subprocess.run",
               return_value=_fake_run(0, '{"other_key": "value"}')):
        with pytest.raises(RuntimeError, match="missing 'result'"):
            invoke_claude("prompt", cwd=str(tmp_path))


def test_tier_haiku_uses_shorter_timeout(tmp_path):
    """Haiku tier gets a shorter timeout than opus."""
    call_kwargs: dict = {}

    def capture_run(cmd, **kwargs):
        call_kwargs.update(kwargs)
        return _fake_run(0, '{"result": "x"}')

    with patch("oxidant.agents.invoke.subprocess.run", side_effect=capture_run):
        invoke_claude("p", cwd=str(tmp_path), tier="haiku")
    haiku_timeout = call_kwargs["timeout"]

    with patch("oxidant.agents.invoke.subprocess.run", side_effect=capture_run):
        invoke_claude("p", cwd=str(tmp_path), tier="opus")
    opus_timeout = call_kwargs["timeout"]

    assert haiku_timeout < opus_timeout
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_invoke.py -v 2>&1 | tail -15
```

Expected: All FAIL with ImportError.

- [ ] **Step 3: Create `src/oxidant/agents/invoke.py`**

```python
"""Invoke Claude Code CLI as a subprocess for Phase B node translation.

IMPORTANT: Always strips ANTHROPIC_API_KEY from the environment before invoking.
If the key is present, Claude Code bills to the API account instead of the user's
Max subscription — this has caused accidental charges of $1,800+ for other users.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_TIMEOUT_BY_TIER: dict[str, int] = {
    "haiku": 120,
    "sonnet": 240,
    "opus": 360,
}
_DEFAULT_TIMEOUT = 300
_MAX_PROMPT_LOG_CHARS = 200


def invoke_claude(
    prompt: str,
    cwd: str | Path,
    tier: str = "sonnet",
) -> str:
    """Call ``claude --print --output-format json`` and return the response text.

    Args:
        prompt: The full conversion prompt to send to the model.
        cwd: Working directory for the subprocess (skeleton project root).
        tier: Translation tier — controls the timeout ("haiku" | "sonnet" | "opus").

    Returns:
        The assistant's response text (value of the ``result`` key in the JSON).

    Raises:
        RuntimeError: claude exits non-zero, returns non-JSON, or ``result`` is absent.
        subprocess.TimeoutExpired: Call exceeds the tier-specific timeout.
    """
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)  # CRITICAL: force Max subscription auth

    timeout = _TIMEOUT_BY_TIER.get(tier, _DEFAULT_TIMEOUT)
    logger.debug(
        "invoke_claude tier=%s prompt[:200]=%r",
        tier,
        prompt[:_MAX_PROMPT_LOG_CHARS],
    )

    result = subprocess.run(
        ["claude", "--print", "--output-format", "json", prompt],
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"claude exited {result.returncode}:\n{result.stderr[:500]}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude returned non-JSON output: {result.stdout[:200]}"
        ) from exc

    if "result" not in data:
        raise RuntimeError(
            f"claude JSON missing 'result' key: {list(data.keys())}"
        )

    return str(data["result"])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_invoke.py -v 2>&1 | tail -15
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/oxidant/agents/invoke.py tests/test_invoke.py
git commit -m "feat: Claude Code subprocess invocation with API key stripping"
```

---

### Task 4: Prompt context assembly

**Background:** Each node gets a prompt that includes: TypeScript source, the Rust function signature extracted from the skeleton, converted Rust snippets of all in-manifest dependencies, relevant idiom dictionary entries (if `idiom_dictionary.md` exists), and retry context on subsequent attempts. The signature is extracted by finding the `todo!` marker in the skeleton .rs file and walking back to the `pub fn` line.

**Files:**
- Create: `src/oxidant/agents/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_context.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from oxidant.agents.context import build_prompt, _extract_rust_signature
from oxidant.models.manifest import (
    ConversionNode, Manifest, NodeKind, NodeStatus, TranslationTier,
)


def _make_node(node_id: str, kind: NodeKind = NodeKind.FREE_FUNCTION, **kw) -> ConversionNode:
    return ConversionNode(
        node_id=node_id,
        source_file="simple.ts",
        line_start=1,
        line_end=5,
        source_text="function foo(x: number): number { return x + 1; }",
        node_kind=kind,
        tier=TranslationTier.HAIKU,
        **kw,
    )


def _make_manifest(nodes: dict) -> Manifest:
    return Manifest(source_repo="test", generated_at="2026-04-15", nodes=nodes)


def test_build_prompt_contains_source():
    """Prompt must include the TypeScript source text."""
    node = _make_node("simple__foo")
    manifest = _make_manifest({"simple__foo": node})
    config = {"crate_inventory": ["serde"], "architectural_decisions": {}}

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config=config,
        target_path=Path("/nonexistent"),
        snippets_dir=Path("/nonexistent/snippets"),
        workspace=Path("/nonexistent"),
    )

    assert "function foo(x: number): number { return x + 1; }" in prompt


def test_build_prompt_contains_crates():
    """Prompt must list the approved crates from config."""
    node = _make_node("simple__foo")
    manifest = _make_manifest({"simple__foo": node})
    config = {"crate_inventory": ["slotmap", "petgraph"], "architectural_decisions": {}}

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config=config,
        target_path=Path("/nonexistent"),
        snippets_dir=Path("/nonexistent/snippets"),
        workspace=Path("/nonexistent"),
    )

    assert "slotmap" in prompt
    assert "petgraph" in prompt


def test_build_prompt_contains_retry_context():
    """On retry, prompt must include the previous error."""
    node = _make_node("simple__foo")
    manifest = _make_manifest({"simple__foo": node})
    config = {"crate_inventory": [], "architectural_decisions": {}}

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config=config,
        target_path=Path("/nonexistent"),
        snippets_dir=Path("/nonexistent/snippets"),
        workspace=Path("/nonexistent"),
        last_error="error[E0308]: type mismatch",
        attempt_count=1,
    )

    assert "error[E0308]" in prompt
    assert "attempt" in prompt.lower()


def test_build_prompt_includes_dep_snippet(tmp_path):
    """When a dep has a snippet on disk, it appears in the prompt."""
    snippets_dir = tmp_path / "snippets" / "simple"
    snippets_dir.mkdir(parents=True)
    dep_snippet = snippets_dir / "simple__bar.rs"
    dep_snippet.write_text("let result = bar_impl();")

    dep_node = _make_node("simple__bar", status=NodeStatus.CONVERTED,
                          snippet_path=str(dep_snippet))
    foo_node = _make_node("simple__foo", call_dependencies=["simple__bar"])

    manifest = _make_manifest({"simple__bar": dep_node, "simple__foo": foo_node})
    config = {"crate_inventory": [], "architectural_decisions": {}}

    prompt = build_prompt(
        node=foo_node,
        manifest=manifest,
        config=config,
        target_path=Path("/nonexistent"),
        snippets_dir=tmp_path / "snippets",
        workspace=tmp_path,
    )

    assert "let result = bar_impl();" in prompt


def test_extract_rust_signature_from_skeleton(tmp_path):
    """Extracts the pub fn line above a todo! marker."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    rs_file = src_dir / "simple.rs"
    rs_file.write_text(
        '#![allow(dead_code)]\n'
        'pub fn distance(a: f64, b: f64) -> f64 {\n'
        '    todo!("OXIDANT: not yet translated — simple__distance")\n'
        '}\n'
    )

    sig = _extract_rust_signature("simple__distance", tmp_path, "simple.ts")
    assert "pub fn distance" in sig
    assert "f64" in sig


def test_extract_rust_signature_missing_returns_comment(tmp_path):
    """Returns a comment when the node_id is not found in the skeleton."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "simple.rs").write_text("// empty\n")

    sig = _extract_rust_signature("simple__nonexistent", tmp_path, "simple.ts")
    assert sig.startswith("//")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_context.py -v 2>&1 | tail -15
```

Expected: All FAIL with ImportError.

- [ ] **Step 3: Create `src/oxidant/agents/context.py`**

```python
"""Assemble the conversion prompt for a single manifest node.

The prompt includes: TypeScript source, Rust signature from skeleton,
converted dependency snippets, idiom dictionary entries, and retry context.
"""
from __future__ import annotations

import re
from pathlib import Path

from oxidant.models.manifest import ConversionNode, Manifest

_PROMPT_TEMPLATE = """\
You are translating a TypeScript function to Rust as part of converting the \
msagl-js graph layout library.

## Critical Rules
- Output ONLY the Rust function body (the code between the outer braces). \
No signatures, no markdown fences, no explanation.
- Do NOT use todo!(), unimplemented!(), or panic!()
- Do NOT simplify, optimize, or restructure — translate semantically faithfully
- Match every conditional branch in the TypeScript source exactly
- Use only approved crates: {crates}

## Architectural Decisions
{arch_decisions}

## Node to Convert
Kind: {node_kind}
Node ID: {node_id}

### TypeScript Source
```typescript
{source_text}
```

### Rust Function Signature (from skeleton — do not change)
```rust
{rust_signature}
```
{deps_section}\
{idiom_section}\
{retry_section}\
Respond with ONLY the Rust function body. No markdown, no explanation.\
"""


def _module_name_for_source(source_file: str) -> str:
    from oxidant.analysis.generate_skeleton import _module_name
    return _module_name(source_file)


def _extract_rust_signature(
    node_id: str,
    target_path: Path,
    source_file: str,
) -> str:
    """Extract the ``pub fn`` signature line for node_id from the skeleton .rs file."""
    module = _module_name_for_source(source_file)
    rs_file = target_path / "src" / f"{module}.rs"
    if not rs_file.exists():
        return f"// signature not found: {module}.rs does not exist"

    content = rs_file.read_text()
    marker = f'todo!("OXIDANT: not yet translated — {node_id}")'
    if marker not in content:
        return f"// signature not found for {node_id} in {module}.rs"

    lines = content.split("\n")
    for i, line in enumerate(lines):
        if marker in line:
            # Walk back up to 5 lines to find the pub fn declaration
            for j in range(i - 1, max(i - 6, -1), -1):
                if "pub fn" in lines[j]:
                    return lines[j].rstrip()
            return f"// pub fn not found near todo! marker for {node_id}"

    return f"// signature not found for {node_id}"


def _load_dep_snippets(
    node: ConversionNode,
    manifest: Manifest,
    snippets_dir: Path,
) -> str:
    """Load converted Rust snippet bodies for all in-manifest dependencies."""
    lines: list[str] = []
    seen: set[str] = set()

    for dep_id in list(node.type_dependencies) + list(node.call_dependencies):
        if dep_id in seen or dep_id not in manifest.nodes:
            continue
        seen.add(dep_id)
        dep_node = manifest.nodes[dep_id]
        if not dep_node.snippet_path:
            continue
        p = Path(dep_node.snippet_path)
        if p.exists():
            lines.append(f"// ── {dep_id} ──")
            lines.append(p.read_text().strip())

    return "\n".join(lines)


def _load_idiom_entries(idioms: list[str], workspace: Path) -> str:
    """Load relevant sections from idiom_dictionary.md for the node's idioms."""
    dict_path = workspace / "idiom_dictionary.md"
    if not dict_path.exists() or not idioms:
        return ""

    content = dict_path.read_text()
    entries: list[str] = []
    for idiom in idioms:
        pattern = re.compile(
            rf"^##\s+{re.escape(idiom)}\b.*?(?=^##\s|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        m = pattern.search(content)
        if m:
            entries.append(m.group(0).strip())

    return "\n\n".join(entries)


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
    """Build the full conversion prompt for one manifest node."""
    crates = ", ".join(config.get("crate_inventory", []))
    arch = config.get("architectural_decisions", {})
    arch_lines = "\n".join(f"- {k}: {v}" for k, v in arch.items()) or "None specified."

    rust_sig = _extract_rust_signature(node.node_id, target_path, node.source_file)

    dep_text = _load_dep_snippets(node, manifest, snippets_dir)
    deps_section = (
        f"\n## Converted Dependencies\n```rust\n{dep_text}\n```\n"
        if dep_text
        else ""
    )

    idiom_text = _load_idiom_entries(node.idioms_needed, workspace)
    idiom_section = f"\n## Idiom Translations\n{idiom_text}\n" if idiom_text else ""

    retry_section = ""
    if attempt_count > 0 and last_error:
        retry_section = (
            f"\n## Previous Attempt Failed (attempt {attempt_count})\n"
            f"Fix this error:\n```\n{last_error}\n```\n"
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
        retry_section=retry_section,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_context.py -v 2>&1 | tail -15
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/oxidant/agents/context.py tests/test_context.py
git commit -m "feat: prompt context assembly for Phase B node translation"
```

---

### Task 5: Verification pipeline

**Background:** Three checks in order of cost:
1. **Stub check** (instant): grep for `todo!(` or `unimplemented!(` in the snippet body.
2. **Branch parity** (instant): count if/else/match/for/while constructs in TypeScript source vs Rust snippet. If TS has ≥3 branches and Rust has < 60% of that count, flag it.
3. **Cargo check** (~5-30 s): inject the snippet into the skeleton .rs file (replacing the `todo!` marker), run `cargo check --message-format=short`, restore the original regardless of outcome. Returns the compiler error on failure.

The `_module_name` helper is imported from `generate_skeleton` (same package — acceptable coupling).

**Files:**
- Create: `src/oxidant/verification/__init__.py`
- Create: `src/oxidant/verification/verify.py`
- Create: `tests/test_verify.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_verify.py`:

```python
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from oxidant.verification.verify import (
    VerifyResult,
    VerifyStatus,
    verify_snippet,
    _check_stubs,
    _check_branch_parity,
)


# ── Stub check ────────────────────────────────────────────────────────────────

def test_stub_check_rejects_todo():
    result = _check_stubs('todo!("not implemented")')
    assert result is not None
    assert result.status == VerifyStatus.STUB


def test_stub_check_rejects_unimplemented():
    result = _check_stubs("unimplemented!()")
    assert result is not None
    assert result.status == VerifyStatus.STUB


def test_stub_check_passes_clean_code():
    result = _check_stubs("let x = 42; x + 1")
    assert result is None


# ── Branch parity check ───────────────────────────────────────────────────────

def test_branch_parity_passes_simple():
    """A single-branch function passes parity regardless of Rust count."""
    ts = "function foo() { return 1; }"
    rs = "1"
    assert _check_branch_parity(ts, rs) is None


def test_branch_parity_fails_many_ts_branches_no_rust():
    """TS has many branches, Rust has none → BRANCH."""
    ts = "if a { } else if b { } else { } for (x of y) { } while (z) { }"
    rs = "42"
    result = _check_branch_parity(ts, rs)
    assert result is not None
    assert result.status == VerifyStatus.BRANCH


def test_branch_parity_passes_matching_branches():
    ts = "if a { } else if b { } else { } for (x of y) { }"
    rs = "if a { } else if b { } else { } for x in y { }"
    assert _check_branch_parity(ts, rs) is None


# ── Full verify_snippet ───────────────────────────────────────────────────────

def test_verify_snippet_stub_fails_before_cargo(tmp_path):
    """Stub check short-circuits — cargo check is never called."""
    result = verify_snippet(
        node_id="m__foo",
        snippet='todo!("still a stub")',
        ts_source="function foo() {}",
        target_path=tmp_path,
        source_file="m.ts",
    )
    assert result.status == VerifyStatus.STUB


def test_verify_snippet_cargo_check_pass(tmp_path):
    """When cargo check passes, result is PASS."""
    src = tmp_path / "src"
    src.mkdir()
    rs_file = src / "m.rs"
    rs_file.write_text(
        'pub fn foo() {\n'
        '    todo!("OXIDANT: not yet translated — m__foo")\n'
        '}\n'
    )

    fake_cargo = MagicMock()
    fake_cargo.returncode = 0
    fake_cargo.stderr = ""
    fake_cargo.stdout = ""

    with patch("oxidant.verification.verify.subprocess.run", return_value=fake_cargo):
        result = verify_snippet(
            node_id="m__foo",
            snippet="42",
            ts_source="function foo() { return 42; }",
            target_path=tmp_path,
            source_file="m.ts",
        )

    assert result.status == VerifyStatus.PASS
    # Skeleton must be restored to original after check
    assert 'todo!("OXIDANT: not yet translated — m__foo")' in rs_file.read_text()


def test_verify_snippet_cargo_check_fail(tmp_path):
    """When cargo check fails, result is CARGO with error text."""
    src = tmp_path / "src"
    src.mkdir()
    rs_file = src / "m.rs"
    rs_file.write_text(
        'pub fn foo() -> i32 {\n'
        '    todo!("OXIDANT: not yet translated — m__foo")\n'
        '}\n'
    )

    fake_cargo = MagicMock()
    fake_cargo.returncode = 1
    fake_cargo.stderr = "error[E0308]: mismatched types"
    fake_cargo.stdout = ""

    with patch("oxidant.verification.verify.subprocess.run", return_value=fake_cargo):
        result = verify_snippet(
            node_id="m__foo",
            snippet='"hello"',
            ts_source="function foo(): number { return 42; }",
            target_path=tmp_path,
            source_file="m.ts",
        )

    assert result.status == VerifyStatus.CARGO
    assert "E0308" in result.error
    # Skeleton always restored
    assert 'todo!("OXIDANT: not yet translated — m__foo")' in rs_file.read_text()


def test_verify_snippet_restores_skeleton_even_on_exception(tmp_path):
    """Skeleton is restored even if subprocess.run raises an exception."""
    src = tmp_path / "src"
    src.mkdir()
    rs_file = src / "m.rs"
    original = 'pub fn foo() {\n    todo!("OXIDANT: not yet translated — m__foo")\n}\n'
    rs_file.write_text(original)

    with patch("oxidant.verification.verify.subprocess.run", side_effect=OSError("no cargo")):
        result = verify_snippet(
            node_id="m__foo",
            snippet="42",
            ts_source="function foo() {}",
            target_path=tmp_path,
            source_file="m.ts",
        )

    assert result.status == VerifyStatus.CARGO
    assert rs_file.read_text() == original
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_verify.py -v 2>&1 | tail -15
```

Expected: All FAIL with ImportError.

- [ ] **Step 3: Create `src/oxidant/verification/__init__.py`**

```python
```

(empty file)

- [ ] **Step 4: Create `src/oxidant/verification/verify.py`**

```python
"""Verification pipeline for converted Rust snippets.

Three checks in order of cost (cheapest first):
1. Stub check   — instant: grep for todo!/unimplemented!
2. Branch parity — instant: rough structural comparison
3. Cargo check  — ~5-30 s: inject into skeleton, run cargo check, restore stub
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class VerifyStatus(str, Enum):
    PASS = "PASS"
    STUB = "STUB"        # todo!/unimplemented! found in snippet
    BRANCH = "BRANCH"    # branch parity check failed
    CARGO = "CARGO"      # cargo check compilation failed


@dataclass
class VerifyResult:
    status: VerifyStatus
    error: str = field(default="")


_STUB_RE = re.compile(r'\btodo!\s*\(|\bunimplemented!\s*\(')
_BRANCH_RE_TS = re.compile(r'\bif\b|\belse\b|\bswitch\b|\bcase\b|\bfor\b|\bwhile\b|\?\s')
_BRANCH_RE_RS = re.compile(r'\bif\b|\belse\b|\bmatch\b|\bfor\b|\bwhile\b|\bloop\b')

_BRANCH_MIN_TS_COUNT = 3          # only check parity when TS has ≥ this many branches
_BRANCH_RATIO_FLOOR = 0.60        # Rust must have ≥ 60% as many branches as TS
_CARGO_TIMEOUT_SECONDS = 120


def _check_stubs(snippet: str) -> VerifyResult | None:
    if _STUB_RE.search(snippet):
        return VerifyResult(VerifyStatus.STUB, "Snippet contains todo!() or unimplemented!()")
    return None


def _check_branch_parity(ts_source: str, rs_snippet: str) -> VerifyResult | None:
    ts_count = len(_BRANCH_RE_TS.findall(ts_source))
    rs_count = len(_BRANCH_RE_RS.findall(rs_snippet))
    if ts_count >= _BRANCH_MIN_TS_COUNT and rs_count < ts_count * _BRANCH_RATIO_FLOOR:
        return VerifyResult(
            VerifyStatus.BRANCH,
            f"Branch parity: TypeScript={ts_count} branches, Rust={rs_count} "
            f"(below {_BRANCH_RATIO_FLOOR:.0%} floor)",
        )
    return None


def _module_name(source_file: str) -> str:
    from oxidant.analysis.generate_skeleton import _module_name as _gen_module_name
    return _gen_module_name(source_file)


def _inject_and_check_cargo(
    node_id: str,
    snippet: str,
    target_path: Path,
    source_file: str,
) -> VerifyResult | None:
    """Inject snippet into skeleton, run cargo check, always restore original."""
    module = _module_name(source_file)
    rs_path = target_path / "src" / f"{module}.rs"

    marker = f'todo!("OXIDANT: not yet translated — {node_id}")'
    original_content = rs_path.read_text()

    if marker not in original_content:
        return VerifyResult(
            VerifyStatus.CARGO,
            f"todo! marker not found for {node_id} in {module}.rs",
        )

    rs_path.write_text(original_content.replace(marker, snippet, 1))
    try:
        proc = subprocess.run(
            ["cargo", "check", "--message-format=short"],
            cwd=target_path,
            capture_output=True,
            text=True,
            timeout=_CARGO_TIMEOUT_SECONDS,
        )
        if proc.returncode == 0:
            return None
        error_text = proc.stderr[:2000] or proc.stdout[:2000]
        return VerifyResult(VerifyStatus.CARGO, error_text)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return VerifyResult(VerifyStatus.CARGO, str(exc))
    finally:
        rs_path.write_text(original_content)


def verify_snippet(
    node_id: str,
    snippet: str,
    ts_source: str,
    target_path: Path,
    source_file: str,
) -> VerifyResult:
    """Run all three verification checks and return the first failure, or PASS.

    Args:
        node_id: The manifest node ID (used to find the todo! marker).
        snippet: The raw Rust function body text returned by the agent.
        ts_source: The original TypeScript source text (for branch parity).
        target_path: Root of the skeleton Rust project.
        source_file: The node's TypeScript source file path.
    """
    if r := _check_stubs(snippet):
        return r
    if r := _check_branch_parity(ts_source, snippet):
        return r
    if r := _inject_and_check_cargo(node_id, snippet, target_path, source_file):
        return r
    return VerifyResult(VerifyStatus.PASS)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_verify.py -v 2>&1 | tail -15
```

Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/verification/__init__.py src/oxidant/verification/verify.py tests/test_verify.py
git commit -m "feat: three-check verification pipeline (stub, branch parity, cargo check)"
```

---

### Task 6: LangGraph node functions

**Background:** Each function in `nodes.py` is a LangGraph node. Nodes return **only the keys they change** — never `{**state, ...}`. This is critical for the `review_queue` field, which uses an `operator.add` reducer: returning the full accumulated list would double-append. `route_after_verify` is a routing function (returns a string), not a node.

Escalation ladder: haiku → sonnet after 3 failures; sonnet → opus after 4; opus → human queue after 5.

**Files:**
- Create: `src/oxidant/graph/nodes.py`
- Create: `tests/test_graph_nodes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_graph_nodes.py`:

```python
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


def _base_state(manifest_path: str, target_path: str = "/nonexistent", **kw) -> OxidantState:
    return OxidantState(
        manifest_path=manifest_path,
        target_path=target_path,
        snippets_dir="/tmp/snippets",
        config={"crate_inventory": [], "architectural_decisions": {}, "model_tiers": {}},
        current_node_id=None,
        current_prompt=None,
        current_snippet=None,
        current_tier=None,
        attempt_count=0,
        last_error=None,
        verify_status=None,
        review_queue=[],
        done=False,
        **kw,
    )


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
    # attempt_count=3 means this is the 4th attempt (0-indexed), haiku limit=3
    state = _base_state("/dev/null", verify_status="STUB", attempt_count=3, current_tier="haiku")
    assert route_after_verify(state) == "escalate"


def test_route_human_review_after_opus_limit():
    from oxidant.graph.nodes import route_after_verify
    state = _base_state("/dev/null", verify_status="CARGO", attempt_count=5, current_tier="opus")
    assert route_after_verify(state) == "queue_for_review"


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_graph_nodes.py -v 2>&1 | tail -20
```

Expected: All FAIL with ImportError.

- [ ] **Step 3: Create `src/oxidant/graph/nodes.py`**

```python
"""LangGraph node functions for the Phase B translation loop.

Each function receives the full OxidantState and returns ONLY the keys it modifies.
Never return {**state, ...} — that would cause the operator.add reducer on
review_queue to double-accumulate existing entries.
"""
from __future__ import annotations

import logging
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
    manifest = Manifest.load(Path(state["manifest_path"]))
    eligible = manifest.eligible_nodes()

    if not eligible:
        remaining = [
            n for n in manifest.nodes.values()
            if n.status == NodeStatus.NOT_STARTED
        ]
        if remaining:
            logger.warning(
                "%d nodes blocked by unresolvable dependencies.", len(remaining)
            )
        else:
            logger.info("All nodes converted. Phase B complete.")
        return {"current_node_id": None, "done": True}

    node = min(eligible, key=lambda n: n.topological_order or 0)
    manifest.update_node(
        Path(state["manifest_path"]), node.node_id, status=NodeStatus.IN_PROGRESS
    )

    tier = node.tier.value if node.tier else TranslationTier.HAIKU.value
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
    )
    return {"current_prompt": prompt}


def invoke_agent(state: OxidantState) -> dict:
    """Call the Claude Code subprocess and capture the Rust snippet body."""
    tier = state.get("current_tier") or TranslationTier.HAIKU.value
    try:
        response = invoke_claude(
            prompt=state["current_prompt"],
            cwd=state["target_path"],
            tier=tier,
        )
        return {"current_snippet": response, "last_error": None}
    except Exception as exc:  # noqa: BLE001
        logger.error("invoke_claude failed for %s: %s", state.get("current_node_id"), exc)
        return {"current_snippet": None, "last_error": str(exc)}


def verify(state: OxidantState) -> dict:
    """Run the three verification checks (stub / branch parity / cargo check)."""
    manifest = Manifest.load(Path(state["manifest_path"]))
    node = manifest.nodes[state["current_node_id"]]
    snippet = state.get("current_snippet") or ""

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
            return "queue_for_review"
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

    manifest.update_node(
        Path(state["manifest_path"]),
        node_id,
        status=NodeStatus.CONVERTED,
        snippet_path=str(snippet_path),
        attempt_count=state.get("attempt_count", 0),
    )
    logger.info("CONVERTED: %s → %s", node_id, snippet_path)
    return {}


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
    return {"review_queue": [entry]}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_graph_nodes.py -v 2>&1 | tail -20
```

Expected: 11 passed.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: ~64 passed (all previous + new).

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/graph/nodes.py tests/test_graph_nodes.py
git commit -m "feat: LangGraph node functions for Phase B translation loop"
```

---

### Task 7: LangGraph graph wiring

**Background:** Wire all nodes into a `StateGraph(OxidantState)`. The graph loops: `pick_next_node → build_context → invoke_agent → verify`, then branches. After `update_manifest` or `queue_for_review`, control returns to `pick_next_node`. The loop exits via `END` when `pick_next_node` sets `done=True`.

**Files:**
- Create: `src/oxidant/graph/graph.py`

No dedicated test file — the graph is a thin wiring layer. Integration test comes in Task 9 (CLI).

- [ ] **Step 1: Create `src/oxidant/graph/graph.py`**

```python
"""LangGraph state graph for the Phase B translation loop.

Wires all node functions into a compilable StateGraph. The module-level
``translation_graph`` is the compiled graph ready for ``.invoke()``.
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
    route_after_verify,
    update_manifest,
    verify,
)
from oxidant.graph.state import OxidantState


def _route_pick(state: OxidantState) -> str:
    return "done" if state.get("done") else "continue"


def build_graph() -> object:
    """Construct and compile the Phase B LangGraph state graph."""
    graph: StateGraph = StateGraph(OxidantState)

    graph.add_node("pick_next_node", pick_next_node)
    graph.add_node("build_context", build_context)
    graph.add_node("invoke_agent", invoke_agent)
    graph.add_node("verify", verify)
    graph.add_node("retry_node", retry_node)
    graph.add_node("escalate_node", escalate_node)
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
            "queue_for_review": "queue_for_review",
        },
    )
    graph.add_edge("retry_node", "build_context")
    graph.add_edge("escalate_node", "build_context")
    graph.add_edge("update_manifest", "pick_next_node")
    graph.add_edge("queue_for_review", "pick_next_node")

    return graph.compile()


# Compiled graph — import and call .invoke(initial_state)
translation_graph = build_graph()
```

- [ ] **Step 2: Verify the graph compiles**

```bash
.venv/bin/python -c "from oxidant.graph.graph import translation_graph; print('graph ok')"
```

Expected: `graph ok`

- [ ] **Step 3: Commit**

```bash
git add src/oxidant/graph/graph.py
git commit -m "feat: wire LangGraph state graph for Phase B translation loop"
```

---

### Task 8: Module file assembly

**Background:** After all functional nodes in a module are CONVERTED, `assemble_module` replaces the skeleton's stub .rs file with one assembled from the individual snippets. Order: enums first, then interfaces (traits), then class structs (the skeleton's struct/impl block is used as-is since fields aren't yet translated), then methods/constructors (from snippets), then free functions. `check_and_assemble` runs over the entire manifest and assembles any module that is ready.

Note: For Phase B v1, the assembly writes each snippet preceded by the skeleton's struct/trait block for context. Full structural reconstruction is deferred to Phase C. The key invariant: assembled modules must still pass `cargo check`.

**Files:**
- Create: `src/oxidant/assembly/__init__.py`
- Create: `src/oxidant/assembly/assemble.py`
- Create: `tests/test_assemble.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_assemble.py`:

```python
from pathlib import Path
import pytest
from oxidant.models.manifest import (
    ConversionNode, Manifest, NodeKind, NodeStatus, TranslationTier,
)
from oxidant.assembly.assemble import assemble_module, check_and_assemble


def _make_node(node_id: str, kind: NodeKind, **kw) -> ConversionNode:
    return ConversionNode(
        node_id=node_id, source_file="m.ts", line_start=1, line_end=5,
        source_text="function foo() {}", node_kind=kind,
        tier=TranslationTier.HAIKU, **kw,
    )


def test_assemble_module_writes_rs_file(tmp_path):
    """assemble_module writes a .rs file with snippet contents."""
    snippets_dir = tmp_path / "snippets" / "m"
    snippets_dir.mkdir(parents=True)

    snippet_path = snippets_dir / "m__foo.rs"
    snippet_path.write_text("42")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "m.rs").write_text(
        '#![allow(dead_code)]\npub fn foo() {\n    todo!("OXIDANT: m__foo")\n}\n'
    )

    nodes = [
        _make_node("m__foo", NodeKind.FREE_FUNCTION,
                   status=NodeStatus.CONVERTED, snippet_path=str(snippet_path)),
    ]
    result = assemble_module("m", nodes, tmp_path)
    assert result is True
    content = (src_dir / "m.rs").read_text()
    assert "42" in content
    assert "m__foo" in content


def test_assemble_module_returns_false_when_not_all_converted(tmp_path):
    """Returns False if any functional node is not yet CONVERTED."""
    (tmp_path / "src").mkdir()
    nodes = [
        _make_node("m__foo", NodeKind.FREE_FUNCTION, status=NodeStatus.NOT_STARTED),
    ]
    result = assemble_module("m", nodes, tmp_path)
    assert result is False


def test_assemble_module_skips_structural_nodes(tmp_path):
    """Structural nodes don't need snippets — module assembles from functional ones only."""
    snippets_dir = tmp_path / "snippets" / "m"
    snippets_dir.mkdir(parents=True)
    snippet_path = snippets_dir / "m__foo.rs"
    snippet_path.write_text("99")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "m.rs").write_text("// skeleton\n")

    nodes = [
        _make_node("m__MyClass", NodeKind.CLASS, status=NodeStatus.CONVERTED),
        _make_node("m__foo", NodeKind.FREE_FUNCTION,
                   status=NodeStatus.CONVERTED, snippet_path=str(snippet_path)),
    ]
    result = assemble_module("m", nodes, tmp_path)
    assert result is True


def test_check_and_assemble_returns_assembled_modules(tmp_path):
    """check_and_assemble returns names of modules that were assembled."""
    snippets_dir = tmp_path / "snippets" / "m"
    snippets_dir.mkdir(parents=True)
    sp = snippets_dir / "m__foo.rs"
    sp.write_text("42")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "m.rs").write_text("// stub\n")

    manifest = Manifest(
        source_repo="t", generated_at="2026-04-15",
        nodes={
            "m__foo": _make_node(
                "m__foo", NodeKind.FREE_FUNCTION,
                status=NodeStatus.CONVERTED, snippet_path=str(sp),
            ),
        },
    )
    assembled = check_and_assemble(manifest, tmp_path)
    assert "m" in assembled
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_assemble.py -v 2>&1 | tail -15
```

Expected: All FAIL with ImportError.

- [ ] **Step 3: Create `src/oxidant/assembly/__init__.py`** (empty)

- [ ] **Step 4: Create `src/oxidant/assembly/assemble.py`**

```python
"""Assemble converted Rust snippet files into full module .rs files.

When all functional nodes (CONSTRUCTOR / METHOD / GETTER / SETTER / FREE_FUNCTION)
in a module are CONVERTED, this module replaces the skeleton's stub .rs file with
one that inlines each snippet, preceded by the node ID as a comment.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from oxidant.models.manifest import ConversionNode, Manifest, NodeKind, NodeStatus

logger = logging.getLogger(__name__)

_STRUCTURAL_KINDS: frozenset[NodeKind] = frozenset({
    NodeKind.CLASS, NodeKind.INTERFACE, NodeKind.ENUM, NodeKind.TYPE_ALIAS,
})

_SNIPPET_KIND_ORDER: list[NodeKind] = [
    NodeKind.CONSTRUCTOR,
    NodeKind.METHOD,
    NodeKind.GETTER,
    NodeKind.SETTER,
    NodeKind.FREE_FUNCTION,
]

_FILE_HEADER = """\
#![allow(dead_code, unused_variables, unused_imports, non_snake_case)]
use std::rc::Rc;
use std::cell::RefCell;
use std::collections::{{HashMap, HashSet}};
"""


def _load_snippet(node: ConversionNode) -> str | None:
    if not node.snippet_path:
        return None
    p = Path(node.snippet_path)
    if not p.exists():
        logger.warning("Snippet file not found: %s", node.snippet_path)
        return None
    return p.read_text()


def assemble_module(
    module: str,
    nodes: list[ConversionNode],
    target_path: Path,
) -> bool:
    """Replace the skeleton .rs file with assembled snippet content.

    Returns True if assembly succeeded (all functional nodes CONVERTED),
    False if any functional node is not yet ready.
    """
    functional = [n for n in nodes if n.node_kind not in _STRUCTURAL_KINDS]
    if any(n.status != NodeStatus.CONVERTED for n in functional):
        return False

    rs_path = target_path / "src" / f"{module}.rs"
    if not rs_path.exists():
        logger.warning("Skeleton file not found: %s", rs_path)
        return False

    lines: list[str] = [_FILE_HEADER]

    for kind in _SNIPPET_KIND_ORDER:
        kind_nodes = sorted(
            (n for n in nodes if n.node_kind == kind),
            key=lambda n: n.topological_order or 0,
        )
        for node in kind_nodes:
            snippet = _load_snippet(node)
            if snippet is None:
                lines.append(f"// OXIDANT: missing snippet — {node.node_id}")
                continue
            lines.append(f"// ── {node.node_id} ──")
            lines.append(snippet.strip())
            lines.append("")

    rs_path.write_text("\n".join(lines) + "\n")
    logger.info("Assembled %s (%d functional nodes)", rs_path.name, len(functional))
    return True


def _module_name(source_file: str) -> str:
    from oxidant.analysis.generate_skeleton import _module_name as _gen
    return _gen(source_file)


def check_and_assemble(manifest: Manifest, target_path: Path) -> list[str]:
    """Assemble all modules whose functional nodes are fully CONVERTED.

    Returns the list of module names that were successfully assembled.
    """
    by_module: dict[str, list[ConversionNode]] = defaultdict(list)
    for node in manifest.nodes.values():
        by_module[_module_name(node.source_file)].append(node)

    assembled: list[str] = []
    for module, nodes in sorted(by_module.items()):
        if assemble_module(module, nodes, target_path):
            assembled.append(module)

    return assembled
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_assemble.py -v 2>&1 | tail -15
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/assembly/__init__.py src/oxidant/assembly/assemble.py tests/test_assemble.py
git commit -m "feat: module assembly from converted snippets"
```

---

### Task 9: CLI `phase-b` command

**Background:** Add `oxidant phase-b` to the existing Typer CLI. Before running the LangGraph loop, auto-convert structural nodes. Provide a `--dry-run` flag that prints the first node's prompt and exits — useful for verifying context assembly without burning API quota.

**Files:**
- Modify: `src/oxidant/cli.py`

- [ ] **Step 1: Read current `src/oxidant/cli.py`** before modifying

The file currently has `phase-a` and a stub `translate` command. Add `phase-b` after `phase-a`.

- [ ] **Step 2: Add the `phase-b` command to `src/oxidant/cli.py`**

Add the following after the `phase_a` function (before the `translate` command):

```python
@app.command("phase-b")
def phase_b(
    config: Path = typer.Option("oxidant.config.json", "--config", "-c"),
    manifest: Path = typer.Option("conversion_manifest.json", "--manifest"),
    snippets_dir: Path = typer.Option("snippets", "--snippets-dir"),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Print the first node's prompt then exit — no API calls made.",
    ),
) -> None:
    """Run Phase B: translate all nodes in topological order via Claude Code.

    Requires a compiled skeleton from ``oxidant phase-a``.
    Structural nodes (class/interface/enum/type_alias) are auto-converted first.
    Exhausted nodes are written to ``review_queue.json``.
    """
    import json as _json

    from oxidant.assembly.assemble import check_and_assemble
    from oxidant.graph.graph import translation_graph
    from oxidant.graph.nodes import build_context, pick_next_node
    from oxidant.graph.state import OxidantState
    from oxidant.models.manifest import Manifest as _Manifest

    cfg = _json.loads(config.read_text())
    manifest_obj = _Manifest.load(manifest)

    count = manifest_obj.auto_convert_structural_nodes(manifest)
    if count:
        typer.echo(f"Auto-converted {count} structural nodes.")

    snippets_dir.mkdir(parents=True, exist_ok=True)
    target_path = Path(cfg["target_repo"])

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

    final_state = translation_graph.invoke(initial_state)

    review_queue = final_state.get("review_queue", [])
    if review_queue:
        import json
        rq_path = Path("review_queue.json")
        rq_path.write_text(json.dumps(review_queue, indent=2))
        typer.echo(f"\n{len(review_queue)} nodes queued for human review → {rq_path}")

    manifest_final = _Manifest.load(manifest)
    assembled = check_and_assemble(manifest_final, target_path)
    if assembled:
        typer.echo(f"Assembled {len(assembled)} module(s).")

    typer.echo("\nPhase B complete.")
```

- [ ] **Step 3: Verify the CLI command is registered**

```bash
.venv/bin/oxidant --help 2>&1 | grep phase
```

Expected output includes both `phase-a` and `phase-b`.

- [ ] **Step 4: Test dry-run with a real manifest (if available)**

If `conversion_manifest.json` exists in the repo root, run:

```bash
.venv/bin/oxidant phase-b --manifest conversion_manifest.json \
  --config oxidant.config.json --dry-run 2>&1 | head -20
```

Expected: Shows first node ID and first 3000 chars of the prompt with no API calls.

If no manifest exists, skip this step (the unit tests in earlier tasks cover the behavior).

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: All previous tests still pass (no regressions from cli.py change).

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/cli.py
git commit -m "feat: add phase-b CLI command with --dry-run option"
```

---

## Self-Review

**Spec coverage check against PRD Section 3:**

| PRD requirement | Task that implements it |
|-----------------|------------------------|
| `pick_next_node` — eligible when all deps CONVERTED | Task 1 (manifest fix) + Task 6 |
| `assemble_context` — TypeScript source + dep snippets + idiom entries | Task 4 |
| `invoke_agent` — subprocess, strip ANTHROPIC_API_KEY | Task 3 |
| `verify` — stub check | Task 5 |
| `verify` — branch parity check | Task 5 |
| `verify` — `cargo check` with restoration | Task 5 |
| `handle_verify_result` — tier escalation (haiku→sonnet→opus) | Task 6 |
| `handle_verify_result` — human review queue after exhaustion | Task 6 |
| `update_manifest` — atomic status update + snippet path | Task 6 |
| `assemble_file` — assemble module when all nodes done | Task 8 |
| `human_review_queue` — JSON file with node details | Task 9 (CLI) |
| Parallelism (BFS levels) | **Not in this plan** — deferred; single-threaded correct first |
| LangGraph durable checkpointing | **Not in this plan** — deferred; adds SQLite checkpointer later |

**Parallelism and checkpointing** are noted as deferred. They are not YAGNI-safe for v1 — the loop is correct without them, and both can be layered on top of this implementation cleanly.

**Placeholder scan:** No TBD/TODO in any code block above. ✓

**Type consistency:** All nodes return `dict` (not `OxidantState`). `route_after_verify` returns `str`. `verify_snippet` returns `VerifyResult`. `build_prompt` returns `str`. `invoke_claude` returns `str`. Consistent throughout. ✓

**Structural node constants:** `_STRUCTURAL_KINDS` is defined independently in three files (`manifest.py`, `nodes.py`, `assemble.py`). This is intentional — they are module-private constants for different concerns. Extracting to a shared location would create coupling without benefit.
