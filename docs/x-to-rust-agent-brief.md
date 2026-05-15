# Agent Brief: Extend Oxidant to X→Rust

## What Oxidant is today

Oxidant is a LangGraph-based agentic pipeline that translates TypeScript codebases to
idiomatic Rust — one function at a time, in dependency order, with `cargo check`
verification at every step. The key insight is that the *verification loop* (not
the LLM) is what prevents lazy rewrites: a translated function must compile before
the pipeline moves on.

Codebase: `/Users/ceres/Desktop/SignalCanvas/oxidant/`

The pipeline has four phases:

| Phase | What it does | Key file |
|---|---|---|
| **A — Analysis** | Extract AST, detect idioms, topological sort, generate Rust skeleton with `todo!()` stubs | `phase_a_scripts/extract_ast.ts`, `phase_a_scripts/detect_idioms.ts`, `src/oxidant/analysis/generate_skeleton.py` |
| **B — Translation** | LangGraph loop: pick node → build context → call Claude → verify with `cargo check` → retry/escalate | `src/oxidant/agents/context.py`, `src/oxidant/agents/invoke.py` |
| **C — Refinement** | `cargo clippy --fix` mechanical cleanup | `src/oxidant/refinement/phase_c.py`, `src/oxidant/refinement/clippy_runner.py` |
| **D — Integration** | `cargo build --release`, parse errors, generate retranslation hints | `src/oxidant/integration/integration_debug.py` |

## The problem with the current design

Phase A is TypeScript-only. It uses:
- `phase_a_scripts/extract_ast.ts` — ts-morph to walk the TypeScript AST
- `phase_a_scripts/detect_idioms.ts` — ts-morph to classify TS-specific patterns
- `src/oxidant/analysis/generate_skeleton.py` — maps TS types to Rust types (hardcoded `_PRIMITIVES` and `_WEB_TYPES` dicts)
- `src/oxidant/agents/context.py` — prompt template hardcodes "TypeScript" and "msagl-js"

Phases B, C, D are already language-agnostic — they just call Claude and run `cargo`.

## What we want

Make `source_language` in `oxidant.config.json` a real routing key. When set to
`"python"`, `"go"`, `"cpp"`, etc., the pipeline should use the appropriate AST
extractor and type map. The translation prompt tells Claude what language it's
translating from; everything else (cargo check loop, topological sort, retry logic)
stays identical.

The architecture already anticipates this — `source_language` exists in the config
but is unused. The goal is to honour it.

## Immediate target: Python → Rust

The first use case driving this work is translating the flora-backend Django/Python
GIS rendering pipeline into Rust for the flora-studio Tauri app. The Python source
files are at `/Users/ceres/Desktop/flora/flora-backend/src/gis/pipeline/svg/` and
the target Rust crate is at `/Users/ceres/Desktop/flora/flora-studio/src-tauri/`.

The Python code has full type annotations (PEP 484 style: `float`, `int`, `str`,
`List[str]`, `Dict[str, Any]`, `TypedDict`, etc.) which makes Rust type inference
much easier than untyped Python would be.

## What needs to change

### 1. Replace Phase A's AST extraction with a language-agnostic dispatch

Current flow:
```
oxidant phase-a
  → runs extract_ast.ts via ts-morph (TypeScript only)
  → runs detect_idioms.ts via ts-morph (TypeScript only)
  → generates conversion_manifest.json
```

Target flow:
```
oxidant phase-a
  → reads source_language from config
  → dispatches to the right extractor:
      "typescript" → existing extract_ast.ts + detect_idioms.ts (unchanged)
      "python"     → new extract_ast_python.py + detect_idioms_python.py
      "go"         → new extract_ast_go.py (future)
      ...
  → generates conversion_manifest.json (same schema, unchanged)
```

### 2. Python AST extractor (`phase_a_scripts/extract_ast_python.py`)

Replaces `extract_ast.ts` for Python source. Should produce a
`conversion_manifest.json` with the same schema as the TypeScript extractor.

Use Python's built-in `ast` module (stdlib, no extra deps) or `libcst` if you need
concrete syntax (comments, formatting). `ast` is sufficient for function extraction.

What to extract per function/class:
- **node_id**: `{file_slug}__{function_name}` (same convention as TS extractor)
- **source_path**: path to the `.py` file
- **line_start / line_end**: `node.lineno` / `node.end_lineno`
- **kind**: `"function"` | `"class"` | `"constant"`
- **dependencies**: names of other functions/classes called within the body
  (walk the AST for `ast.Call` nodes, resolve to node_ids where possible)
- **signature**: Python type-annotated signature as a string (e.g. `"def render_title_block(buf: str, lc: LayoutCalc, params: TitleBlockParams) -> None"`)
- **complexity**: cyclomatic complexity (count `If`, `For`, `While`, `Try`, `With`,
  boolean operators — same approach as the TS extractor)

### 3. Python idiom detector (`phase_a_scripts/detect_idioms_python.py`)

Replaces `detect_idioms.ts`. Walk the Python AST and tag each node with idioms
it uses. Python-specific idioms that require Rust thought:

| Python pattern | Rust consideration |
|---|---|
| List comprehensions | `.iter().filter().map().collect()` |
| `Optional[T]` / `T \| None` | `Option<T>` |
| `dict` with string keys | `HashMap<String, V>` or a struct |
| `dataclass` / `TypedDict` | `#[derive(Debug, Clone)] struct` |
| `@property` | getter method on `impl` |
| `*args` / `**kwargs` | usually a `Vec<T>` or `HashMap` |
| `with` statement | RAII — struct `Drop` or scoped block |
| Generator functions (`yield`) | `Iterator` impl |
| Multiple return values (tuple) | tuple or named struct |
| `f"..."` format strings | `format!("...")` |
| `None` checks | `if let Some(x) = ...` |
| `isinstance` checks | usually `match` on enum variants |
| `svgwrite.Drawing` / DOM-like objects | string buffer (`String`/`Vec<u8>`) |

### 4. Type map for Python → Rust (`generate_skeleton.py` or new file)

Add a `_PYTHON_PRIMITIVES` dict alongside the existing `_PRIMITIVES` (TS) dict:

```python
_PYTHON_PRIMITIVES: dict[str, str] = {
    "int": "i64",
    "float": "f64",
    "str": "String",
    "bool": "bool",
    "bytes": "Vec<u8>",
    "None": "()",
    "Any": "serde_json::Value",
    "Dict": "std::collections::HashMap",
    "List": "Vec",
    "Tuple": "(",  # partial — needs element types
    "Optional": "Option",
    "Set": "std::collections::HashSet",
    "Union": "",  # needs enum or manual handling
}
```

The skeleton generator should route to the right primitive map based on
`config.source_language`.

### 5. Update the translation prompt (`src/oxidant/agents/context.py`)

The prompt currently hardcodes TypeScript. Replace with a template that reads
`source_language` from config:

```python
# Current (hardcoded):
"You are converting one TypeScript function to Rust as part of porting msagl-js."

# Target (parameterised):
f"You are converting one {config.source_language.title()} function to Rust."
```

Also update the "Files" section header from `## TypeScript Source` to
`## {source_language.title()} Source`.

The rest of the prompt — cargo check instructions, skeleton path, dependency
context — needs no changes.

### 6. Add `source_language` routing in `cli.py`

In `phase-a` command handling, after loading config:

```python
if config.source_language == "typescript":
    run_ts_extractor(config)   # existing path
elif config.source_language == "python":
    run_python_extractor(config)  # new
else:
    raise ValueError(f"Unsupported source_language: {config.source_language}")
```

### 7. Update `oxidant.config.json` schema (`src/oxidant/models/manifest.py`)

`source_language` already exists in the JSON config. Make sure the Pydantic/dataclass
model for config exposes it and passes it through to both Phase A (extractor choice)
and Phase B (prompt text).

## What does NOT need to change

- `src/oxidant/graph/` — dependency graph, topological sort: language-agnostic ✓
- `src/oxidant/verification/verify.py` — `cargo check` verification: language-agnostic ✓
- `src/oxidant/refinement/` — clippy runner: language-agnostic ✓
- `src/oxidant/integration/` — cargo build + error parsing: language-agnostic ✓
- `src/oxidant/models/db.py` — SQLite checkpoint storage: language-agnostic ✓
- `src/oxidant/serve/` — web UI / SSE event stream: language-agnostic ✓
- `src/oxidant/assembly/assemble.py` — final Rust file assembly: language-agnostic ✓
- The `conversion_manifest.json` schema — must stay identical so Phases B-D work ✓

## Python-specific idiom dictionary

Create `docs/idiom_dictionary_python.md` (parallel to `idiom_dictionary.md` for TS).
This file is injected into Phase B prompts as context. For the flora-backend
translation specifically, include guidance on:

- `svgwrite` → string buffer (`buf: &mut String`, `buf.push_str(...)`)
- `PIL.Image` rotation → the `image` crate
- `numpy` array ops → plain Rust iterators or `ndarray`
- Python f-strings with format specs → `format!("{:.2}", x)`
- `@dataclass` fields with defaults → Rust struct with `Default` impl
- `TypedDict` → Rust struct (not HashMap)
- `**kwargs` patterns in SVG functions → named struct param

## Suggested implementation order

1. `phase_a_scripts/extract_ast_python.py` — get manifest generation working for a
   single small Python file, verify the schema matches what Phase B expects
2. `phase_a_scripts/detect_idioms_python.py` — idiom tagging
3. Routing in `cli.py` + type map in `generate_skeleton.py`
4. Prompt parameterisation in `agents/context.py`
5. Test end-to-end on a small self-contained Python file (e.g., a single utility
   function with type annotations)
6. Run on the flora-backend GIS files

## Test target (small, self-contained)

Use this Python function as the first end-to-end test — it has type annotations,
uses no external deps beyond stdlib, and has a clear Rust equivalent:

```python
# from flora-backend/src/gis/pipeline/svg/title_block.py

def fit_text_to_cell(
    text: str,
    max_width: float,
    max_height: float,
    base_font_size: float = 10,
    min_font_size: float = 7,
    chars_per_px: float = 0.165,
) -> tuple[list[str], float]:
    """Fit text into a cell by word wrapping and shrinking font if needed."""
    if not text:
        return ([""], base_font_size)
    font_size = base_font_size
    while font_size >= min_font_size:
        scale_factor = font_size / 10.0
        chars_per_line = int(max_width * chars_per_px / scale_factor)
        if chars_per_line < 3:
            chars_per_line = 3
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip() if current_line else word
            if len(test_line) <= chars_per_line:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        line_height = font_size * 1.2
        total_height = len(lines) * line_height
        if total_height <= max_height:
            return (lines, font_size)
        font_size -= 1
    return (lines[:int(max_height / (min_font_size * 1.2))], min_font_size)
```

The Rust equivalent should be in `title_block.rs` as `fit_text_to_cell`, pass
`cargo check`, and produce identical output to the Python for the same inputs.
Verify with a `#[test]`.

## Key files to read before starting

```
oxidant/
├── oxidant.config.json                     ← source_language field
├── phase_a_scripts/
│   ├── extract_ast.ts                      ← REPLACE for non-TS languages
│   └── detect_idioms.ts                    ← REPLACE for non-TS languages
├── src/oxidant/
│   ├── cli.py                              ← add source_language routing
│   ├── analysis/
│   │   ├── generate_skeleton.py            ← add Python type map
│   │   └── classify_tiers.py              ← read for tier logic
│   ├── agents/
│   │   ├── context.py                      ← update prompt template
│   │   └── invoke.py                       ← LangGraph node — no changes
│   ├── models/
│   │   └── manifest.py                     ← ConversionNode schema
│   └── verification/
│       └── verify.py                       ← cargo check — no changes
└── idiom_dictionary.md                     ← reference for format of new Python dict
```
