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
{supervisor_section}\
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
    supervisor_hint: str | None = None,
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
