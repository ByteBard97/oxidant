# oxidant

An agentic harness for automated TypeScript-to-Rust translation, powered by [LangGraph](https://github.com/langchain-ai/langgraph).

**[Documentation & Architecture →](https://bytebard97.github.io/oxidant/)**

## What It Does

Oxidant drives a four-phase pipeline that reads a TypeScript codebase, analyzes its structure, and produces idiomatic Rust — one function at a time, in dependency order, verified at every step.

## Pipeline

| Phase | What it does |
|-------|-------------|
| **A — Analysis** | ts-morph AST extraction, idiom detection, topological sort, tier classification, Rust skeleton generation |
| **B — Translation** | LangGraph loop: pick → prompt → `claude --print` → verify → retry/escalate → commit |
| **C — Refinement** | `cargo clippy` auto-fix for mechanical warnings; structural warnings surfaced for review |
| **D — Integration** | `cargo build --release`, error parsing, manifest intersection, retranslation hints |

```mermaid
flowchart LR

    subgraph phaseA ["Phase A — Analysis"]
        direction TB
        tsFiles[".ts source files"]
        astExtract["ts-morph AST<br>extraction"]
        idiomDetect["idiom detection<br>& classification"]
        topoSort["topological sort<br>by dependency"]
        skeleton["Rust skeleton<br>generation"]
        tsFiles --> astExtract --> idiomDetect --> topoSort --> skeleton
    end

    manifest[("conversion_manifest.json<br>+ Rust skeletons")]

    subgraph phaseB ["Phase B — Translation"]
        direction TB
        pickNode["pick next node<br>(topo order)"]
        buildCtx["build context<br>TS src + deps + idioms"]
        claudeCall["claude --print<br>(haiku → sonnet → opus)"]
        verifySnip["verify snippet<br>stub · branch · cargo check"]
        pickNode --> buildCtx --> claudeCall --> verifySnip
        verifySnip -->|"fail: retry / escalate"| buildCtx
    end

    snippets[/"snippets/*.rs<br>(per-node Rust)"/]

    subgraph phaseC ["Phase C — Refinement"]
        direction TB
        clippyFix["cargo clippy --fix<br>mechanical auto-fix"]
        clippyReview["structural warnings<br>surfaced for review"]
        clippyFix --> clippyReview
    end

    subgraph phaseD ["Phase D — Integration"]
        direction TB
        cargoBuild["cargo build --release"]
        errorParse["error parsing +<br>retranslation hints"]
        cargoBuild --> errorParse
    end

    phaseA ==> manifest
    manifest ==> phaseB
    phaseB ==> snippets
    snippets ==> phaseC
    phaseC ==> phaseD

    classDef io fill:#fed7aa,stroke:#c2410c,color:#374151
    classDef ai fill:#ddd6fe,stroke:#6d28d9,color:#374151
    classDef success fill:#a7f3d0,stroke:#047857,color:#374151

    class manifest,snippets io
    class claudeCall ai
    class verifySnip success
```

## Quick Start

```bash
# Install (requires uv)
uv sync

# Full Phase A: extract AST, detect idioms, sort, classify, generate skeleton
oxidant phase-a --heuristic-tiers

# Phase B: translate all nodes in topological order
oxidant phase-b

# Smoke test (translate first 3 nodes only)
oxidant phase-b --max-nodes 3

# Phase C: Clippy refinement
oxidant phase-c

# Phase D: full build verification
oxidant phase-d
```

## Project Structure

```
oxidant/
├── src/oxidant/
│   ├── agents/          # Prompt construction (context.py) and Claude invocation
│   ├── analysis/        # Tier classification, skeleton generation
│   ├── assembly/        # Module assembly from converted snippets
│   ├── graph/           # LangGraph StateGraph (nodes.py, graph.py, state.py)
│   ├── integration/     # Phase D — full build error isolation
│   ├── models/          # Manifest schema (Pydantic)
│   ├── refinement/      # Phase C — Clippy auto-fix
│   ├── verification/    # Three-layer snippet verification
│   └── cli.py           # Typer CLI entry point
├── phase_a_scripts/     # ts-morph TypeScript scripts (A1 AST, A2 idioms)
├── snippets/            # Per-node .rs snippets output by Phase B
├── docs/                # GitHub Pages site
├── idiom_dictionary.md  # TS→Rust idiom guidance injected into prompts
└── oxidant.config.json  # Paths, model tiers, target repo config
```

## How Translation Works

Every translatable unit in the TypeScript codebase — class, method, function, interface, enum — becomes a node in `conversion_manifest.json`. Nodes are processed in topological order: by the time a node is translated, all its dependencies are already in Rust.

For each node, Phase B:
1. Assembles a prompt with the TS source, Rust skeleton signature, dependency snippets, and relevant idiom guidance
2. Calls `claude --print` as a subprocess (subscription auth — no API key needed)
3. Verifies the snippet: stub check → branch parity → `cargo check`
4. Retries with error context, escalating haiku → sonnet → opus if needed
5. Marks the node `CONVERTED` or queues it for human review

```mermaid
stateDiagram-v2
    direction LR

    [*] --> pick_next_node

    state "pick_next_node<br>find next PENDING node" as pick_next_node
    state "build_context<br>TS src + deps + idiom hints" as build_context
    state "invoke_agent<br>claude --print (current tier)" as invoke_agent
    state "verify<br>stub · branch parity · cargo check" as verify
    state "retry_node<br>same tier, +error context" as retry_node
    state "escalate_node<br>haiku → sonnet → opus" as escalate_node
    state "update_manifest<br>mark CONVERTED, save snippet" as update_manifest
    state "queue_for_review<br>mark NEEDS_REVIEW" as queue_for_review

    pick_next_node --> build_context : nodes remain
    pick_next_node --> [*] : all done

    build_context --> invoke_agent
    invoke_agent --> verify

    verify --> update_manifest : PASS
    verify --> retry_node : fail, attempts < 3
    verify --> escalate_node : fail, attempts = 3
    verify --> queue_for_review : fail, already at opus

    retry_node --> build_context
    escalate_node --> build_context

    update_manifest --> pick_next_node
    queue_for_review --> pick_next_node

    pick_next_node:::primary
    invoke_agent:::ai
    verify:::decision
    update_manifest:::success
    queue_for_review:::error
    retry_node:::trigger
    escalate_node:::trigger

    classDef primary fill:#3b82f6,stroke:#1e3a5f,color:#ffffff
    classDef ai fill:#ddd6fe,stroke:#6d28d9,color:#374151
    classDef decision fill:#fef3c7,stroke:#b45309,color:#374151
    classDef success fill:#a7f3d0,stroke:#047857,color:#374151
    classDef error fill:#fecaca,stroke:#b91c1c,color:#374151
    classDef trigger fill:#fed7aa,stroke:#c2410c,color:#374151
```

## License

MIT
