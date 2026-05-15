# Task 5: Parameterise Prompt Language + Wire Idiom Loader

**Part of:** [Python→Rust Frontend](2026-05-15-python-frontend-overview.md) — do Task 4 first.

**Goal:** Three things in `agents/context.py`:
1. Replace all 6 hardcoded "TypeScript" strings in `_PROMPT_TEMPLATE` with `{source_language}`
2. Update `_load_idiom_entries()` to pick `idiom_dictionary_python.md` vs `idiom_dictionary.md` by language
3. Thread `source_language` through `build_prompt()` to both

**Files:**
- Modify: `src/oxidant/agents/context.py`
- Modify: `tests/test_context.py`

---

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_context.py`. The existing file uses a `_make_manifest()` helper function — use `Manifest.load(db)` directly for a minimal empty manifest:

```python
def test_prompt_uses_python_language(tmp_path):
    """build_prompt with source_language=python should not mention TypeScript."""
    from oxidant.agents.context import build_prompt
    from oxidant.models.manifest import ConversionNode, Manifest, NodeKind

    db = tmp_path / "test.db"
    manifest = Manifest.load(db)
    node = ConversionNode(
        node_id="sample__foo",
        source_file="sample.py",
        line_start=1, line_end=5,
        source_text="def foo(): pass",
        node_kind=NodeKind.FREE_FUNCTION,
    )
    manifest.nodes["sample__foo"] = node

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config={
            "source_language": "python",
            "source_repo": ".",
            "crate_inventory": [],
            "architectural_decisions": {},
        },
        target_path=tmp_path,
        snippets_dir=tmp_path,
        workspace=tmp_path,
    )
    assert "TypeScript" not in prompt, "Prompt still contains 'TypeScript'"
    assert "Python" in prompt
    assert "## Python Source" in prompt


def test_prompt_defaults_to_typescript(tmp_path):
    """build_prompt without source_language should still say TypeScript."""
    from oxidant.agents.context import build_prompt
    from oxidant.models.manifest import ConversionNode, Manifest, NodeKind

    db = tmp_path / "test2.db"
    manifest = Manifest.load(db)
    node = ConversionNode(
        node_id="sample__bar",
        source_file="sample.ts",
        line_start=1, line_end=3,
        source_text="function bar() {}",
        node_kind=NodeKind.FREE_FUNCTION,
    )
    manifest.nodes["sample__bar"] = node

    prompt = build_prompt(
        node=node,
        manifest=manifest,
        config={"source_repo": ".", "crate_inventory": [], "architectural_decisions": {}},
        target_path=tmp_path,
        snippets_dir=tmp_path,
        workspace=tmp_path,
    )
    assert "TypeScript" in prompt
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
python -m pytest tests/test_context.py::test_prompt_uses_python_language tests/test_context.py::test_prompt_defaults_to_typescript -v
```

Expected: first test FAIL ("TypeScript" still in prompt), second PASS.

- [ ] **Step 3: Add language lookup dicts and update `_load_idiom_entries`**

At the top of `src/oxidant/agents/context.py`, after the imports, add:

```python
_LANG_DISPLAY: dict[str, str] = {
    "typescript": "TypeScript",
    "python": "Python",
}

_IDIOM_DICT_PATHS: dict[str, str] = {
    "typescript": "idiom_dictionary.md",
    "python": "idiom_dictionary_python.md",
}
```

Replace the `_load_idiom_entries` function signature and first line:

```python
def _load_idiom_entries(
    idioms: list[str],
    workspace: Path,
    source_language: str = "typescript",
) -> str:
    """Load relevant sections from the idiom dictionary for this language."""
    dict_filename = _IDIOM_DICT_PATHS.get(source_language, "idiom_dictionary.md")
    dict_path = workspace / dict_filename
    if not dict_path.exists() or not idioms:
        return ""
    # ... rest of function unchanged (regex pattern search) ...
```

- [ ] **Step 4: Replace all 6 "TypeScript" occurrences in `_PROMPT_TEMPLATE`**

Replace the entire `_PROMPT_TEMPLATE` string with the version below. The key changes: every `TypeScript` reference becomes `{source_language}`, the code fence tag is `{source_language_fence}`, and double-braces escape the literal braces in the example `fn` body.

```python
_PROMPT_TEMPLATE = """\
You are converting one {source_language} function to Rust.

## Your job
1. Read the {source_language} source file to understand the function and its context
2. Read the Rust skeleton file to understand available types and fields
3. Write the Rust function body and insert it into the skeleton using Edit
4. Run cargo check to verify it compiles: use Bash with `cd {rs_skeleton_dir} && cargo check`
5. Fix any errors and repeat until cargo check passes

## Files
- {source_language} source: {ts_source_path} (lines {line_start}--{line_end})
- Rust skeleton: {rs_skeleton_path}
- Cargo check directory: {rs_skeleton_dir}
- Function to implement: `{node_id}`
- The skeleton has a `todo!("OXIDANT: not yet translated — {node_id}")` marker \
where your implementation goes

## {source_language} Source
```{source_language_fence}
{source_text}
```

## Rules
- Implement ONLY the function body for `{node_id}` -- do not change anything else
- OUTPUT PURE ASCII ONLY. No backticks, no em-dashes, no curly quotes, \
no non-ASCII characters of any kind. They break compilation for every function in the file.
- Do NOT use todo!(), unimplemented!(), or panic!()
- Translate semantically faithfully -- match every branch in the {source_language} source
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
```

- [ ] **Step 5: Update `build_prompt()` to derive and pass `source_language`**

In `build_prompt()`, replace the existing `idiom_text` / `idiom_section` lines and add the `source_language` variables. The `return _PROMPT_TEMPLATE.format(...)` call needs two new arguments:

```python
    source_language_key = config.get("source_language", "typescript")
    source_language_display = _LANG_DISPLAY.get(source_language_key, source_language_key.title())
    source_language_fence = source_language_key  # used as code fence language tag

    # Replace the existing idiom_text line:
    idiom_text = _load_idiom_entries(
        node.idioms_needed, workspace, source_language=source_language_key
    )
    idiom_section = f"\n## Idiom Translations\n{idiom_text}\n" if idiom_text else ""

    # In the return call, add these two new keyword args:
    return _PROMPT_TEMPLATE.format(
        source_language=source_language_display,
        source_language_fence=source_language_fence,
        # ... all existing args unchanged ...
    )
```

- [ ] **Step 6: Run all context tests**

```bash
python -m pytest tests/test_context.py tests/test_context_progressive.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/oxidant/agents/context.py tests/test_context.py
git commit -m "feat: parameterise source language in translation prompt and idiom loader"
```

**Next:** [Task 6 — Branch parity](2026-05-15-python-frontend-t6-branch-parity.md)
