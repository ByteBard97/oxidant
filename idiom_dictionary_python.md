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

## shapely_geometry

Shapely geometry types and operations translate to the `geo` crate.

**Type mapping:**

| Shapely | Rust (`geo` crate) |
|---------|-------------------|
| `Polygon` | `geo::Polygon<f64>` |
| `LineString` | `geo::LineString<f64>` |
| `MultiLineString` | `geo::MultiLineString<f64>` |
| `Point` | `geo::Point<f64>` |

**Construction:**

```python
poly = Polygon([(x0,y0), (x1,y1), (x2,y2)])
line = LineString([(x0,y0), (x1,y1)])
pt   = Point(x, y)
```

```rust
use geo::{Polygon, LineString, Point, coord};
let poly = Polygon::new(
    LineString::from(vec![(x0, y0), (x1, y1), (x2, y2)]),
    vec![],
);
let line = LineString::from(vec![(x0, y0), (x1, y1)]);
let pt   = Point::new(x, y);
```

**Bounds (replaces `.bounds` → `(min_x, min_y, max_x, max_y)`):**

```python
(min_x, min_y, max_x, max_y) = poly.bounds
```

```rust
use geo::BoundingRect;
let bbox = poly.bounding_rect().unwrap();
let (min_x, min_y) = (bbox.min().x, bbox.min().y);
let (max_x, max_y) = (bbox.max().x, bbox.max().y);
```

**Rotation (replaces `affinity.rotate(geom, angle_deg, origin)`):**

```python
rotated = affinity.rotate(poly, angle_deg, origin=(cx, cy))
```

```rust
use geo::{Rotate, Point};
let origin = Point::new(cx, cy);
let rotated = poly.rotate_around_point(-angle_deg, origin);
```

Note: shapely rotates counter-clockwise for positive angles; `geo::Rotate` also rotates counter-clockwise, so signs match directly.

**Intersection (replaces `.intersection(other)`):**

```python
intersection = line.intersection(poly)
if type(intersection) is MultiLineString:
    for geom in intersection.geoms:
        ...
else:
    ...  # LineString
```

```rust
use geo::algorithm::line_intersection::LineIntersection;
use geo::Intersects;
// For polygon-clip of a line, use geo::algorithm::clip::Clip:
use geo::Clip;
let clipped: geo::MultiLineString<f64> = line.clip(&poly, false);
for segment in clipped.0.iter() {
    // segment is a geo::LineString<f64>
}
```

**Checking intersection (replaces `.intersects(other)`):**

```python
if line.intersects(poly):
```

```rust
use geo::Intersects;
if line.intersects(&poly) {
```

**LineString coords iteration:**

```python
for coord in line.coords:
    x, y = coord
```

```rust
for coord in line.coords() {
    let (x, y) = (coord.x, coord.y);
}
```

**Minimum rotated rectangle (replaces `.minimum_rotated_rectangle`):**

```python
rect = poly.minimum_rotated_rectangle
rectx = rect.exterior.xy[0]
recty = rect.exterior.xy[1]
```

```rust
use geo::MinimumRotatedRect;
let rect: Option<geo::Polygon<f64>> = poly.minimum_rotated_rect();
if let Some(rect) = rect {
    let coords: Vec<_> = rect.exterior().coords().collect();
    // coords[i].x, coords[i].y
}
```

**Area:**

```python
area = poly.area
```

```rust
use geo::Area;
let area = poly.unsigned_area();
```

**Point buffer (replaces `Point(lon, lat).buffer(radius)`):**

Shapely's `.buffer()` has no direct single-call equivalent in `geo`. For the common pattern of creating a fake circular boundary around a point, use a manual approximation:

```rust
// approximate circle as N-sided polygon
fn point_buffer(lon: f64, lat: f64, radius: f64, n: usize) -> geo::Polygon<f64> {
    use std::f64::consts::TAU;
    let coords: Vec<_> = (0..=n).map(|i| {
        let angle = TAU * (i as f64) / (n as f64);
        geo::coord! { x: lon + radius * angle.cos(), y: lat + radius * angle.sin() }
    }).collect();
    geo::Polygon::new(geo::LineString::from(coords), vec![])
}
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
