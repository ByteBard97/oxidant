# Task 6: Language-Aware Branch Parity

**Part of:** [Python→Rust Frontend](2026-05-15-python-frontend-overview.md) — do Task 5 first.

**Goal:** `_check_branch_parity` currently uses `_BRANCH_RE_TS` (TypeScript keywords) even when the source is Python. Add `_BRANCH_RE_PY`, make the regex an optional parameter, rename the misleadingly-named `_BRANCH_MIN_TS_COUNT` constant, and thread the correct regex from config through `graph/nodes.py`.

**Files:**
- Modify: `src/oxidant/verification/verify.py`
- Modify: `src/oxidant/graph/nodes.py`
- Modify: `tests/test_verify.py`

---

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify.py`:

```python
def test_branch_parity_python_regex_triggers_on_python_branches():
    """Python regex should count elif/try/except. A Rust snippet with only 1
    branch should fail parity when Python source has 6+ branch points."""
    from oxidant.verification.verify import _check_branch_parity, _BRANCH_RE_PY, VerifyStatus
    # 6 branch points: if, elif, elif, else, try, except
    py_source = (
        "if a:\n    x()\n"
        "elif b:\n    y()\n"
        "elif c:\n    z()\n"
        "else:\n    w()\n"
        "try:\n    f()\n"
        "except ValueError:\n    pass\n"
    )
    rs_snippet = "if a { x() }"  # 1 Rust branch — well below 60% of 6
    result = _check_branch_parity(py_source, rs_snippet, source_branch_re=_BRANCH_RE_PY)
    assert result is not None
    assert result.status == VerifyStatus.BRANCH


def test_branch_parity_ts_regex_default_unchanged():
    """Calling without source_branch_re preserves TypeScript behaviour."""
    from oxidant.verification.verify import _check_branch_parity, VerifyStatus
    ts = "if a { } else if b { } else { } for (x of y) { } while (z) { }"
    rs = "42"
    result = _check_branch_parity(ts, rs)
    assert result is not None
    assert result.status == VerifyStatus.BRANCH


def test_branch_parity_python_regex_passes_simple():
    """A simple Python function with 1 branch should pass (below threshold)."""
    from oxidant.verification.verify import _check_branch_parity, _BRANCH_RE_PY
    py_source = "if x:\n    return x\nreturn 0\n"
    rs_snippet = "if x { return x; } 0"
    result = _check_branch_parity(py_source, rs_snippet, source_branch_re=_BRANCH_RE_PY)
    assert result is None  # only 1 branch in source — below the min threshold
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
python -m pytest tests/test_verify.py::test_branch_parity_python_regex_triggers_on_python_branches tests/test_verify.py::test_branch_parity_ts_regex_default_unchanged tests/test_verify.py::test_branch_parity_python_regex_passes_simple -v
```

Expected: first test FAIL (`_BRANCH_RE_PY` doesn't exist), others PASS.

- [ ] **Step 3: Update `verify.py`**

**3a.** Rename `_BRANCH_MIN_TS_COUNT` → `_BRANCH_MIN_SRC_COUNT` (two occurrences: definition and use in `_check_branch_parity`).

**3b.** Add `_BRANCH_RE_PY` below the existing `_BRANCH_RE_TS` line:

```python
_BRANCH_RE_PY = re.compile(
    r'\bif\b|\belif\b|\belse\b|\bfor\b|\bwhile\b|\btry\b|\bexcept\b|\bwith\b|\bmatch\b'
)
```

**3c.** Update `_check_branch_parity` signature:

```python
def _check_branch_parity(
    source_text: str,
    rs_snippet: str,
    source_branch_re: re.Pattern | None = None,
) -> VerifyResult | None:
    branch_re = source_branch_re if source_branch_re is not None else _BRANCH_RE_TS
    src_count = len(branch_re.findall(source_text))
    rs_count = len(_BRANCH_RE_RS.findall(rs_snippet))
    if src_count >= _BRANCH_MIN_SRC_COUNT and rs_count < src_count * _BRANCH_RATIO_FLOOR:
        return VerifyResult(
            VerifyStatus.BRANCH,
            f"Branch parity: source={src_count} branches, Rust={rs_count} "
            f"(below {_BRANCH_RATIO_FLOOR:.0%} floor)",
        )
    return None
```

**3d.** Add `source_branch_re` kwarg to `verify_snippet`:

```python
def verify_snippet(
    node_id: str,
    snippet: str,
    ts_source: str,
    target_path: Path,
    source_file: str,
    source_branch_re: re.Pattern | None = None,
) -> VerifyResult:
    if r := _check_stubs(snippet):
        return r
    if r := _check_branch_parity(ts_source, snippet, source_branch_re=source_branch_re):
        return r
    if r := _inject_and_check_cargo(node_id, snippet, target_path, source_file):
        return r
    return VerifyResult(VerifyStatus.PASS)
```

- [ ] **Step 4: Update `graph/nodes.py` to derive and pass the branch regex**

Replace the body of `verify()` in `src/oxidant/graph/nodes.py` with:

```python
def verify(state: OxidantState) -> dict:
    """Run the three verification checks (stub / branch parity / cargo check)."""
    from oxidant.verification.verify import _BRANCH_RE_PY, _BRANCH_RE_TS

    source_language = state.get("config", {}).get("source_language", "typescript")
    branch_re = _BRANCH_RE_PY if source_language == "python" else _BRANCH_RE_TS

    manifest = Manifest.load(_db(state))
    node = manifest.get_node(state["current_node_id"]) or manifest.nodes[state["current_node_id"]]
    snippet = state.get("current_snippet")

    if snippet is None:
        return {
            "verify_status": VerifyStatus.CARGO.value,
            "last_error": state.get("last_error") or "Agent invocation failed (no snippet returned)",
        }

    worker_id = state.get("worker_id", 0)
    target = Path(state["target_path"])
    if worker_id > 0:
        clone = target / f".clone_{worker_id}"
        if clone.exists():
            target = clone

    result = verify_snippet(
        node_id=node.node_id,
        snippet=snippet,
        ts_source=node.source_text,
        target_path=target,
        source_file=node.source_file,
        source_branch_re=branch_re,
    )
    return {
        "verify_status": result.status.value,
        "last_error": result.error or None,
    }
```

- [ ] **Step 5: Run all verify and graph tests**

```bash
python -m pytest tests/test_verify.py tests/test_graph_nodes.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/verification/verify.py src/oxidant/graph/nodes.py tests/test_verify.py
git commit -m "feat: language-aware branch parity, add _BRANCH_RE_PY, rename _BRANCH_MIN_SRC_COUNT"
```

**Next:** [Task 7 — Idiom dictionary](2026-05-15-python-frontend-t7-idiom-dict.md)
