"""Assemble the conversion prompt for a single manifest node.

The prompt includes: TypeScript source, Rust signature from skeleton,
converted dependency snippets, idiom dictionary entries, and retry context.

Progressive Context Disclosure levels:
  Level 1 (always): Full Rust snippets for direct call+type deps
  Level 2 (always): Truncated snippets for transitive (2-hop) deps
  JIT Unfurl (retry only): Full snippets for modules named in cargo errors
"""
from __future__ import annotations

import re
from pathlib import Path

from oxidant.models.manifest import ConversionNode, Manifest

_PROMPT_TEMPLATE = """\
You are converting one TypeScript function to Rust as part of porting msagl-js.

## Your job
1. Read the TypeScript source file to understand the function and its context
2. Read the Rust skeleton file to understand available types and fields
3. Write the Rust function body and insert it into the skeleton using Edit
4. Run cargo check to verify it compiles: use Bash with `cd {rs_skeleton_dir} && cargo check`
5. Fix any errors and repeat until cargo check passes

## Files
- TypeScript source: {ts_source_path} (lines {line_start}--{line_end})
- Rust skeleton: {rs_skeleton_path}
- Cargo check directory: {rs_skeleton_dir}
- Function to implement: `{node_id}`
- The skeleton has a `todo!("OXIDANT: not yet translated \u2014 {node_id}")` marker \
where your implementation goes

## TypeScript Source
```typescript
{source_text}
```

## Rules
- Implement ONLY the function body for `{node_id}` -- do not change anything else
- OUTPUT PURE ASCII ONLY. No backticks, no em-dashes, no curly quotes, \
no non-ASCII characters of any kind. They break compilation for every function in the file.
- Do NOT use todo!(), unimplemented!(), or panic!()
- Translate semantically faithfully -- match every branch in the TypeScript
- Use only approved crates: {crates}
- Do NOT simplify, optimize, or restructure

## Architectural Decisions
{arch_decisions}
{deps_section}\
{transitive_section}\
{idiom_section}\
{supervisor_section}\
{retry_section}\
{unfurl_section}\
When cargo check passes, output two things separated by the literal line `---SUMMARY---`:
1. The final Rust function body (no markdown fences, no explanation)
2. 1-2 sentences describing what this function does (used as context for callers)

Example format:
fn my_func() -> i32 {{
    42
}}
---SUMMARY---
Computes the answer. Returns 42 always.\
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
) -> tuple[str, set[str]]:
    """Load converted Rust snippet bodies for direct (1-hop) in-manifest dependencies.

    Returns (snippet_text, direct_dep_ids) so the caller can use direct_dep_ids
    to avoid double-loading them in the transitive pass.
    """
    lines: list[str] = []
    seen: set[str] = set()
    direct_dep_ids: set[str] = set(node.type_dependencies) | set(node.call_dependencies)

    all_nodes = manifest.nodes
    for dep_id in list(node.type_dependencies) + list(node.call_dependencies):
        if dep_id in seen or dep_id not in all_nodes:
            continue
        seen.add(dep_id)
        dep_node = all_nodes[dep_id]
        if not dep_node.snippet_path:
            continue
        p = Path(dep_node.snippet_path)
        if p.exists():
            lines.append(f"// -- {dep_id} --")
            lines.append(p.read_text().strip())

    return "\n".join(lines), direct_dep_ids


# ── Transitive deps (Level 2): truncated snippets for 2-hop neighbors ─────────

_TRANSITIVE_TRUNCATE_LINES = 20
_TRANSITIVE_CHAR_BUDGET = 2000


def _load_transitive_dep_snippets(
    node: ConversionNode,
    manifest: Manifest,
    direct_dep_ids: set[str],
) -> str:
    """Load first 20 lines of converted snippets for 2-hop transitive deps.

    Excludes nodes already included as direct deps. Capped at _TRANSITIVE_CHAR_BUDGET
    chars total to avoid token pressure.
    """
    all_nodes = manifest.nodes
    seen: set[str] = set(direct_dep_ids) | {node.node_id}
    transitive: list[str] = []

    # Collect unique 2-hop dep IDs
    for dep_id in direct_dep_ids:
        dep_node = all_nodes.get(dep_id)
        if dep_node is None:
            continue
        for tdep in list(dep_node.type_dependencies) + list(dep_node.call_dependencies):
            if tdep not in seen and tdep in all_nodes:
                transitive.append(tdep)
                seen.add(tdep)

    if not transitive:
        return ""

    parts: list[str] = []
    remaining = _TRANSITIVE_CHAR_BUDGET

    for dep_id in transitive:
        dep_node = all_nodes.get(dep_id)
        if dep_node is None:
            continue
        # Prefer agent-written summary over truncated code — denser signal
        if dep_node.summary_text:
            entry = f"// -- {dep_id} (transitive) --\n// {dep_node.summary_text}"
        elif dep_node.snippet_path:
            p = Path(dep_node.snippet_path)
            if not p.exists():
                continue
            snippet_lines = p.read_text().strip().splitlines()
            truncated = "\n".join(snippet_lines[:_TRANSITIVE_TRUNCATE_LINES])
            if len(snippet_lines) > _TRANSITIVE_TRUNCATE_LINES:
                truncated += f"\n// ... ({len(snippet_lines) - _TRANSITIVE_TRUNCATE_LINES} more lines)"
            entry = f"// -- {dep_id} (transitive) --\n{truncated}"
        else:
            continue
        if remaining - len(entry) < 0:
            parts.append(f"// [transitive budget exhausted — {remaining} chars remaining]")
            break
        parts.append(entry)
        remaining -= len(entry)

    return "\n\n".join(parts)


# ── JIT Unfurling (Level 2 retry): load snippets for modules in cargo errors ──

_CARGO_FILE_RE = re.compile(r"^(src/[\w/]+\.rs):\d+:\d+:", re.MULTILINE)
_UNFURL_CHAR_BUDGET = 3000


def _parse_error_modules(error_text: str, target_rs_filename: str) -> list[str]:
    """Extract unique Rust module names from cargo error lines.

    Excludes the target file — those errors are for the agent to fix, not for context.
    """
    files = set(_CARGO_FILE_RE.findall(error_text))
    files.discard(target_rs_filename)
    modules: list[str] = []
    for f in sorted(files):
        stem = Path(f).stem
        if stem not in modules:
            modules.append(stem)
    return modules


def _load_module_snippets(
    module_name: str,
    manifest: Manifest,
    char_budget: int,
) -> str:
    """Load all converted snippets for nodes whose source_file maps to module_name.

    Returns at most char_budget characters total (truncated with a notice).
    """
    lines: list[str] = []
    total_chars = 0

    for node_id, node in manifest.nodes.items():
        if _module_name_for_source(node.source_file) != module_name:
            continue
        if not node.snippet_path:
            continue
        p = Path(node.snippet_path)
        if not p.exists():
            continue
        body = p.read_text().strip()
        entry = f"// -- {node_id} --\n{body}"
        if total_chars + len(entry) > char_budget:
            lines.append(f"// [truncated: budget exhausted at {total_chars} chars]")
            break
        lines.append(entry)
        total_chars += len(entry)

    return "\n\n".join(lines)


def _load_unfurled_deps(
    error_text: str,
    target_source_file: str,
    manifest: Manifest,
) -> str:
    """JIT unfurl: given a cargo error, load snippets for all implicated modules.

    Only called on retry (attempt_count > 0). Identifies which .rs files are
    mentioned in the cargo error (excluding the target file), maps them back to
    manifest nodes, and loads their converted implementations.
    """
    target_module = _module_name_for_source(target_source_file)
    target_rs = f"src/{target_module}.rs"

    modules = _parse_error_modules(error_text, target_rs)
    if not modules:
        return ""

    parts: list[str] = []
    remaining_budget = _UNFURL_CHAR_BUDGET

    for module in modules:
        content = _load_module_snippets(module, manifest, remaining_budget)
        if content:
            parts.append(f"// === Module: {module} ===\n{content}")
            remaining_budget -= len(content)
        if remaining_budget <= 0:
            break

    return "\n\n".join(parts)


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

    # Level 1: direct dep snippets + collect their IDs for transitive pass
    dep_text, direct_dep_ids = _load_dep_snippets(node, manifest, snippets_dir)
    deps_section = (
        f"\n## Converted Dependencies\n```rust\n{dep_text}\n```\n"
        if dep_text
        else ""
    )

    # Level 2: transitive (2-hop) dep snippets, truncated
    transitive_text = _load_transitive_dep_snippets(node, manifest, direct_dep_ids)
    transitive_section = (
        f"\n## Transitive Dependencies (truncated to {_TRANSITIVE_TRUNCATE_LINES} lines each)\n"
        f"```rust\n{transitive_text}\n```\n"
        if transitive_text
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

    # JIT Unfurling: on retry, load full snippets for modules named in the error
    unfurl_section = ""
    if attempt_count > 0 and last_error:
        unfurled_text = _load_unfurled_deps(last_error, node.source_file, manifest)
        if unfurled_text:
            unfurl_section = (
                f"\n## Unfurled Dependencies (from cargo errors)\n"
                f"Implementations of modules mentioned in the previous cargo error:\n"
                f"```rust\n{unfurled_text}\n```\n"
            )

    supervisor_section = ""
    if supervisor_hint:
        supervisor_section = (
            f"\n## Supervisor Hint\n"
            f"A supervisor agent has reviewed previous failures and suggests:\n"
            f"{supervisor_hint}\n"
        )

    from oxidant.analysis.generate_skeleton import _module_name
    module = _module_name(node.source_file)
    # source_file is relative to the msagljs corpus root (e.g. "modules/drawing/src/color.ts")
    source_repo = config.get("source_repo", "corpora/msagljs")
    ts_source_path = (workspace / source_repo / node.source_file).resolve()
    rs_skeleton_path = (target_path / "src" / f"{module}.rs").resolve()
    rs_skeleton_dir = target_path.resolve()

    return _PROMPT_TEMPLATE.format(
        crates=crates,
        arch_decisions=arch_lines,
        node_id=node.node_id,
        ts_source_path=ts_source_path,
        rs_skeleton_path=rs_skeleton_path,
        rs_skeleton_dir=rs_skeleton_dir,
        line_start=node.line_start,
        line_end=node.line_end,
        source_text=node.source_text,
        deps_section=deps_section,
        transitive_section=transitive_section,
        idiom_section=idiom_section,
        supervisor_section=supervisor_section,
        retry_section=retry_section,
        unfurl_section=unfurl_section,
    )
