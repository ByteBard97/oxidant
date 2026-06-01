# React → Vue 3 Fork Notes (vuemorphic)

Observations on adapting oxidant for React component → Vue 3 SFC conversion.
Written after reading the full oxidant source: `agents/context.py`, `verification/verify.py`,
`graph/nodes.py`, `models/db.py`, `idiom_dictionary.md`.

---

## Name suggestion: `vuemorphic`

---

## What stays the same (copy verbatim or rename only)

| File | Change needed |
|------|---------------|
| `graph/graph.py` | None — LangGraph StateGraph topology is identical |
| `graph/nodes.py` | Minor: rename "Rust" references to "Vue"; drop empty-body short-circuit |
| `graph/state.py` | Rename `db_path`, `target_path`, `snippets_dir` — same shape |
| `models/db.py` | Keep NodeRecord schema; drop `return_type`, `parent_class` (not meaningful for components); add `component_name: str` |
| `models/manifest.py` | Keep entirely — SQLite manifest, `claim_next_eligible`, topological sort |
| `agents/invoke.py` | Keep entirely — `claude --print` subprocess invocation is unchanged |
| `serve/` | Keep entirely — FastAPI dashboard works as-is |
| `cli.py` | Keep structure; rename phase commands and drop `generate-skeleton` |

---

## What changes significantly

### Phase A: Analysis (`analysis/`)

**`generate_skeleton.py` → DELETE**

No skeleton needed. Vue SFCs have a fixed structure. The "skeleton" for each
component is just an empty shell written once:

```vue
<template>
  <!-- TODO: VUEMORPHIC: ComponentName -->
</template>

<script setup lang="ts">
// TODO: VUEMORPHIC: ComponentName
</script>
```

The agent replaces these markers, same as the `todo!()` marker pattern in oxidant.

**`extract_ast.ts` → rewrite for React component extraction**

Use `@babel/parser` (handles JSX/TSX) or the TypeScript compiler API to extract:
- Component name + file path
- Import dependency list (which other local `.tsx`/`.vue` components are imported)
- Hooks used (`useState`, `useEffect`, `useMemo`, etc.) → maps to `idioms_needed`
- Props interface name + shape (for context building)
- JSX element count (used in structural parity check — see Verification)
- Whether it uses `useContext` or a global store → flag as complex tier

Node granularity: **one node per component file** (not per function like oxidant).
oxidant processes individual functions; here each `.tsx` file is one node.

**`detect_idioms.ts` → repurpose**

Scan each component for React hook usage patterns and emit `idioms_needed` list:
`["useState", "useEffect_watch", "useMemo", "useContext"]`
etc. Same idiom key format as oxidant — the `build_prompt` function reads these
to pull the relevant sections from `idiom_dictionary.md`.

**`classify_tiers.py` → keep, change heuristics**

Tier classification based on:
- `haiku`: No hooks or only `useState`/`useEffect` with no deps; no context
- `sonnet`: Multiple hooks, computed state, custom hooks, sibling component imports
- `opus`: Global context/store access, complex conditional rendering, `forwardRef`, compound patterns

**`hierarchy.py` → keep, change input**

Instead of TypeScript function call graph, build a component import graph:
`ComponentA.tsx imports ComponentB.tsx` → topological sort so leaf components
(no local imports) are converted first and their converted Vue SFCs are available
as context when converting their parents.

---

### Verification (`verification/verify.py`) — full rewrite

Three checks analogous to oxidant's, same cheapest-first order:

**1. Stub check (instant) — replace `todo!/unimplemented!` grep**

Check for leftover React-isms in the output:
```python
_REACT_REMNANT_RE = re.compile(
    r'\bimport\s+React\b'
    r'|\buseState\b|\buseEffect\b|\buseCallback\b|\buseMemo\b|\buseRef\b|\buseContext\b'
    r'|\bReactDOM\b'
    r'|className=\{'      # JSX dynamic class (not :class)
    r'|onClick=\{'        # JSX event syntax (not @click)
    r'|<>\s*</'           # JSX fragments
)
```
If any match → STUB failure, retry immediately.

**2. Structural parity check (instant) — replaces branch parity**

Count JSX elements in the React source vs `v-if`/`v-for`/`v-show`/`<template`
occurrences in the Vue output. If the React source had conditional/list rendering
and the Vue output has none → suspect incomplete conversion.

```python
_JSX_COND_RE = re.compile(r'\{.*&&\s*<|\bmap\s*\(|ternary|\?\s*<')
_VUE_COND_RE = re.compile(r'v-if|v-for|v-show')
```

More lenient than oxidant's branch parity (60% floor) — maybe 50% floor here
since React and Vue express the same logic with different element counts.

**3. vue-tsc check (~2-5s) — replaces cargo check**

Write the converted `.vue` file, run `vue-tsc --noEmit`, restore original on failure.
Much faster than `cargo check` (~2-5s vs 5-30s). Error parsing is simpler too:
vue-tsc errors are `path/to/Component.vue(line,col): error TS####: message`.

```python
proc = subprocess.run(
    ["vue-tsc", "--noEmit"],
    cwd=target_path,
    capture_output=True, text=True, timeout=30,
)
```

Cascade detection: if the error file is NOT the component we just wrote,
it's a cascade from a previously converted component → same CASCADE status,
retry without penalty.

---

### Context / prompt assembly (`agents/context.py`) — significant rewrite

**`_extract_rust_signature` → DELETE**

No skeleton signature. Instead, pass the React component's TypeScript `Props`
interface as context (extracted by Phase A and stored in the node).

**`_load_dep_snippets` → load already-converted Vue SFCs**

Load the `.vue` files for any imported child components that have already been
converted. Show them as context so the agent knows what props/events those
components expose:

```python
# Already converted child component — show its <script setup> block
# so the agent knows how to pass props to it in the template
```

**`_parse_error_modules` → parse vue-tsc output**

vue-tsc error lines: `src/components/Foo.vue(12,5): error TS2339: ...`
Extract `Foo.vue` → load that component's converted content as unfurled context.

**`_PROMPT_TEMPLATE` — rewrite**

Key differences from oxidant's prompt:
- "Write a Vue 3 SFC file" instead of "implement a Rust function body"
- "Run `vue-tsc --noEmit` to verify" instead of `cargo check`
- No skeleton signature — show React source + Props interface + child component context
- Output format: the entire `.vue` file content (not just a function body)
- `---SUMMARY---` delimiter preserved — agent describes what the component does

```
You are converting a React component to a Vue 3 SFC as part of porting
a React codebase to Vue.

## Your job
1. Read the React source component
2. Write an equivalent Vue 3 SFC using <script setup lang="ts">
3. Write the .vue file using the Edit tool
4. Run vue-tsc --noEmit to verify it type-checks
5. Fix any errors and repeat

## Component to convert: {component_name}
## React source: {react_source_path}
## Vue output target: {vue_output_path}

## React Source
{source_text}

## Rules
- Use <script setup lang="ts"> (Composition API, NOT Options API)
- Use ref() for reactive state, computed() for derived state
- Use watch() / watchEffect() for side effects
- Do NOT use defineComponent() wrapper
- Use Pinia stores instead of useContext()
- Preserve all prop names and types exactly
- className → :class, onClick → @click, onChange → @change
- Map JSX conditional rendering → v-if / v-else / v-show
- Map .map() JSX rendering → v-for with :key
- Children → <slot />

## Converted Child Components (already available)
{child_components_section}

## Idiom Translations
{idiom_section}

{retry_section}
{unfurl_section}

When vue-tsc passes, output the entire .vue file content followed by ---SUMMARY---
and 1-2 sentences describing what this component does.
```

---

### Assembly (`assembly/assemble.py`) — simplify drastically

oxidant's assembly inlines multiple snippets into skeleton `.rs` files.
Here each component is its own complete `.vue` file — no inlining needed.

Assembly = just confirming all `.vue` files exist in `src/components/`.
Or delete this phase entirely; `update_manifest` already writes the file.

---

### Refinement Phase C — replace clippy with ESLint + Prettier

```python
subprocess.run(["npx", "eslint", "--fix", "src/components/"], cwd=target_path)
subprocess.run(["npx", "prettier", "--write", "src/components/"], cwd=target_path)
```

Categorize remaining ESLint warnings: `vue/no-unused-vars`, `@typescript-eslint/*`, etc.

---

### Integration Phase D — replace cargo build with vite build

```python
subprocess.run(["npx", "vue-tsc", "--noEmit"], cwd=target_path)   # type check all
subprocess.run(["npx", "vite", "build"], cwd=target_path)          # bundle check
```

---

## idiom_dictionary.md — full replacement

React→Vue idiom dictionary. Same section format as oxidant (`## idiom_name` headers).

```markdown
## useState
React:  const [value, setValue] = useState(initial)
Vue:    const value = ref(initial)
        // mutate: value.value = newValue

## useEffect_mount
React:  useEffect(() => { setup() }, [])
Vue:    onMounted(() => { setup() })

## useEffect_cleanup
React:  useEffect(() => { return () => cleanup() }, [])
Vue:    onUnmounted(() => { cleanup() })

## useEffect_watch
React:  useEffect(() => { doSomething() }, [dep1, dep2])
Vue:    watch([dep1, dep2], () => { doSomething() }, { immediate: false })

## useCallback
React:  const fn = useCallback(() => { ... }, [deps])
Vue:    // No equivalent needed — just a plain function
        const fn = () => { ... }

## useMemo
React:  const value = useMemo(() => compute(a, b), [a, b])
Vue:    const value = computed(() => compute(a, b))

## useRef_mutable
React:  const ref = useRef(0); ref.current = 5
Vue:    const val = ref(0); val.value = 5

## useRef_dom
React:  const el = useRef<HTMLDivElement>(null); <div ref={el} />
Vue:    const el = ref<HTMLDivElement | null>(null); <div ref="el" />

## useContext
React:  const value = useContext(MyContext)
Vue:    const store = useMyStore()  // Pinia store

## props
React:  function Comp({ foo, bar }: { foo: string; bar: number }) {}
Vue:    const props = defineProps<{ foo: string; bar: number }>()

## emit
React:  prop: onClose: () => void; <button onClick={onClose}>
Vue:    const emit = defineEmits<{ close: [] }>()
        <button @click="emit('close')">

## className
React:  className={`base ${active ? 'active' : ''}`}
Vue:    :class="['base', { active }]"

## conditional_render
React:  {condition && <Component />}
Vue:    <Component v-if="condition" />

## ternary_render
React:  {condition ? <A /> : <B />}
Vue:    <A v-if="condition" /><B v-else />

## list_render
React:  {items.map(item => <Row key={item.id} item={item} />)}
Vue:    <Row v-for="item in items" :key="item.id" :item="item" />

## fragment
React:  <><Child1 /><Child2 /></>
Vue:    Vue 3 supports multiple root elements — just remove the wrapper

## children_slot
React:  {children}; props: { children: ReactNode }
Vue:    <slot />

## children_named_slot
React:  {props.header}; props: { header: ReactNode }
Vue:    <slot name="header" />

## forwardRef
React:  const Comp = forwardRef((props, ref) => ...)
Vue:    defineExpose({ methodName, propertyName })

## style_dynamic
React:  style={{ color: active ? 'red' : 'blue' }}
Vue:    :style="{ color: active ? 'red' : 'blue' }"

## event_handler
React:  onClick={handler}  onChange={e => setValue(e.target.value)}
Vue:    @click="handler"   @change="value = ($event.target as HTMLInputElement).value"
```

---

## Key simplifications vs oxidant

1. **No skeleton generation** — the biggest complexity cut. Phase A is just
   component discovery + dependency graph + idiom detection.

2. **Faster verification** — vue-tsc takes 2-5s vs cargo's 5-30s. The stub
   check (React remnants grep) catches most failures instantly.

3. **One node = one file** — oxidant processes individual functions within
   files. Here each component file is one atomic unit. Simpler manifest,
   simpler assembly.

4. **No clone directories for parallel workers** — each worker writes to a
   different `.vue` file; no skeleton file sharing. Safe to parallelize
   without clones.

5. **No branch parity** — React and Vue express equivalent logic with
   different syntax. Use a looser structural check (v-if/v-for presence)
   rather than raw branch count.

---

## Test case: Claude Design output

The first real-world test will be the Variation 3 X-Plane Sim page from
Claude Design, converted from React to Vue 3 to drop into Argus.
This gives us a known-good React source and a known target environment
(Argus: Vue 3 + Tailwind v4 + Pinia).
