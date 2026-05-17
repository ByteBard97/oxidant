# Language Frontends

Oxidant's source language is a **plugin**. A frontend is a pair of scripts that together implement Phase A1 (AST extraction) and A2 (idiom detection) for a specific source language. Everything from Phase A3 onward — topological sort, tier classification, skeleton generation, and the entire Phase B/C/D pipeline — is language-agnostic.

## Selecting a frontend

Set `"source_language"` in your config file:

```json
{
  "source_language": "typescript",
  "source_root": "path/to/ts/project",
  ...
}
```

or

```json
{
  "source_language": "python",
  "source_root": "path/to/python/package",
  ...
}
```

Oxidant dispatches Phase A1 and A2 to the appropriate scripts automatically.

---

## Shipped frontends

### TypeScript

| Script | What it does |
|--------|-------------|
| `phase_a_scripts/extract_ast.ts` | ts-morph AST extraction with full cross-file type resolution |
| `phase_a_scripts/detect_idioms.ts` | Detects 14 TS→Rust translation patterns |

**Best for:** TypeScript codebases with class hierarchies, interfaces, generics, and DOM/Web API usage.

**Tested on:** msagl-js (~4,800 functions, Microsoft graph layout engine)

### Python

| Script | What it does |
|--------|-------------|
| `phase_a_scripts/extract_ast_python.py` | stdlib `ast`-based extraction; handles classes, methods, free functions, dataclasses |
| `phase_a_scripts/detect_idioms_python.py` | Detects Python-specific patterns: svgwrite buffers, pandas DataFrames, shapely geometry, Callable parameters |

**Best for:** Python packages with clear function boundaries and typed signatures.

**Tested on:** a private GIS map rendering pipeline (~90 functions)

---

## Writing a new frontend

A frontend must produce a manifest JSON that matches the schema consumed by Phase A3+. The required fields per node:

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | string | Unique identifier (e.g. `module__ClassName__method_name`) |
| `source_file` | string | Relative path to source file |
| `kind` | string | `class`, `method`, `free_function`, `constructor`, `interface`, `enum`, `type_alias` |
| `source_text` | string | Full source text of the node |
| `dependencies` | string[] | `node_id`s this node depends on |
| `idioms_needed` | string[] | Detected idiom tags (may be empty) |
| `complexity` | int | Cyclomatic complexity estimate |
| `line_start` / `line_end` | int | Source line range |

Place your scripts in `phase_a_scripts/` and add a dispatch branch in `cli.py` under the `phase-a` command for your new `source_language` value.
