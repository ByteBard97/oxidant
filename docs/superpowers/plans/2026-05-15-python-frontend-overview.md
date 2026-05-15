# Python→Rust Frontend — Overview Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Execute each task file in order; each task produces a passing commit before the next begins.

**Goal:** Extend Oxidant's Phase A analysis pipeline so `source_language: "python"` in `oxidant.config.json` routes to a Python AST extractor instead of the TypeScript one, enabling end-to-end Python→Rust translation on the flora-backend GIS SVG pipeline.

**Architecture:** Add a Python extractor script pair (`extract_ast_python.py` + `detect_idioms_python.py`) alongside the existing TypeScript scripts. Route Phase A dispatch in `cli.py` based on `source_language`. Add `map_python_type()` to the skeleton generator and thread a source-language branch regex through the verification pipeline. Update `_load_idiom_entries()` to pick the correct idiom dictionary file by language. Phases B, C, D, and the LangGraph graph are otherwise untouched.

**Tech Stack:** Python `ast` stdlib (no new deps), pytest, existing oxidant SQLite/LangGraph stack.

---

## Task Files (execute in order)

| # | File | What it builds |
|---|---|---|
| 1 | [t1-cli-dispatch.md](2026-05-15-python-frontend-t1-cli-dispatch.md) | `source_language` routing in `cli.py` |
| 2 | [t2-ast-extractor.md](2026-05-15-python-frontend-t2-ast-extractor.md) | `phase_a_scripts/extract_ast_python.py` |
| 3 | [t3-idiom-detector.md](2026-05-15-python-frontend-t3-idiom-detector.md) | `phase_a_scripts/detect_idioms_python.py` |
| 4 | [t4-type-mapper.md](2026-05-15-python-frontend-t4-type-mapper.md) | `map_python_type()` + skeleton Cargo.toml fix |
| 5 | [t5-prompt-wiring.md](2026-05-15-python-frontend-t5-prompt-wiring.md) | Parameterise prompt language + idiom loader |
| 6 | [t6-branch-parity.md](2026-05-15-python-frontend-t6-branch-parity.md) | Language-aware branch parity in `verify.py` |
| 7 | [t7-idiom-dict.md](2026-05-15-python-frontend-t7-idiom-dict.md) | `idiom_dictionary_python.md` |
| 8 | [t8-e2e-test.md](2026-05-15-python-frontend-t8-e2e-test.md) | End-to-end smoke test on `fit_text_to_cell` |

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| **Create** | `phase_a_scripts/extract_ast_python.py` | Walk Python source with `ast`, emit `conversion_manifest.json` |
| **Create** | `phase_a_scripts/detect_idioms_python.py` | Tag Python idioms on an existing manifest |
| **Create** | `idiom_dictionary_python.md` | Python→Rust idiom guidance injected into Phase B prompts (workspace root, same level as `idiom_dictionary.md`) |
| **Create** | `tests/test_extract_ast_python.py` | Unit tests for the Python extractor |
| **Create** | `tests/test_detect_idioms_python.py` | Unit tests for the Python idiom detector |
| **Create** | `tests/test_map_python_type.py` | Unit tests for `map_python_type()` |
| **Modify** | `src/oxidant/cli.py` | Dispatch Phase A by `source_language`; remove hard `tsconfig` requirement |
| **Modify** | `src/oxidant/analysis/generate_skeleton.py` | Add `map_python_type()`; skip Cargo.toml if already exists |
| **Modify** | `src/oxidant/agents/context.py` | Replace all hardcoded language strings; wire idiom dict by language |
| **Modify** | `src/oxidant/verification/verify.py` | Accept source-language branch regex; rename ambiguous constant |
| **Modify** | `src/oxidant/graph/nodes.py` | Pass source branch regex from config into `verify_snippet` |

---

## Known Out-of-Scope (deferred)

- Phase B run against real flora-backend corpus (manual step, requires Claude API)
- `supervisor_node()` hint text still says "TypeScript-to-Rust" — prose only, no correctness impact
- **Python class field extraction:** the skeleton generator parses TS field syntax; Python class structs will emit `_placeholder: ()`. Before running Phase A on flora-backend, grep the corpus for `@dataclass` and `TypedDict` usage. If widespread, plan a follow-up to mine `__init__` self-assignments and dataclass fields in the extractor
- **Nested generic type splitting** (e.g. `dict[tuple[int,int], str]`): verify against the corpus before fixing

---

## Self-Review Summary

All issues from the Kimi + Advisor pre-implementation review have been addressed:
- All 6 hardcoded "TypeScript" strings in `_PROMPT_TEMPLATE` replaced
- `_load_idiom_entries` wired to correct dict by `source_language`
- `sys.executable` used (not bare `"python"`) in subprocess calls
- Branch parity test is a real assertion (not a tautology)
- `_BRANCH_MIN_TS_COUNT` renamed to `_BRANCH_MIN_SRC_COUNT`
- Language display name uses a lookup dict (`_LANG_DISPLAY`), not `.title()`
- Directory skip filter uses exact set membership, not fragile `startswith`
- `map_python_type` uses module-level `re`, no inner import
