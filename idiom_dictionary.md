# Idiom Dictionary — msagl-js → Rust

MSAGL-specific guidance for each TypeScript pattern detected in the corpus.
Sections are keyed exactly to idiom names used in `conversion_manifest.json`.

---

## mutable_shared_state

TypeScript class properties are mutable by default and shared freely via
object references. In the msagl-js skeleton, classes use `Rc<RefCell<T>>`
for shared graph nodes. Inside method bodies translate property mutation as:

```rust
// TS: this.someField = value;
self.some_field = value;           // if self is &mut Self

// TS: node.someField = value;     // where node is a shared ref
node.borrow_mut().some_field = value;
```

For local mutable variables, use `let mut`:
```rust
// TS: let count = 0; count++;
let mut count = 0i32; count += 1;
```

Do NOT reach for `RefCell` for local variables — only for shared heap nodes.

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
