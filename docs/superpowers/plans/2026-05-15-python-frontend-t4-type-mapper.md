# Task 4: Python Type Mapper + Skeleton Generator Update

**Part of:** [Python→Rust Frontend](2026-05-15-python-frontend-overview.md) — do Task 3 first.

**Goal:** Add `map_python_type()` to `generate_skeleton.py` alongside the existing `map_ts_type()`. Also parameterise the Cargo.toml writer: use `crate_name` from config, and skip writing if Cargo.toml already exists (the flora-studio target crate has its own).

**Known limitation:** `map_python_type` splits composite types (e.g. `dict[K, V]`, `tuple[T, U]`) by finding the first top-level comma. This breaks on double-nested generics like `dict[tuple[int, int], str]`. Check the flora-backend corpus for such annotations before deciding whether to fix this.

**Files:**
- Modify: `src/oxidant/analysis/generate_skeleton.py`
- Create: `tests/test_map_python_type.py`

---

- [ ] **Step 1: Write the failing tests**

Create `tests/test_map_python_type.py`:

```python
from oxidant.analysis.generate_skeleton import map_python_type


def test_primitives():
    assert map_python_type("int") == "i64"
    assert map_python_type("float") == "f64"
    assert map_python_type("str") == "String"
    assert map_python_type("bool") == "bool"
    assert map_python_type("bytes") == "Vec<u8>"
    assert map_python_type("None") == "()"


def test_list():
    assert map_python_type("list[int]") == "Vec<i64>"
    assert map_python_type("List[str]") == "Vec<String>"


def test_dict():
    assert map_python_type("dict[str, int]") == "std::collections::HashMap<String, i64>"
    assert map_python_type("Dict[str, float]") == "std::collections::HashMap<String, f64>"


def test_set():
    assert map_python_type("set[str]") == "std::collections::HashSet<String>"


def test_optional_bracket():
    assert map_python_type("Optional[int]") == "Option<i64>"
    assert map_python_type("Optional[str]") == "Option<String>"


def test_optional_union_syntax():
    assert map_python_type("int | None") == "Option<i64>"
    assert map_python_type("None | str") == "Option<String>"


def test_tuple_two():
    assert map_python_type("tuple[str, float]") == "(String, f64)"
    assert map_python_type("Tuple[int, int]") == "(i64, i64)"


def test_any():
    assert map_python_type("Any") == "serde_json::Value"


def test_unknown_type():
    assert map_python_type("MyClass") == "serde_json::Value"


def test_known_class():
    assert map_python_type("MyClass", known_classes={"MyClass"}) == "Rc<RefCell<MyClass>>"


def test_nested_list_optional():
    assert map_python_type("list[Optional[int]]") == "Vec<Option<i64>>"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
python -m pytest tests/test_map_python_type.py -v
```

Expected: ImportError (`map_python_type` not yet defined).

- [ ] **Step 3: Add `map_python_type()` to `generate_skeleton.py`**

`generate_skeleton.py` already has `import re` at the top. Add the block below immediately **after** the `map_ts_type` function. Do not add another `import re` — use the existing module-level one.

```python
# ── Python → Rust type mapper ──────────────────────────────────────────────────

_PYTHON_PRIMITIVES: dict[str, str] = {
    "int": "i64", "float": "f64", "str": "String", "bool": "bool",
    "bytes": "Vec<u8>", "None": "()", "Any": "serde_json::Value",
    "object": "serde_json::Value", "complex": "serde_json::Value",
}


def map_python_type(py_type: str, known_classes: set[str] | None = None) -> str:
    """Map a Python type annotation string to a Rust type string.

    Note: composite type splitting (dict[K,V], tuple[T,U]) uses naive comma
    splitting which breaks on doubly-nested generics like dict[tuple[int,int], str].
    Check the target corpus for such annotations before extending this.
    """
    t = py_type.strip()
    known = known_classes or set()

    def recurse(inner: str) -> str:
        return map_python_type(inner.strip(), known)

    if t in _PYTHON_PRIMITIVES:
        return _PYTHON_PRIMITIVES[t]

    if m := re.fullmatch(r"(?:list|List)\[(.+)\]", t):
        return f"Vec<{recurse(m.group(1))}>"

    if m := re.fullmatch(r"(?:dict|Dict)\[(.+),\s*(.+)\]", t):
        return f"std::collections::HashMap<{recurse(m.group(1))}, {recurse(m.group(2))}>"

    if m := re.fullmatch(r"(?:set|Set)\[(.+)\]", t):
        return f"std::collections::HashSet<{recurse(m.group(1))}>"

    if m := re.fullmatch(r"Optional\[(.+)\]", t):
        return f"Option<{recurse(m.group(1))}>"

    # T | None  /  None | T
    parts = [p.strip() for p in t.split("|")]
    non_none = [p for p in parts if p != "None"]
    if len(non_none) < len(parts) and len(non_none) == 1:
        return f"Option<{recurse(non_none[0])}>"

    if m := re.fullmatch(r"(?:tuple|Tuple)\[(.+)\]", t):
        elems = [recurse(e.strip()) for e in m.group(1).split(",")]
        return f"({', '.join(elems)})"

    if t in known:
        return f"Rc<RefCell<{t}>>"

    return "serde_json::Value"
```

- [ ] **Step 4: Update `generate_skeleton()` to skip existing Cargo.toml and accept config**

Change the function signature and wrap the Cargo.toml write in an existence check:

```python
def generate_skeleton(manifest_path: Path, target_path: Path, config: dict | None = None) -> None:
```

Then find the `(target_path / "Cargo.toml").write_text(...)` block and replace it with:

```python
    cargo_toml = target_path / "Cargo.toml"
    if not cargo_toml.exists():
        crate_name = (config or {}).get("crate_name") or target_path.name
        cargo_toml.write_text(textwrap.dedent(f"""\
            [package]
            name = "{crate_name}"
            version = "0.1.0"
            edition = "2021"

            [dependencies]
            slotmap      = "1"
            petgraph     = "0.6"
            nalgebra     = "0.33"
            thiserror    = "2"
            itertools    = "0.13"
            ordered-float = "4"
            serde        = {{ version = "1", features = ["derive"] }}
            serde_json   = "1"
        """))
```

Note: existing callers in `tests/test_generate_skeleton.py` call `generate_skeleton(mpath, target)` without `config` — since it defaults to `None`, they continue to work unchanged. The `cli.py` A5 call is updated by Task 1 (not this task).

- [ ] **Step 5: Run all type mapper and skeleton tests**

```bash
python -m pytest tests/test_map_python_type.py tests/test_generate_skeleton.py -v
```

Expected: all PASS (existing TS skeleton tests unaffected).

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/analysis/generate_skeleton.py tests/test_map_python_type.py
git commit -m "feat: add map_python_type(), parameterise Cargo.toml crate_name"
```

**Next:** [Task 5 — Prompt wiring](2026-05-15-python-frontend-t5-prompt-wiring.md)
