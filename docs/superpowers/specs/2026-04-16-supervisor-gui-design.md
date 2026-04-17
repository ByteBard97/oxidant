# Oxidant Supervisor + GUI Design

## Architectural Decision: Process Model

**Decision: Option A — FastAPI + LangGraph in the same process**  
**Confidence: Medium-High**  
**Decided: 2026-04-16**

FastAPI runs Phase B's LangGraph graph as an asyncio background task in the same process. `claude --print` calls are wrapped in `asyncio.create_subprocess_exec`.

**Why:** LangGraph `interrupt()` is a physical coupling requirement — it raises `GraphInterrupt`, serializes to a checkpointer, and replays via that same instance. Splitting checkpointer and resume handler across processes requires hand-rolling LangGraph's interrupt/resume protocol as a second state machine. That cost outweighs the one-time async refactor.

**Mitigations for blast-radius risk:**
- `asyncio.create_subprocess_exec` with hard wall-clock timeout + process-group kill on failure
- `SqliteSaver` checkpointer (instead of `MemorySaver`) — durable across server restarts
- Subprocess watchdog emits structured error event to SSE queue on failure

**Deferred:** Re-evaluate process isolation at Phase C if multi-agent parallelism creates real resource contention.

---

## Spec 1 — Agent Infrastructure: Supervisor + Human-in-the-Loop

### Goal

Add a `supervisor_node` that fires at the escalation boundary (tier exhausted, before queuing for human review), provides a 2–3 sentence targeted hint, and re-queues the node for a retry. Wire `interrupt()` so a human can optionally step in when `review_mode = "interactive"`.

### State Additions (`OxidantState`)

```python
supervisor_hint: Optional[str]       # hint injected into next build_context call
interrupt_payload: Optional[dict]    # data surfaced to human reviewer
review_mode: Literal["auto", "interactive", "supervised"]  # default: "auto"
```

`review_mode` lives in `oxidant.config.json` and is read into state at graph init.

### Node: `supervisor_node`

**Placement:** fires when verification fails AND the current tier is exhausted (i.e., the path that currently leads to `queue_for_review`).

**Behavior:**
1. Receives: node source, Rust skeleton, error output, tier history
2. Calls Sonnet with a structured prompt: "Given this TypeScript source and this Rust error, generate a 2–3 sentence hint for the next translation attempt."
3. Writes `supervisor_hint` to state
4. If `review_mode = "interactive"`: calls `interrupt()` with `interrupt_payload` (source, error, hint) — pauses graph for human input
5. If `review_mode = "auto"` or `"supervised"`: returns hint directly, graph continues to `build_context` with hint injected
6. On resume: human-provided hint (if any) overwrites `supervisor_hint`; graph retries the node at the current tier

**Escalation path change:**

Before:
```
verify (fail, tier exhausted) → queue_for_review
```

After:
```
verify (fail, tier exhausted) → supervisor_node → build_context (with hint) → invoke_agent
                                     ↓ (interactive mode + human approves skip)
                                 queue_for_review
```

### `interrupt()` Wiring

- Checkpointer: swap `MemorySaver` → `SqliteSaver` in `graph.py`
- Each run gets a `thread_id` (e.g., `f"run-{timestamp}"`)
- `interrupt()` call in `supervisor_node` when `review_mode = "interactive"`
- FastAPI `POST /resume/{thread_id}` calls `graph.invoke(Command(resume=human_hint), config=...)`

### FastAPI Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/run` | Start a Phase B run, returns `thread_id` |
| `GET` | `/stream/{thread_id}` | SSE stream of progress events |
| `POST` | `/pause/{thread_id}` | Signal graph to pause after current node |
| `POST` | `/abort/{thread_id}` | Kill subprocess + mark run aborted |
| `POST` | `/resume/{thread_id}` | Resume after interrupt, body: `{"hint": "..."}` |
| `GET` | `/review-queue` | Nodes currently awaiting human review |
| `GET` | `/status/{thread_id}` | Run status snapshot |

### SSE Event Schema

```json
{ "event": "node_start",    "node_id": "...", "tier": "haiku" }
{ "event": "node_complete", "node_id": "...", "tier": "haiku", "attempts": 1 }
{ "event": "node_escalate", "node_id": "...", "from_tier": "haiku", "to_tier": "sonnet" }
{ "event": "supervisor",    "node_id": "...", "hint": "...", "requires_human": false }
{ "event": "interrupt",     "node_id": "...", "payload": { "source": "...", "error": "...", "hint": "..." } }
{ "event": "run_complete",  "converted": 42, "needs_review": 3 }
{ "event": "error",         "node_id": "...", "message": "..." }
```

### `invoke_claude` async refactor

Replace `subprocess.run` with:

```python
async def invoke_claude_async(prompt: str, timeout: int = 360) -> str:
    proc = await asyncio.create_subprocess_exec(
        "claude", "--print",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout=timeout)
        if proc.returncode != 0:
            raise InvokeError(stderr.decode())
        return stdout.decode()
    except asyncio.TimeoutError:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        raise InvokeError(f"claude --print timed out after {timeout}s")
```

---

## Spec 2 — GUI: Vue 3 Progress Dashboard

### Goal

A Vue 3 + Vite single-page app served by FastAPI (`/`) that gives operators real-time visibility into Phase B runs and (when `review_mode = "interactive"`) a panel for reviewing and providing hints.

### Stack

- **Vue 3** + **Vite** (TypeScript)
- **Pinia** for state
- **EventSource** (native browser API) for SSE
- **No component library** — minimal custom CSS, readable in 2 years
- Served as static files by FastAPI (`app.mount("/", StaticFiles(...))`)

### Components

```
App.vue
├── RunControls.vue       — Start · Pause · Abort · review_mode toggle
├── ProgressDashboard.vue — Module tree, tier bars, cost tracker, ETA
├── LiveNodeFeed.vue      — SSE stream: currently translating, recent completions
└── ReviewPanel.vue       — Active when review_mode=interactive + interrupt pending
    ├── NodeSource.vue    — TS source + Rust skeleton side-by-side
    ├── ErrorDisplay.vue  — Verification error
    ├── HintDisplay.vue   — Supervisor hint (editable)
    └── ResumeButton.vue  — POST /resume with human hint
```

### Pinia Store (`useRunStore`)

```typescript
interface RunState {
  threadId: string | null
  status: 'idle' | 'running' | 'paused' | 'interrupted' | 'complete' | 'aborted'
  reviewMode: 'auto' | 'interactive' | 'supervised'
  nodes: Record<string, NodeProgress>
  pendingReview: InterruptPayload | null
  eventLog: SSEEvent[]
  stats: { converted: number; needsReview: number; totalCost: number }
}
```

### Behavior

- **Start**: `POST /run` → receive `thread_id` → open `EventSource /stream/{thread_id}` → update store on each event
- **Pause**: `POST /pause/{thread_id}` → store status = 'paused'
- **Abort**: `POST /abort/{thread_id}` → confirm dialog → store status = 'aborted'
- **review_mode toggle**: visible in RunControls; calls `POST /run` with `review_mode` in body (only configurable before run starts)
- **ReviewPanel**: shown only when `status === 'interrupted'` and `pendingReview !== null`
  - Displays source, error, supervisor hint (pre-filled, user-editable)
  - Submit calls `POST /resume/{threadId}` with `{ hint: editedHint }`

### ProgressDashboard layout

- **Module tree**: collapsible tree of TS modules → nodes, colored by status (pending/converting/converted/needs_review)
- **Tier bars**: horizontal stacked bar per tier (haiku/sonnet/opus) showing node counts
- **Cost tracker**: running $ total based on tier × token estimates
- **ETA**: simple moving average of nodes/minute × remaining

### Build & Serve

```bash
# Dev
cd gui && npm run dev        # Vite dev server with API proxy to :8000

# Prod
cd gui && npm run build      # outputs to gui/dist/
# FastAPI serves gui/dist/ at /
```

`oxidant serve` command: starts FastAPI (uvicorn), which serves the built GUI and runs Phase B on demand.

---

## Open Questions (resolved)

| Question | Answer |
|----------|--------|
| Process model | Option A: single process, asyncio |
| Checkpointer | SqliteSaver (replaces MemorySaver) |
| Frontend stack | Vue 3 + Vite + Pinia |
| review_mode storage | oxidant.config.json, read into state at graph init |
| Supervisor fires when | At escalation boundary (tier exhausted), not on every retry |
| LangGraph Studio | Stays as dev/debug tool alongside this |
