# Oxidant — Product Requirements Document

**Version:** 0.1 (First Pass)  
**Status:** Draft — agent review requested  
**Date:** April 2026  

---

## Purpose of This Document

This PRD describes the Oxidant system — an agentic harness for converting TypeScript codebases to idiomatic Rust. It is written for a Claude Code agent being spun up fresh on this project. The agent should read this document in full, identify any requirements that are underspecified, ambiguous, or in tension with each other, and raise those issues before proceeding to planning or implementation.

This document intentionally does not prescribe a build plan. The agent is expected to derive that plan after validating the requirements herein.

Two supporting research documents exist in this repository and should be consulted alongside this PRD:

- `RESEARCH_SUMMARY.md` — synthesizes the academic and open-source literature on LLM-assisted code translation, including lessons from ORBIT, His2Trans, SACTOR, EvoC2Rust, ENCRUST, and vjeux's Pokemon Showdown port
- `RESEARCH_ACADEMIC.md` — the detailed academic survey with citations

---

## 1. Project Overview

### 1.1 What Is Oxidant?

Oxidant is an agentic harness that takes a TypeScript codebase as input and produces an idiomatic, compiling, test-passing Rust codebase as output. It is not a traditional transpiler — it does not mechanically map TypeScript syntax to Rust syntax. Instead, it orchestrates a pipeline of AI agents, static analysis tools, and deterministic verification steps to perform a semantically faithful translation that respects Rust's ownership model, idiomatic patterns, and ecosystem conventions.

The harness controls agents — it does not replace them. The harness decides what to convert, in what order, with what context, using what model tier, and whether the output is acceptable. The agents (Claude Code instances) do the actual conversion work within the structure the harness imposes.

### 1.2 Why Does This Exist?

The TypeScript-to-Rust translation problem is unsolved at repository scale. No mature tool exists for it. The closest analogues are C-to-Rust systems (ORBIT, ENCRUST, SACTOR) which have demonstrated that agentic, AST-driven, dependency-ordered approaches substantially outperform naive file-by-file LLM prompting.

The primary motivation is the Tauri desktop application ecosystem. Developers who want to build lightweight native desktop applications using Tauri must write Rust. Many have existing TypeScript libraries they would like to bring to Rust. Doing this manually is extremely expensive and error-prone — the developer becomes the harness, manually tracking progress, managing context, and verifying output. Oxidant automates the harness role.

The secondary motivation is broader: TypeScript is the dominant language for serious JavaScript projects, and the Rust ecosystem has significant gaps that TypeScript has already filled. A reliable translation harness would allow high-quality TypeScript libraries to be made available in Rust without full manual rewrites.

### 1.3 Primary Test Case

The primary test case is **MSAGL-JS** (https://github.com/microsoft/msagljs) — Microsoft's JavaScript graph layout engine, a port of their C# MSAGL library. It is approximately 50,000 lines of TypeScript, organized as a monorepo with several subpackages. It has existing tests. It is a pure computation library with no DOM or browser dependencies in its core layout engine. It is OOP-heavy, has deep class hierarchies, and contains the bidirectional graph reference pattern (Node↔Edge) that is specifically hostile to Rust's ownership model.

MSAGL-JS was chosen because:
- It represents a real gap in the Rust ecosystem (no equivalent graph layout library exists)
- It is complex enough to stress test the harness on hard patterns
- It has tests that can be used for equivalence verification
- One of the project authors has already attempted a manual conversion and experienced the failure modes firsthand, providing ground truth about where agents cut corners

### 1.4 Success Criteria

A successful v1.0 of Oxidant on MSAGL-JS means:
1. `cargo build` passes on the output
2. All tests that pass in the TypeScript original also pass in the Rust output
3. No `unsafe` blocks except where explicitly approved by a human reviewer
4. No `todo!()` or `unimplemented!()` macros in any converted function
5. Clippy passes with no warnings at the `clippy::pedantic` level (or documented suppressions with rationale)
6. The Rust output is architecturally coherent — consistent naming conventions, consistent ownership strategy, consistent error handling patterns throughout

---

## 2. System Architecture Overview

### 2.1 High-Level Pipeline

Oxidant operates in two major phases plus a pre-phase:

```
Pre-Phase: Human Architectural Decisions
    ↓
Phase A: Analysis and Preparation (deterministic, no AI)
    ↓
Phase B: Translation (agentic, AI-driven)
    ↓
Phase C: Idiomatic Refinement (agentic, AI-driven)
    ↓
Phase D: Integration and Verification (deterministic + agentic)
```

These phases are sequential at the top level but Phase B's internal loop is highly iterative.

### 2.2 Pre-Phase: Human Architectural Decisions

Before any automated work begins, a human must make certain architectural decisions that the harness cannot make autonomously. These decisions are encoded into the project configuration and the idiom dictionary, and they govern all subsequent translation work.

For MSAGL-JS specifically, the critical decision is the **graph ownership strategy**: how to handle the bidirectional Node↔Edge reference pattern that permeates the library. The options are:

- **Arena allocation** (recommended for MSAGL): nodes and edges become integer indices into typed arenas (`slotmap` or `typed-arena` crate). This is the most performant and idiomatic Rust approach for graph data structures. It requires a globally-accessible arena context to be threaded through the codebase.
- **`Rc<RefCell<T>>`**: single-threaded reference counting with interior mutability. Simpler to generate automatically, correct but not performant, useful as a Phase A fallback.
- **`petgraph` internals**: use petgraph's node/edge index pattern as the foundation. Only appropriate if MSAGL's graph API maps cleanly to petgraph's.

This decision must be made before skeleton generation because it determines the struct definitions for `Node` and `Edge` throughout the entire codebase. The human records this decision in `oxidant.config.json` and it is injected into every relevant agent prompt.

### 2.3 Phase A: Analysis and Preparation

Phase A is entirely deterministic — no AI involvement. It produces all the structured inputs that Phase B requires.

**A1 — AST Extraction (TypeScript, ts-morph)**

A TypeScript script using ts-morph parses the entire source codebase and produces `conversion_manifest.json`. This manifest is the central data structure for the entire system. It contains every translatable unit (class, method, function, interface, enum, type alias) with:

- Unique node ID
- Source file and line range
- Full source text
- Resolved TypeScript type of all parameters and return values
- All types this node references (type dependency edges)
- All functions/methods this node calls (call graph edges)
- All functions/methods that call this node (reverse call edges)
- Cyclomatic complexity score
- Node kind (class definition, method, free function, interface, enum, etc.)
- Topological order index (derived from the unified dependency graph)
- BFS level (for parallelism grouping)
- Status: `NOT_STARTED`
- Tier: `null` (set in A3)
- Snippet path: `null` (set during Phase B)
- Idioms needed: `[]` (set in A2)
- Assembly index and kind (for file assembly ordering)

**A2 — Idiom Detection (TypeScript, ts-morph)**

A second TypeScript script scans the AST for patterns known to require special handling in TS→Rust translation. For each node in the manifest, it annotates `idioms_needed` with the specific patterns present in that node's source. Detected pattern categories include:

- Optional chaining (`?.`)
- Null/undefined duality
- Class inheritance relationships
- Interface-as-type-parameter patterns
- Mutable shared state (objects mutated after being passed to a function)
- Array method chains (map/filter/reduce/find/some/every)
- Closures that capture outer scope variables
- TypeScript union types
- Dynamic property access
- `Map<K,V>` and `Set<T>` usage
- Async/await and Promise patterns
- `number` type in arithmetic vs index contexts
- Discriminated union types (which map to Rust enums)
- Class fields initialized in constructor
- Static class members
- Generator functions

The idiom detection script also performs pattern extraction: where possible, it extracts the specific pattern text from the node (e.g., the exact optional chain expression) rather than just flagging the category. This extracted pattern, combined with a pre-computed Rust equivalent from the idiom dictionary, gets injected directly into the conversion prompt for that node.

**A3 — Idiom Dictionary Generation (single Opus call)**

After A2 produces `idiom_candidates.json` containing all detected patterns with examples from the actual codebase, a single Opus call generates the `idiom_dictionary.md`. This call provides:
- The complete list of detected pattern categories
- Concrete examples from the actual source code for each category
- The human architectural decisions from the pre-phase
- The target crate inventory (see A5)

The Opus call produces a structured markdown document mapping each pattern to its idiomatic Rust translation, with MSAGL-specific notes where the library's particular usage requires special treatment. A human reviews and edits this document before Phase B begins. The idiom dictionary is versioned and treated as a first-class artifact.

**A4 — Complexity Classification (Haiku pass)**

A cheap Haiku pass over every node in the manifest assigns each a translation tier:
- `haiku`: simple getters/setters, basic type definitions, pure arithmetic, straightforward data transformations with no complex patterns
- `sonnet`: moderate complexity, async conversions, medium-complexity algorithms, non-trivial ownership decisions
- `opus`: complex algorithms where a simpler incorrect version would be plausible, nodes with cyclic reference involvement, heavy generics, anything the classifier flags as requiring deep reasoning

The classifier uses the complexity score from A1, the idioms detected in A2, and the node kind. It outputs a JSON response per node: `{"tier": "haiku"|"sonnet"|"opus", "reason": "..."}`.

**A5 — Target Crate Inventory (human decision)**

A human reviews the MSAGL-JS dependency manifest and the idiom candidates to decide which Rust crates will be available to the translation agents. This list is recorded in `oxidant.config.json` and injected into every agent prompt. For MSAGL-JS the initial inventory is expected to include:

- `slotmap` or `typed-arena` — for arena-based graph node ownership (per pre-phase decision)
- `petgraph` — for graph algorithms (Floyd-Warshall, etc.) that MSAGL may delegate to
- `nalgebra` or `glam` — for geometric/linear algebra operations (Point, Vector, Matrix)
- `thiserror` — for error type definitions
- `itertools` — for iterator combinators that match TypeScript array method patterns
- `ordered-float` — for `f64` values that need to be used as map keys
- `serde` / `serde_json` — for any serialization present in MSAGL

**A6 — Skeleton Generation (deterministic script)**

A Python script reads the manifest and generates a complete, compilable Rust project skeleton. Every module exists. Every struct has its fields. Every trait has its method signatures. Every function has a `todo!("OXIDANT: not yet translated")` body. The skeleton must pass `cargo build` before Phase B begins.

Skeleton generation is the most mechanically complex part of Phase A. It requires:
- Mapping TypeScript class hierarchies to Rust struct+trait combinations (using the pre-phase and idiom dictionary decisions)
- Generating correct `use` declarations based on the type dependency graph
- Generating `Cargo.toml` with the crate inventory from A5
- Generating `mod.rs` files reflecting the module structure
- Ensuring the generated code compiles — this may require several iterations

The skeleton uses `todo!()` macros with a specific marker string (`OXIDANT:`) so that Phase B can find unconverted functions by grepping the codebase. The number of remaining `todo!()` macros is the primary progress metric throughout Phase B.

---

## 3. Phase B: Translation

Phase B is the core translation loop. It is orchestrated by a LangGraph state graph running in Python. It consumes the manifest and the skeleton, converts nodes one at a time in topological order, writes snippets to disk, and updates the manifest after each successful conversion.

### 3.1 Technology Stack

- **Orchestration**: LangGraph (Python) — chosen for durable execution with checkpointing, conditional edges, persistent state, and composable subgraphs
- **Agent**: Claude Code CLI invoked as a subprocess — chosen to run under the user's existing Max subscription rather than pay-per-token API billing
- **AST extraction**: ts-morph (TypeScript) — chosen for full TypeScript compiler type resolution including cross-file inference
- **TypeScript runner**: `tsx` — runs Phase A TypeScript scripts directly without a compilation step (`npm install -D tsx`; invoked as `tsx extract_ast.ts`)
- **Verification**: `cargo check` and `cargo clippy` (Rust toolchain) run against the skeleton project
- **Progress tracking**: `conversion_manifest.json` — the single source of truth, updated atomically after each successful conversion

### 3.2 Subprocess Invocation of Claude Code

Claude Code is invoked as a subprocess via the shell, not via the Python SDK. This is because the Python SDK currently requires an API key and does not support Max subscription billing. The correct invocation strips `ANTHROPIC_API_KEY` from the environment to force subscription authentication:

```python
import subprocess
import os

def invoke_claude_code(prompt: str, cwd: str) -> str:
    env = os.environ.copy()
    # Critical: remove API key to force Max subscription auth
    env.pop("ANTHROPIC_API_KEY", None)
    
    result = subprocess.run(
        ["claude", "--print", "--output-format", "json", prompt],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300
    )
    return result.stdout
```

**Warning**: if `ANTHROPIC_API_KEY` is present in the environment, Claude Code will bill to the API account rather than the Max subscription. This has caused accidental charges of $1,800+ for other users. The harness must always strip this key before invoking Claude Code.

### 3.3 The Translation Loop (LangGraph State Graph)

The LangGraph graph has the following nodes:

**`pick_next_node`**
Reads the manifest and selects the next node eligible for conversion. A node is eligible when:
- Its status is `NOT_STARTED`
- All nodes it depends on (both type dependencies and call dependencies) have status `CONVERTED`

If no eligible node exists and there are still `NOT_STARTED` nodes, those nodes are blocked (circular dependency or all dependencies are themselves blocked). The graph surfaces these to the human review queue and halts.

If no `NOT_STARTED` nodes remain, the graph transitions to the assembly phase.

**`assemble_context`**
For the selected node, assembles the complete prompt context:
- The node's TypeScript source text
- The already-converted Rust snippets for everything this node calls (from disk, by snippet path in manifest)
- The TypeScript signatures of everything that calls this node (for awareness of how it's used)
- The specific idiom dictionary entries for the idioms flagged in this node's `idioms_needed`
- The human architectural decisions relevant to this node
- The available crate inventory
- The conversion tier for this node
- Any previous failed attempts at this node (for retry context)

**`invoke_agent`**
Constructs the conversion prompt and invokes Claude Code as a subprocess. The prompt instructs the agent to:
- Convert only this specific function/method/type — not surrounding code
- Produce a Rust snippet that can stand alone as a file
- Follow the idiom translations provided exactly
- Not simplify, optimize, or restructure the logic — translate it faithfully
- Not use `todo!()`, `unimplemented!()`, or `panic!()`
- Match every conditional branch present in the TypeScript source
- Use only crates from the approved inventory

The output is written to `snippets/<module>/<node_id>.rs`.

**`verify`**
Runs a layered verification sequence. Each check is cheaper than the next:

1. **Stub detector**: grep for `todo!`, `unimplemented!`, empty function bodies. Instant failure if found.
2. **Branch parity check**: count if/match arms, loop constructs, and early returns in the TypeScript source vs the Rust output. Flag if Rust has significantly fewer.
3. **`cargo check`**: the converted snippet is written into the skeleton project at the correct module path, replacing the `todo!()` stub for that function. `cargo check` then runs on the whole skeleton project. Because every other unconverted function remains a `todo!()` stub, the check meaningfully exercises the new code's type interactions with the rest of the skeleton, catching boundary mismatches immediately. Compile errors go back to the agent with the error message.
4. **Discriminator check**: a verification step that checks the output for simplification, missing branches, and hallucinated APIs. Returns `PASS` or `FAIL` with specific issues. Implementation (separate model call vs self-review step) is TBD during planning — see Open Question 7.

**`handle_verify_result`**
Conditional edge:
- All checks pass → `update_manifest` with status `CONVERTED`
- Stub/branch/discriminator failure → increment attempt counter; if under `MAX_ATTEMPTS[tier]`, back to `invoke_agent` with failure context; if at limit, escalate tier and retry; if at Opus limit, send to `human_review_queue`
- `cargo check` failure → back to `invoke_agent` with compiler error appended to context
- Escalation: `haiku` → `sonnet` after 3 failures; `sonnet` → `opus` after 4 failures; `opus` → human queue after 5 failures

**`update_manifest`**
Atomically updates the node's status to `CONVERTED` and snippet path in the manifest JSON. Checks if all sibling nodes for this node's source file are now `CONVERTED` — if so, triggers file assembly for that file.

**`assemble_file`**
When all nodes belonging to a source file are converted, assembles them into a single `.rs` file in the correct order (structs before traits before trait impls before inherent impls before free functions). Writes to the `src/` directory of the Rust project, replacing the skeleton's `todo!()` version. Runs `cargo check` on the assembled file.

**`human_review_queue`**
Nodes that have exhausted all retry attempts are written to `review_queue.json` with:
- The node ID and source
- All failed Rust attempts
- All error messages
- The specific failure mode (stub detected / branch parity / discriminator / cargo check)

The harness does not halt for these nodes — it continues converting other eligible nodes and surfaces the queue at the end of each run.

### 3.4 Parallelism

Nodes within the same BFS level of the dependency graph are independent of each other and can be converted in parallel. The harness spawns multiple Claude Code subprocess calls simultaneously for nodes at the same level. The degree of parallelism is configurable but should respect Claude Code's rate limits under the Max subscription.

---

## 4. Phase C: Idiomatic Refinement

After Phase B completes (all nodes converted or in the human review queue), Phase C runs a second pass focused on idiomaticity rather than correctness.

Phase C runs `cargo clippy --all-targets -- -W clippy::pedantic` and categorizes warnings by type:
- **Mechanical fixes**: redundant clones, unnecessary `mut`, simple iterator improvements — a Haiku agent fixes these automatically
- **Structural improvements**: opportunities to replace `Rc<RefCell<>>` with proper ownership, obvious arena allocation improvements — a Sonnet agent proposes changes with human approval required
- **Human decisions**: anything clippy flags that requires architectural judgment

Phase C does not change behavior — only style and efficiency. Every change in Phase C must pass the full test suite before being committed.

---

## 5. Phase D: Integration and Verification

### 5.1 Full Build Verification

After Phase C, a full `cargo build --release` runs. Errors at this stage are integration errors — mismatches at the boundaries between components that each compiled individually but conflict when linked. These are handled by a delta debugging strategy: binary search through recently assembled files to isolate the conflict, then re-translate the conflicting snippet with the integration error as additional context.

### 5.2 Equivalence Testing

The TypeScript test suite is ported to run against both the original TypeScript and the Rust output simultaneously, comparing outputs numerically. For MSAGL specifically, equivalence means:
- Node positions (x, y coordinates) match within floating-point epsilon
- Edge spline control points match within floating-point epsilon
- Graph topology (which nodes are connected to which) is identical

The test harness compiles the Rust library to WebAssembly via `wasm-pack` and runs it in Node.js alongside the original TypeScript, comparing outputs. This approach avoids the need to port the test suite to Rust while providing functional correctness verification.

### 5.3 Property-Based Testing

Beyond the existing MSAGL tests, a property-based test suite using `proptest` (Rust) is generated to check geometric invariants that should hold for any graph:
- Bounding boxes contain all their nodes
- Edge routes connect the correct source and target nodes
- Layout results are deterministic for the same input
- No coordinate values are NaN or infinite

---

## 6. Configuration

All project-specific settings live in `oxidant.config.json` at the root of the Oxidant workspace:

```json
{
  "source_repo": "../msagljs",
  "target_repo": "../msagl-rs",
  "source_language": "typescript",
  "target_language": "rust",
  "tsconfig": "../msagljs/tsconfig.json",
  
  "architectural_decisions": {
    "graph_ownership_strategy": "arena_slotmap",
    "error_handling": "thiserror"
  },
  
  "crate_inventory": [
    "slotmap",
    "petgraph", 
    "nalgebra",
    "thiserror",
    "itertools",
    "ordered-float",
    "serde",
    "serde_json"
  ],
  
  "model_tiers": {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6"
  },
  
  "max_attempts": {
    "haiku": 3,
    "sonnet": 4,
    "opus": 5
  },
  
  "parallelism": 4,
  
  "subscription_auth": true
}
```

---

## 7. Repository Structure

The Oxidant repository contains the harness code itself. It does not contain the source or target codebases — those are referenced by path in `oxidant.config.json`.

The phase names (A/B/C/D) are conceptual groupings, not directories. The code lives in a standard Python `src/` layout so it works correctly with pytest, pip install, and IDE tooling. Phase A TypeScript scripts live alongside the Python package.

```
oxidant/
  README.md
  oxidant.config.json             ← project configuration
  pyproject.toml
  package.json                    ← tsx + ts-morph dev dependencies
  
  docs/
    OXIDANT_PRD.md                ← this document
    RESEARCH_SUMMARY.md           ← literature review
    RESEARCH_ACADEMIC.md          ← detailed academic citations
  
  src/oxidant/                    ← Python package (harness)
    analysis/                     ← Phase A: Python analysis steps
      classify_tiers.py           ← Haiku tier classification
      generate_skeleton.py        ← Rust skeleton generator
    graph/                        ← Phase B: LangGraph state graph
      graph.py                    ← graph definition and wiring
      nodes.py                    ← individual node implementations
    agents/                       ← agent invocation and prompting
      invoke.py                   ← Claude Code subprocess invocation
      context.py                  ← prompt context assembly
    verification/                 ← Phase B verify step
      verify.py
    manifest/                     ← manifest read/write
      manifest.py
    assembly/                     ← file assembly from skeleton
      assemble.py
    refinement/                   ← Phase C: Clippy-driven refinement
      clippy_runner.py
      mechanical_fixes.py
      structural_improvements.py
    integration/                  ← Phase D: integration and equivalence
      integration_debug.py
      equivalence_test.js         ← Node.js WASM comparison harness
    models/                       ← Pydantic state models
    corpus/                       ← corpus loaders
    cli.py                        ← Typer CLI entry point
  
  phase_a_scripts/                ← Phase A TypeScript scripts (run via tsx)
    extract_ast.ts                ← ts-morph AST extractor → conversion_manifest.json
    detect_idioms.ts              ← idiom pattern scanner → idiom_candidates.json
  
  tests/
  
  idiom_dictionary.md             ← generated + human-reviewed idiom map
  idiom_candidates.json           ← raw output of detect_idioms.ts
  conversion_manifest.json        ← central state, updated throughout
  review_queue.json               ← nodes requiring human attention
  corpora/                        ← source repos (gitignored)
    msagljs/
```

---

## 8. Key Design Decisions and Rationale

### 8.1 Why skeleton-first?

The research literature (His2Trans, EvoC2Rust, Skel) consistently shows that skeleton-first approaches dramatically outperform node-by-node translation that builds up from nothing. The skeleton ensures:
- `cargo build` works from day one, providing continuous compiler feedback
- Agents always have correct type signatures for functions they depend on (from the skeleton)
- Integration errors surface early rather than only after all conversion is complete
- Progress is measurable as a count of remaining `todo!()` macros

### 8.2 Why topological order?

When converting a function, every function it calls has already been converted and its Rust snippet is available on disk. The agent can be shown the exact Rust signatures it needs to call, eliminating guesswork about what the API looks like. This is the single biggest driver of conversion quality in all comparable systems.

### 8.3 Why per-node snippets rather than per-file conversion?

Per-node granularity provides:
- Resumability: if the harness crashes, the manifest records exactly which nodes are done
- Verifiability: each snippet can be checked independently before being assembled
- Parallelism: nodes at the same BFS level can be converted simultaneously
- Isolation of failures: a difficult function doesn't block conversion of its siblings
- Precision of retry: only the failing node is retried, not the entire file

### 8.4 Why LangGraph rather than Archon?

Archon's YAML workflow model is designed for static, repeatable development workflows (fix a bug, build a feature). Oxidant's workflow is fundamentally dynamic — the number of steps, their order, and their routing depends entirely on the runtime structure of the dependency graph derived from the input codebase. LangGraph's graph model with conditional edges, persistent state, and durable execution maps directly onto this requirement. Archon would require extensive workarounds to express the topological ordering and conditional tier escalation logic.

### 8.5 Why Claude Code subprocess rather than the Python SDK?

The Claude Agent SDK (Python) currently requires API key authentication and does not support Max subscription billing. Using `claude --print` via subprocess with `ANTHROPIC_API_KEY` removed from the environment allows the harness to run under an existing Max subscription, which is substantially cheaper for a long-running conversion job than pay-per-token API billing.

### 8.6 Why two-phase translation (unidiomatic then idiomatic)?

Attempting to produce perfectly idiomatic Rust in a single pass is too much to ask of any single agent call. The SACTOR paper demonstrates that splitting translation into a correctness-first pass (Phase B, allowing `Rc<RefCell<>>`, `.clone()` everywhere) followed by an idiomaticity pass (Phase C, driven by Clippy) produces better results than trying to do both simultaneously. Phase B agents can focus entirely on semantic correctness; Phase C agents can focus entirely on Rust idioms.

---

## 9. Known Hard Patterns in MSAGL-JS

The following patterns are known from the research literature and from prior manual conversion attempts to be specifically difficult. The harness must handle each of these explicitly.

### 9.1 Bidirectional graph references (Node↔Edge)

MSAGL nodes reference their edges and edges reference their source/target nodes. This is the most fundamental Rust-hostile pattern in the library. The architectural decision (arena allocation) must be made in the pre-phase and encoded into the skeleton before any translation begins. Every agent prompt involving Node or Edge types must include the architectural decision and its rationale.

### 9.2 Deep class inheritance (Entity → GeometryObject → Node/Edge/Label)

TypeScript class inheritance has no direct Rust equivalent. The translation strategy (trait + struct composition) must be decided in the pre-phase and applied consistently. The skeleton generator handles the structural mapping; agents fill in the method implementations.

### 9.3 Mutable shared state during layout

Layout algorithms mutate node positions and edge routes while traversing the graph. Rust requires either single-ownership mutation or interior mutability. The Phase A idiom detection should flag every instance of this pattern, and the idiom dictionary should prescribe the consistent Rust approach.

### 9.4 The `number` type

TypeScript's `number` is a 64-bit float used for everything: coordinates, counts, indices, flags. The idiom scanner should detect the usage context of every `number` type in the codebase and annotate each with the appropriate Rust type: `f64` for coordinates and measurements, `usize` for array indices and counts, `i32` for signed counts.

### 9.5 "Improvement during translation"

LLM agents consistently attempt to refactor, optimize, or simplify code during translation rather than performing faithful conversion. This is documented by vjeux in the Pokemon Showdown port and appears in virtually every LLM translation study. The discriminator check in the verification layer specifically targets this failure mode. Prompts must explicitly instruct agents not to improve the code — only translate it.

---

## 10. What This Document Does Not Specify

The following are intentionally left to the agent's judgment during planning:

- The precise schema for `conversion_manifest.json` (the agent should propose this)
- The exact prompt templates for each tier (the agent should draft these)
- The specific ts-morph API calls for each idiom detector (the agent should implement these)
- The LangGraph graph code itself (the agent should write this)
- The test equivalence harness implementation details
- CI/CD configuration
- Whether Phase B and Phase C can overlap (an open question)
- Precise parallelism strategy within LangGraph

---

## 11. Open Questions for Agent Review

Before planning or implementation begins, the agent should evaluate whether the following questions have been adequately answered in this document, and flag any that need resolution:

1. Is the two-phase approach (unidiomatic Phase B + idiomatic Phase C) the right split, or should Phase B target idiomatic output directly with a longer retry budget?
2. Is `slotmap` or `typed-arena` the better choice for the graph ownership strategy, given MSAGL's access patterns?
3. Should the skeleton be generated from the TypeScript types (via ts-morph) or should it be written manually for the most critical types (Node, Edge, Graph)?
4. Is the WASM-based equivalence testing approach feasible for MSAGL's output types (graph coordinates, splines), or does it require a custom serialization format?
5. Are there TypeScript patterns in MSAGL-JS that the idiom detection categories in Section A2 do not cover?
6. Is `cargo check` after each individual snippet sufficient, or should each snippet be checked in the context of the partially-assembled file?
7. Should the discriminator check be a separate Haiku call or incorporated into the main agent prompt as a self-review step?
8. How should the harness handle TypeScript generics — these appear in MSAGL's geometry types and map to Rust generics, but the mapping is not always straightforward.
9. Is there a risk that the skeleton generation step is itself complex enough to require its own agentic assistance rather than being fully deterministic?
10. What is the fallback strategy if a significant portion of nodes end up in the human review queue — is there a point at which manual intervention should restructure the approach rather than continuing node-by-node?

---

## 12. References

- MSAGL-JS source: https://github.com/microsoft/msagljs
- ORBIT paper: https://arxiv.org/html/2604.12048v1
- His2Trans paper: https://arxiv.org/html/2603.02617v1
- ENCRUST paper: https://arxiv.org/html/2604.04527v1
- SACTOR paper: https://arxiv.org/html/2503.12511v3
- EvoC2Rust paper: https://arxiv.org/html/2508.04295v2
- LangGraph documentation: https://langchain-ai.github.io/langgraph/
- ts-morph documentation: https://ts-morph.com/
- Claude Code Max subscription auth: https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan
- Archon (considered and rejected): https://github.com/coleam00/archon

---

*This document is version 0.1. The agent reviewing it should propose amendments, flag ambiguities, and identify missing requirements before proceeding to produce a build plan.*
