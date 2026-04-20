# msagl-rs — Oxidant Agent Context

You are translating TypeScript functions from `msagl-js` into Rust.

## Your Task

You will receive a prompt describing:
- The TypeScript source file and line range to translate
- The Rust skeleton file containing a `todo!()` placeholder where your implementation goes
- How to run `cargo check` to verify compilation

Read both files, implement the function using Edit, run cargo check to verify, fix errors, repeat.
When cargo check passes, output the final function body text (no fences, no explanation).

**Critical rules:**
- Implement ONLY the function marked with the `todo!("OXIDANT: ...")` placeholder in the prompt
- Do NOT change any other function, type, or constant in the skeleton file
- **OUTPUT PURE ASCII RUST CODE ONLY. NO EXCEPTIONS.**
- Do NOT use backticks (`) anywhere — not in comments, not in strings, nowhere
- Do NOT use em-dashes (--), en-dashes, curly quotes, or ANY non-ASCII character
- Every character in your Rust output must be standard ASCII (codes 0-127)
- Violations break compilation for every other function in the file
- Do NOT use `todo!()`, `unimplemented!()`, or `panic!()`
- Translate semantically faithfully -- match every branch in the TypeScript
- Do NOT simplify, optimize, or restructure
- Use only the approved crates listed below

## Approved Crates

```
slotmap, petgraph, nalgebra, thiserror, itertools, ordered-float, serde, serde_json
```

## Architectural Decisions

- **graph_ownership_strategy**: `arena_slotmap` — graph entities (Node, Edge, GeomNode, GeomEdge)
  are stored in flat `Vec` or `SlotMap` arenas and referenced by index/key. Do NOT use
  `Rc<RefCell<T>>` for these. Check the skeleton types before inventing new storage strategies.
- **error_handling**: `thiserror` — propagate errors with `?`, return `Result<T, MyError>`.

## Key Idiom Translations

### mutable_shared_state
```rust
// TS: this.someField = value;
self.some_field = value;

// TS: let count = 0; count++;
let mut count = 0i32; count += 1;
```
Do NOT reach for `RefCell` for local variables or `&mut self` fields.
`Rc<RefCell<T>>` is only appropriate for non-graph shared state with genuine shared ownership.

### null_undefined
```rust
// TS: if (x == null)       →  if x.is_none()
// TS: if (x != null)       →  if let Some(val) = x
// TS: x ?? defaultVal      →  x.unwrap_or(default_val)
// TS: x?.method()          →  x.as_ref().map(|v| v.method())
// TS: return null;         →  return None;
// TS: x!                   →  x.unwrap()
```

### dynamic_property_access
```rust
// TS: map[key]             →  map.get(&key)           // Option<&V>
// TS: arr[i]               →  arr[i as usize]
// TS: obj[key] = val       →  map.insert(key, val);
// TS: delete obj[key]      →  map.remove(&key);
```

### optional_chaining
```rust
// TS: obj?.field           →  obj.as_ref().map(|o| o.field)
// TS: obj?.field?.nested   →  obj.as_ref().and_then(|o| o.field.as_ref()).map(|f| f.nested)
```

### array_method_chain
```rust
// TS: arr.map(x => x*2)           →  arr.iter().map(|x| x * 2.0).collect::<Vec<_>>()
// TS: arr.filter(x => x > 0)      →  arr.iter().filter(|&&x| x > 0.0).copied().collect()
// TS: arr.find(x => x.id == t)    →  arr.iter().find(|x| x.id == t)    // Option<&T>
// TS: arr.some(x => cond)         →  arr.iter().any(|x| cond)
// TS: arr.every(x => cond)        →  arr.iter().all(|x| cond)
// TS: arr.forEach(x => { ... })   →  for x in &arr { ... }
// TS: arr.reduce((a,x)=>a+x, 0)  →  arr.iter().fold(0.0, |a, &x| a + x)
```

### map_usage
```rust
// TS: new Map<string, Foo>()  →  HashMap::<String, Foo>::new()
// TS: map.set(k, v)           →  map.insert(k, v);
// TS: map.get(k)              →  map.get(&k)         // Option<&V>
// TS: map.has(k)              →  map.contains_key(&k)
// TS: map.delete(k)           →  map.remove(&k);
// TS: map.size                →  map.len()
// TS: for (const [k,v] of m)  →  for (k, v) in &map { ... }
```

### set_usage
```rust
// TS: new Set<T>()    →  HashSet::<T>::new()
// TS: set.add(v)      →  set.insert(v);
// TS: set.has(v)      →  set.contains(&v)
// TS: set.delete(v)   →  set.remove(&v);
// TS: set.size        →  set.len()
```

### number_as_index
```rust
// TS: arr[i]   where i is number  →  arr[i as usize]
// TS: arr.length                   →  arr.len()
// TS: for (let i=0; i<n; i++)      →  for i in 0..n { ... }
```

### closure_capture
```rust
// TS: const f = (x: number) => x * 2;              →  let f = |x: f64| x * 2.0;
// TS: arr.filter(n => n > threshold)               →  arr.iter().filter(|&&n| n > threshold)
// For mutation: use a for loop, not a closure with &mut capture
// Stored callbacks: Box<dyn Fn()> or Box<dyn FnMut()>
```

### getter_setter
```rust
// TS: get width(): number         →  pub fn width(&self) -> f64 { self.width }
// TS: set width(v: number)        →  pub fn set_width(&mut self, v: f64) { self.width = v; }
// TS: get isEmpty(): boolean      →  pub fn is_empty(&self) -> bool { self.items.is_empty() }
```

### class_inheritance / super
```rust
// TS: super.method()              →  self.base.method()
// TS: class Child extends Parent  →  struct Child { base: Parent, ... }
```

### generator_function
```rust
// TS: function* edges() { for (e of ...) yield e; }
// Rust: return Vec or impl Iterator
pub fn edges(&self) -> impl Iterator<Item = EdgeId> + '_ { self.edge_ids.iter().copied() }
```

### error_handling
```rust
// TS: throw new Error("msg")     →  return Err(anyhow::anyhow!("msg"));
// TS: try { f() } catch (e) {}  →  match f() { Ok(v) => ..., Err(e) => ... }
// Propagate with:                   let v = risky_op()?;
```

### arena_allocation
Graph entities are stored in `Vec` arenas, referenced by `usize` index:
```rust
pub type NodeId = usize;
pub struct Graph { pub nodes: Vec<Node>, pub edges: Vec<Edge> }
// Mutate: graph.nodes[node_id].some_field = value;
// Iterate: for &eid in &graph.nodes[node_id].out_edge_ids { let e = &graph.edges[eid]; }
```
Do NOT introduce `Rc<RefCell<T>>` for types the skeleton already defines as arena indices.

### static_members
```rust
// TS: static create(): Foo      →  pub fn create() -> Self { ... }    // Foo::create()
// TS: static readonly PI = 3.14 →  const PI: f64 = 3.14;
// TS: mutable static            →  thread_local! { static X: RefCell<T> = RefCell::new(...); }
```

### union_type
```rust
// TS: type Shape = Circle | Rect  →  enum Shape { Circle(Circle), Rect(Rect) }
// TS: if (x instanceof Circle)    →  if let Shape::Circle(c) = x
// TS: string | null               →  Option<String>
```

### interface_trait
```rust
// TS: interface ICurve { length(): number; }
pub trait ICurve { fn length(&self) -> f64; }
// Returning trait object: Box<dyn ICurve>
// The skeleton already defines traits — implement the todo!() blanks, don't redefine.
```
