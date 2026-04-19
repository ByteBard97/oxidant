# Idiom Detection

TypeScript has patterns with no direct Rust equivalent. Oxidant detects these statically in Phase A and injects targeted translation guidance into Phase B prompts. Each node only receives guidance for the idioms present in *its own* source — no noise, no irrelevant context.

---

## Detected idioms (msagl-js counts)

| Idiom | Occurrences | Description |
|-------|-------------|-------------|
| `mutable_shared_state` | 1,608 | Objects mutated after being passed to a function |
| `null_undefined` | 1,171 | `== null`, `?.`, `??`, nullable return types |
| `dynamic_property_access` | 945 | `obj[key]` with a computed key |
| `static_members` | 920 | `static` class fields and methods |
| `number_as_index` | 519 | `number` used to index an array (should be `usize`) |
| `closure_capture` | 441 | Closures that capture outer-scope variables |
| `array_method_chain` | 248 | `.map()` / `.filter()` / `.reduce()` / `.find()` chains |
| `map_usage` | 242 | `Map<K,V>` usage |
| `set_usage` | 220 | `Set<T>` usage |
| `generator_function` | 186 | `function*` and `yield` |
| `class_inheritance` | 118 | `extends` relationships (see Class Hierarchies) |
| `union_type` | 34 | TypeScript union types (`A \| B`) |
| `optional_chaining` | 13 | `?.` operator |
| `async_await` | 7 | `async`/`await` and `Promise` patterns |

---

## How idiom guidance is injected

`context.py` loads relevant sections from `idiom_dictionary.md` by matching section headers to the node's `idioms_needed` tags:

```python
def _load_idiom_entries(idioms: list[str], workspace: Path) -> str:
    content = (workspace / "idiom_dictionary.md").read_text()
    for idiom in idioms:
        pattern = re.compile(rf"^##\s+{re.escape(idiom)}\b.*?(?=^##\s|\Z)",
                             re.MULTILINE | re.DOTALL)
        # ... extract matching section
```

The result appears in the prompt under `## Idiom Translations`, containing only the sections relevant to the current node.

---

## Translation examples

### `null_undefined` → `Option<T>`

=== "TypeScript"

    ```typescript
    const node = graph.findNode(id);
    if (node == null) return null;
    return node.label ?? "untitled";
    ```

=== "Rust"

    ```rust
    let node = graph.borrow().find_node(id);
    if node.is_none() { return None; }
    let node = node.unwrap();
    Some(node.borrow().label
        .clone()
        .unwrap_or_else(|| "untitled".to_string()))
    ```

### `mutable_shared_state` → `Rc<RefCell<T>>`

=== "TypeScript"

    ```typescript
    class GeomGraph {
      boundingBox: Rectangle;
      constructor() {
        this.boundingBox = new Rectangle();
      }
    }
    // Shared reference: graph is passed to multiple objects
    // and they all mutate boundingBox
    ```

=== "Rust"

    ```rust
    pub struct GeomGraph {
        pub bounding_box: Rectangle,
    }

    // Shared, mutable reference:
    let graph: Rc<RefCell<GeomGraph>> = Rc::new(RefCell::new(GeomGraph { ... }));
    // Read:  graph.borrow().bounding_box
    // Write: graph.borrow_mut().bounding_box = r;
    ```

### `array_method_chain` → iterators

=== "TypeScript"

    ```typescript
    const result = nodes
      .filter(n => n.isVisible)
      .map(n => n.label)
      .find(l => l.startsWith("main"));
    ```

=== "Rust"

    ```rust
    let result = nodes.iter()
        .filter(|n| n.borrow().is_visible)
        .map(|n| n.borrow().label.clone())
        .find(|l| l.starts_with("main"));
    ```
