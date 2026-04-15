# oxidant

An agentic harness for automated TypeScript-to-Rust translation, powered by [LangGraph](https://github.com/langchain-ai/langgraph).

## What It Does

Oxidant drives a multi-agent pipeline that reads TypeScript source, understands its structure, and produces idiomatic Rust. The first target corpus is **msagl-js** (Microsoft's Automatic Graph Layout library).

## Architecture

```
TS source
    │
    ▼
[Chunker] — splits source into translatable units
    │
    ▼
[Analyzer] — extracts types, dependencies, semantics
    │
    ▼
[Translator] — LLM agent: TS → Rust (idiomatic)
    │
    ▼
[Validator] — rustc / cargo check / unit tests
    │
    ▼
[Patcher] — fixes errors, retries with context
    │
    ▼
Rust output
```

## First Target: msagl-js

[msagl-js](https://github.com/microsoft/msagljs) is Microsoft's graph layout engine in TypeScript (~50k lines). Converting it to Rust is the initial benchmark for the harness.

## Getting Started

```bash
# Install dependencies (requires uv)
uv sync

# Run on a single file
oxidant translate path/to/file.ts --out path/to/output/

# Run on msagl-js corpus
oxidant translate --corpus msagljs
```

## Project Structure

```
oxidant/
├── oxidant/           # Core package
│   ├── agents/        # LangGraph agent nodes
│   ├── graph/         # LangGraph graph definitions
│   ├── models/        # Pydantic state models
│   ├── corpus/        # Corpus loaders (msagljs, ...)
│   └── cli.py         # Typer CLI entry point
├── tests/
├── corpora/           # Source corpora (gitignored if large)
└── pyproject.toml
```

## License

MIT
