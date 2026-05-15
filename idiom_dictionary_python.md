# Python → Rust Idiom Dictionary

Injected into Phase B translation prompts when source_language is "python".
Section headers must match idiom tags from detect_idioms_python.py exactly.

## list_comprehension

Python list comprehensions translate to Rust iterator chains.

**Python:**
```python
result = [x * 2 for x in items if x > 0]
```

**Rust:**
```rust
let result: Vec<_> = items.iter()
    .filter(|&&x| x > 0)
    .map(|&x| x * 2)
    .collect();
```

For dict comprehensions: `.map(|(k, v)| ...).collect::<HashMap<_, _>>()`.
For set comprehensions: `.collect::<HashSet<_>>()`.

## optional_type

Python `Optional[T]` and `T | None` both map to Rust `Option<T>`.

**Python:**
```python
def find(items: list[str], key: str) -> Optional[str]:
    return None
```

**Rust:**
```rust
fn find(items: &[String], key: &str) -> Option<String> {
    None
}
```

Use `if let Some(x) = value { ... }` instead of `if value is not None`.

## generator_function

Python generators (`yield`) become Rust `impl Iterator` types.
For simple cases, collect into a `Vec` first and return that.

**Python:**
```python
def gen_pairs(items):
    for i, item in enumerate(items):
        yield (i, item)
```

**Rust (collect approach):**
```rust
fn gen_pairs(items: &[String]) -> Vec<(usize, String)> {
    items.iter().enumerate().map(|(i, s)| (i, s.clone())).collect()
}
```

## format_string

Python f-strings translate directly to Rust `format!()`.

**Python:** `f"Hello, {name}! Count: {count:.2f}"`

**Rust:** `format!("Hello, {}! Count: {:.2}", name, count)`

Format spec mapping: `{:.2f}` → `{:.2}`, `{:>10}` → `{:>10}`.

## none_check

Python `x is None` / `x is not None` → Rust `x.is_none()` / `x.is_some()`.

**Python:**
```python
if x is None:
    return default
return x
```

**Rust:**
```rust
x.unwrap_or(default)
// or:
match x {
    None => default,
    Some(v) => v,
}
```

## isinstance_check

Python `isinstance(x, SomeClass)` usually signals a type hierarchy that should
become a Rust `enum` with `match`.

**Python:**
```python
if isinstance(shape, Circle):
    draw_circle(shape)
elif isinstance(shape, Rect):
    draw_rect(shape)
```

**Rust:**
```rust
match shape {
    Shape::Circle(c) => draw_circle(c),
    Shape::Rect(r) => draw_rect(r),
}
```

## multiple_return

Python functions returning `tuple[T, U]` become Rust functions returning `(T, U)`.

**Python:** `def split(s: str) -> tuple[list[str], float]: ...`

**Rust:** `fn split(s: &str) -> (Vec<String>, f64) { ... }`

Destructure with `let (lines, size) = split(s);`.

## svgwrite_buffer

`svgwrite.Drawing` and similar DOM-like SVG builders → accumulate into a `String`.
Use `buf.push_str(...)` to append SVG tag strings.

**Python:**
```python
dwg = svgwrite.Drawing()
dwg.add(dwg.text("Hello", insert=(10, 20)))
return dwg.tostring()
```

**Rust:**
```rust
let mut buf = String::new();
buf.push_str(r#"<text x="10" y="20">Hello</text>"#);
buf
```

## typed_dict

Python `TypedDict` becomes a Rust `struct` (not a `HashMap`).

**Python:**
```python
class TitleBlockParams(TypedDict):
    width: float
    height: float
    title: str
```

**Rust:**
```rust
#[derive(Debug, Clone)]
struct TitleBlockParams {
    pub width: f64,
    pub height: f64,
    pub title: String,
}
```
