# Idiom Dictionary — msagl-js → Rust

MSAGL-specific guidance for each TypeScript pattern detected in the corpus.
Sections are keyed exactly to idiom names used in `conversion_manifest.json`.

---

## mutable_shared_state

TypeScript class properties are mutable by default and shared freely via
object references.

**For simple field mutation on `&mut self`:**
```rust
// TS: this.someField = value;
self.some_field = value;

// TS: let count = 0; count++;
let mut count = 0i32; count += 1;
```

Do NOT reach for `RefCell` for local variables or for `self` fields accessed
through `&mut self`.

**For graph entities that hold references to other graph entities (Node, Edge,
GeomNode, GeomEdge, etc.):** use the **arena allocation pattern** — see
`arena_allocation` idiom. Do NOT use `Rc<RefCell<T>>` for these; it creates
nested borrow chains that become unmanageable. `Rc<RefCell<T>>` is only
appropriate for non-graph shared state that genuinely needs shared ownership
with interior mutability (e.g., a shared configuration object).

**For shared non-graph state that needs `Rc<RefCell<T>>`:**
```rust
// TS: node.someField = value;   where node is a truly shared ref
node.borrow_mut().some_field = value;
```

---

## null_undefined

TypeScript `null | undefined` maps to `Option<T>`. Common patterns:

```rust
// TS: if (x == null) { ... }
if x.is_none() { ... }

// TS: if (x != null) { ... }
if let Some(val) = x { ... }
// or: if x.is_some() { ... }

// TS: x ?? defaultVal
x.unwrap_or(default_val)

// TS: x?.method()
x.as_ref().map(|v| v.method())
// or for Rc<RefCell<T>>:
x.as_ref().map(|v| v.borrow().method())

// TS: return null;
return None;

// TS: x!  (non-null assertion)
x.unwrap()   // or x.expect("reason")
```

For msagl graph nodes that are `null` when not yet attached:
use `Option<Rc<RefCell<T>>>` in the skeleton types.

---

## dynamic_property_access

TypeScript `obj[key]` with string/number keys maps to:

```rust
// TS: map[key]  where map is Map<string, V>
map.get(&key)          // returns Option<&V>
map[&key]              // panics if missing — use only when certain

// TS: arr[i]  where arr is an array/typed array
arr[i as usize]        // cast index to usize

// TS: obj[key] = val  for Map
map.insert(key, val);

// TS: delete obj[key]
map.remove(&key);
```

For msagl's `idToGeomNode` and similar id-keyed maps, use `HashMap<NodeId, ...>`.

---

## static_members

TypeScript static class members translate to associated functions or
`static` items in Rust impl blocks:

```rust
// TS: static count = 0;
// In Rust, use a thread_local! or lazy_static for mutable statics,
// or a const for immutable ones.
static COUNT: std::sync::atomic::AtomicI32 = std::sync::atomic::AtomicI32::new(0);
// or for thread-local mutable state:
thread_local! { static COUNT: RefCell<i32> = RefCell::new(0); }

// TS: static create(): Foo { ... }
// In impl block:
pub fn create() -> Self { ... }    // called as Foo::create()

// TS: static readonly PI = 3.14;
const PI: f64 = 3.14;              // associated const
```

msagl uses static factory methods extensively (e.g., `GeomNode.mkGeom`).
These become associated functions: `GeomNode::mk_geom(...)`.

---

## number_as_index

TypeScript allows using `number` as an array index. Rust requires `usize`:

```rust
// TS: arr[i]   where i is number
arr[i as usize]

// TS: for (let i = 0; i < arr.length; i++)
for i in 0..arr.len() { ... }   // i is usize automatically

// TS: arr.length
arr.len()
```

When an index comes from an external computation that might be negative,
guard first:
```rust
if i >= 0 { arr[i as usize] }
```

---

## closure_capture

TypeScript arrow functions and function expressions that capture variables:

```rust
// TS: const f = (x: number) => x * 2;
let f = |x: f64| x * 2.0;

// TS: arr.filter(n => n > threshold)   where threshold is captured
arr.iter().filter(|&&n| n > threshold)

// TS: capturing mutable state:
// const sum = 0; arr.forEach(x => sum += x);
let mut sum = 0.0_f64;
for x in &arr { sum += x; }
// Rust closures can capture &mut, but not if captured by multiple closures.
// Use a for loop when mutation is involved.

// TS: () => { ... }  as callback stored in struct
// Use Box<dyn Fn()> or Box<dyn FnMut()> for heap-stored callbacks.
```

---

## array_method_chain

TypeScript array method chains (`map`, `filter`, `reduce`, etc.) become
iterator chains in Rust:

```rust
// TS: arr.map(x => x * 2)
arr.iter().map(|x| x * 2.0).collect::<Vec<_>>()

// TS: arr.filter(x => x > 0)
arr.iter().filter(|&&x| x > 0.0).copied().collect::<Vec<_>>()

// TS: arr.reduce((acc, x) => acc + x, 0)
arr.iter().fold(0.0_f64, |acc, &x| acc + x)

// TS: arr.find(x => x.id == target)
arr.iter().find(|x| x.id == target)  // returns Option<&T>

// TS: arr.some(x => condition)
arr.iter().any(|x| condition)

// TS: arr.every(x => condition)
arr.iter().all(|x| condition)

// TS: arr.forEach(x => { ... })
for x in &arr { ... }

// TS: arr.flatMap(x => x.children)
arr.iter().flat_map(|x| x.children.iter()).collect::<Vec<_>>()
```

For msagl geometry collections, prefer iterator adapters over intermediate Vecs.

---

## map_usage

TypeScript `Map<K, V>` maps to `std::collections::HashMap<K, V>`:

```rust
// TS: new Map<string, Foo>()
HashMap::<String, Foo>::new()

// TS: map.set(key, val)
map.insert(key, val);

// TS: map.get(key)
map.get(&key)   // returns Option<&V>

// TS: map.has(key)
map.contains_key(&key)

// TS: map.delete(key)
map.remove(&key);

// TS: map.size
map.len()

// TS: for (const [k, v] of map)
for (k, v) in &map { ... }

// TS: map.keys()  /  map.values()  /  map.entries()
map.keys()  /  map.values()  /  map.iter()
```

msagl uses `Map<number, GeomNode>` for node lookups. In Rust, use
`HashMap<u32, Rc<RefCell<GeomNode>>>` or index into a slotmap.

---

## set_usage

TypeScript `Set<T>` maps to `std::collections::HashSet<T>`:

```rust
// TS: new Set<string>()
HashSet::<String>::new()

// TS: set.add(val)
set.insert(val);

// TS: set.has(val)
set.contains(&val)

// TS: set.delete(val)
set.remove(&val);

// TS: set.size
set.len()

// TS: for (const v of set)
for v in &set { ... }
```

For msagl edge/node sets, `HashSet<SlotMapKey>` works well since keys
are `Copy` and `Hash`.

---

## generator_function

TypeScript `function*` generators yield sequences lazily. In Rust, there
are no stable generators yet. Translate as:

1. **Collect upfront** (simplest — msagl generators are typically small):
```rust
// TS: function* edges() { for (const e of ...) yield e; }
// Rust: return a Vec instead
pub fn edges(&self) -> Vec<EdgeId> {
    self.edge_ids.iter().copied().collect()
}
```

2. **Return an iterator** (when collection is expensive):
```rust
pub fn edges(&self) -> impl Iterator<Item = EdgeId> + '_ {
    self.edge_ids.iter().copied()
}
```

For msagl graph traversals, collect into `Vec` unless the caller is always
iterating without storing — then returning `impl Iterator` is preferred.

---

## class_inheritance

TypeScript class inheritance (`extends`) becomes trait implementations in Rust.
msagl uses `extends` for geometry types (e.g., `GeomGraph extends GeomNode`).

```rust
// TS: class Child extends Parent { ... }
// Rust pattern used in this skeleton: composition + Deref, or trait objects.
// The skeleton uses Rc<RefCell<T>> for parent data stored as a field:
struct GeomGraph {
    base: GeomNode,   // composition — access via self.base.field
    // ...additional fields
}
```

For polymorphic dispatch (calling parent methods):
```rust
// TS: super.method()
self.base.method()

// TS: instanceof check
// Use match on an enum wrapping variant types, or check via a trait method.
```

msagl's type hierarchy is relatively flat — prefer composition with explicit
`base:` fields over complex trait hierarchies in Phase B.

---

## union_type

TypeScript union types (`A | B | C`) become Rust enums:

```rust
// TS: type Shape = Circle | Rectangle | Line;
enum Shape { Circle(Circle), Rectangle(Rectangle), Line(Line) }

// TS: if (x instanceof Circle) { ... }
if let Shape::Circle(c) = x { ... }
// or:
match x { Shape::Circle(c) => { ... }, _ => {} }
```

For simple `string | null` or `number | undefined`, use `Option<T>`.

For msagl curve types (`ICurve` implemented by `LineSeg`, `Ellipse`, etc.),
the skeleton uses `Box<dyn ICurve>` (trait objects) which is already handled
in the skeleton — do not re-introduce an enum.

---

## optional_chaining

TypeScript `?.` operator chains through potentially-null values:

```rust
// TS: obj?.field
obj.as_ref().map(|o| o.field)
// or if field is Copy:
obj.as_ref().map(|o| o.field).unwrap_or_default()

// TS: obj?.method()
obj.as_ref().map(|o| o.method())

// TS: obj?.field?.nested
obj.as_ref()
   .and_then(|o| o.field.as_ref())
   .map(|f| f.nested)

// TS: arr?.length
arr.as_ref().map(|a| a.len())
```

When the entire chain returns `Option<T>` and the caller expects it,
use `?` inside a function returning `Option`:
```rust
let val = obj?.field?.nested;
```

---

## async_await

TypeScript `async`/`await` maps to Rust async:

```rust
// TS: async function fetchData(): Promise<Data> { ... }
async fn fetch_data() -> Data { ... }

// TS: await somePromise
some_future.await

// TS: Promise.all([a, b, c])
futures::future::join_all([a, b, c]).await
// or tokio::join!(a, b, c)
```

Note: msagl-js has very few async functions (7 in corpus). Most are in
rendering/IO paths. The skeleton uses `tokio` as the async runtime.
For Phase B, keep async signatures if the skeleton has them; otherwise
translate to sync if the TS async was a wrapper with no real awaits.

---

## interface_trait

TypeScript `interface` declarations become Rust `trait` definitions. Classes
that `implement` an interface need a corresponding `impl Trait for Type` block.

```rust
// TS: interface ICurve { length(): number; bbox(): Rectangle; }
pub trait ICurve {
    fn length(&self) -> f64;
    fn bbox(&self) -> Rectangle;
}

// TS: class LineSeg implements ICurve { ... }
pub struct LineSeg { /* fields */ }
impl ICurve for LineSeg {
    fn length(&self) -> f64 { /* ... */ }
    fn bbox(&self) -> Rectangle { /* ... */ }
}
```

**Returning a trait object:** when a function returns "any ICurve", use
`Box<dyn ICurve>` (or `Arc<dyn ICurve>` if shared across threads):
```rust
// TS: function makeCurve(): ICurve { ... }
fn make_curve() -> Box<dyn ICurve> { Box::new(LineSeg::new()) }
```

**Storing a trait object in a struct field:**
```rust
// TS: curve: ICurve
curve: Box<dyn ICurve>
```

The msagl skeleton already defines traits for `ICurve`, `IGeom`, etc.
Do not re-define them — implement them where the skeleton `todo!()`s are.

---

## abstract_class

TypeScript `abstract class` becomes a Rust `trait` (for the interface
contract) paired with a concrete base struct (for shared fields).

```rust
// TS:
// abstract class Shape { abstract area(): number; x: number; y: number; }
// class Circle extends Shape { area() { return Math.PI * r * r; } }

// Rust approach 1 — trait + separate structs (preferred when subclasses
// have little shared state):
pub trait Shape {
    fn area(&self) -> f64;
}
pub struct Circle { pub x: f64, pub y: f64, pub r: f64 }
impl Shape for Circle {
    fn area(&self) -> f64 { std::f64::consts::PI * self.r * self.r }
}

// Rust approach 2 — composition (when subclasses share substantial state):
pub struct ShapeBase { pub x: f64, pub y: f64 }
pub struct Circle { pub base: ShapeBase, pub r: f64 }
// access shared fields via: self.base.x
```

**Abstract methods with a default body:** put the default in the trait with
`fn method(&self) -> T { /* default */ }` and let implementors override.

For msagl, most abstract classes define a geometric contract (area, bbox,
tangent). Prefer the trait approach; put shared fields in a `*Base` struct
and store it as `pub base: FooBase` in each concrete type.

---

## getter_setter

TypeScript `get`/`set` accessor pairs become plain Rust methods. There is no
property syntax in Rust — callers use `obj.width()` and `obj.set_width(v)`.

```rust
// TS: get width(): number { return this._width; }
pub fn width(&self) -> f64 { self.width }

// TS: set width(v: number) { this._width = v; }
pub fn set_width(&mut self, v: f64) { self.width = v; }

// TS: get isEmpty(): boolean { return this.items.length === 0; }
pub fn is_empty(&self) -> bool { self.items.is_empty() }

// TS: get node(): Node | null { return this._node; }
pub fn node(&self) -> Option<NodeId> { self.node }
```

Naming convention: getter `foo()`, setter `set_foo()`. If the getter returns
`bool`, prefix with `is_` or `has_` as appropriate (`is_empty`, `has_children`).

**Computed getters** (no backing field — derived from other data):
```rust
// TS: get perimeter(): number { return 2 * (this.width + this.height); }
pub fn perimeter(&self) -> f64 { 2.0 * (self.width + self.height) }
```

Do NOT add a backing field `_perimeter` — just compute it in the method body.

---

## error_handling

TypeScript `throw` / `try-catch` becomes `Result<T, E>` with the `?` operator.

```rust
// TS: throw new Error("bad input")
return Err(anyhow::anyhow!("bad input"));
// or with a typed error enum:
return Err(MyError::BadInput);

// TS: if (!condition) throw new Error("msg")
if !condition { return Err(anyhow::anyhow!("msg")); }

// TS: try { riskyOp() } catch (e) { handleErr(e) }
match risky_op() {
    Ok(val) => { /* use val */ }
    Err(e)  => { handle_err(e); }
}

// TS: function parse(s: string): number { ... throws ... }
fn parse(s: &str) -> anyhow::Result<f64> { /* use ? to propagate */ }
```

**Propagating errors with `?`:**
```rust
// TS: const val = riskyOp(); // throws if it fails
let val = risky_op()?;   // returns Err early if risky_op returns Err
```

For msagl-js, most `throw` statements are parameter validation guards.
Translate them as `anyhow::bail!("msg")` or return `Err(...)` directly.
The msagl skeleton uses `anyhow::Result` — match that convention.

---

## arena_allocation

Classes that hold fields typed as other user-defined class instances (Node,
Edge, GeomNode, etc.) are candidates for **arena allocation** in Rust.

Arena allocation solves the graph ownership problem: instead of
`Rc<RefCell<Node>>` (which creates nested borrow chains), store all nodes in
a flat `Vec<Node>` and refer to them by `usize` index.

```rust
// TS: class Graph { nodes: Node[]; edges: Edge[]; }
// class Node { outEdges: Edge[]; geom: GeomNode | null; }

// Rust arena pattern:
pub type NodeId = usize;
pub type EdgeId = usize;

pub struct Graph {
    pub nodes: Vec<Node>,   // arena
    pub edges: Vec<Edge>,   // arena
}
pub struct Node {
    pub out_edge_ids: Vec<EdgeId>,   // indices into Graph.edges
    pub geom: Option<GeomNodeId>,    // index into a GeomNode arena
}
pub struct Edge {
    pub source: NodeId,
    pub target: NodeId,
}
```

**Mutating an arena node:**
```rust
// TS: node.someField = value;
graph.nodes[node_id].some_field = value;
```

**Iterating:**
```rust
// TS: for (const e of node.outEdges) { ... }
for &eid in &graph.nodes[node_id].out_edge_ids {
    let edge = &graph.edges[eid];
    // ...
}
```

The msagl skeleton stores graph entities this way. Check the skeleton type
definitions before inventing new storage strategies — do not introduce
`Rc<RefCell<T>>` for types that the skeleton already defines as arena indices.
