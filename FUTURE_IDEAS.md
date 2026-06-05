# Future Ideas & Architecture Vision

Captured 2026-04-24. These are ideas to revisit — not committed plans.

---

## 1. Generic Transpiler Harness

The core of oxidant (LangGraph state machine, SQLite manifest, `claude --print`
subprocess, progressive context disclosure, retry/escalation ladder, FastAPI
dashboard) is entirely language-agnostic. The language-specific parts are thin:

- **Analyzer** — Phase A: AST extraction, dependency graph, node classification
- **Verifier** — Phase B: checks if output is valid (cargo check, vue-tsc, etc.)
- **IdiomDictionary** — markdown file of source→target translation patterns
- **PromptBuilder** — assembles the conversion prompt for one node
- **Assembler** — Phase C/D: post-processing, refinement, integration check

Pull those out as a plugin interface and the harness becomes reusable for any
source→target transpilation pair.

```
┌──────────────────────────────────────────────────────────┐
│                    transpiler-harness                     │
│                                                           │
│  LangGraph state machine                                  │
│  pick → build_context → invoke → verify →                │
│  retry/escalate → supervisor → update_manifest            │
│                                                           │
│  SQLite manifest  |  claude subprocess  |  dashboard      │
│                                                           │
│  Plugin interface:                                        │
│  ┌────────────┐  ┌──────────┐  ┌─────────────────────┐  │
│  │  Analyzer  │  │ Verifier │  │  BehaviorExtractor   │  │
│  │  (Phase A) │  │ (Phase B)│  │  (pairwise tests)    │  │
│  └────────────┘  └──────────┘  └─────────────────────┘  │
│  ┌──────────────────────┐  ┌────────────────────────┐    │
│  │   IdiomDictionary    │  │     PromptBuilder       │    │
│  └──────────────────────┘  └────────────────────────┘    │
└──────────────────────────────────────────────────────────┘

Known plugin implementations:
  oxidant:     TS → Rust     | cargo check  | branch parity
  vuemorphic:  React → Vue 3 | vue-tsc      | React remnant grep
  (future)     Python → Go   | go build     | ?
  (future)     SQL → ORM     | type check   | query result diff
```

The harness would live in a `transpiler-harness` package that oxidant and
vuemorphic both depend on. Each plugin registers an `Analyzer`, `Verifier`,
`PromptBuilder`, and optionally a `BehaviorExtractor`.

---

## 2. Unit Comparison Testing (Three Levels)

Current oxidant verification only proves syntax validity (`cargo check` /
`vue-tsc`). A converted node can compile perfectly and still have different
behavior. Three levels of verification, increasing in strength:

### Level 1: Syntax verification (current)
Compile check — proves output is structurally valid. Says nothing about behavior.

### Level 2: LLM-generated behavioral spec + pairwise tests (most practical)

Before conversion, extract a behavioral specification from the source node:

```
"This component: renders a button labeled {label}, emits 'click' when pressed,
applies class 'disabled' and ignores clicks when prop disabled=true,
shows a spinner when prop loading=true"
```

Store the spec in the manifest (`behavioral_spec` field on NodeRecord).
Generate tests from the spec that can run against BOTH the original and converted
implementation. If both pass, behavioral equivalence is verified.

This is framework-agnostic — the spec is a portable artifact independent of
React or Vue. It also becomes the component's living documentation.

A new `BehaviorExtractor` phase runs before Phase B:
- For each node: call Claude to extract behavioral spec from source
- Generate test stubs for both source and target frameworks
- Store in manifest
- Phase B verification adds a 4th check: run generated tests against output

### Level 3: Execution comparison (strongest, hardest)

For UI components: Playwright renders both original and converted in headless
browser, compares DOM structure / screenshot diff for identical prop inputs.

For pure logic: extract functions, run with identical inputs, assert identical
outputs.

Practical for simple components. Gets hard for components with side effects,
async behavior, or heavy context dependencies.

---

## 3. vuemorphic — React → Vue 3 Fork

See `REACT_TO_VUE_NOTES.md` for full details. Summary:

- Same harness, different plugins
- No skeleton generation (Vue SFCs have fixed structure)
- One node = one component file (not per-function)
- Verification: React remnant grep → vue-tsc (2-5s vs 30s)
- Idiom dictionary covers: useState→ref, useEffect→watch/onMounted,
  useMemo→computed, useContext→Pinia, JSX→template syntax
- First real test case: Claude Design Variation 3 (X-Plane Sim page for Argus)
  converting React output → Vue 3 to drop into the Argus codebase

---

## 4. Manifest Schema Extensions

To support the generic harness and behavioral testing, NodeRecord would gain:

```python
# New fields on NodeRecord
behavioral_spec:     Optional[str]  # LLM-extracted behavioral description
source_test_path:    Optional[str]  # path to generated tests for source impl
target_test_path:    Optional[str]  # path to generated tests for target impl
test_parity_result:  Optional[str]  # PASS / FAIL / SKIPPED
conversion_pair:     Optional[str]  # e.g. "react->vue3", "ts->rust"
```

---

## 5. Plugin Registration Pattern

Each transpilation target registers itself with the harness:

```python
# oxidant/plugins/ts_to_rust.py
@register_plugin("ts->rust")
class TsToRustPlugin(TranspilerPlugin):
    analyzer   = TsToRustAnalyzer()
    verifier   = CargoCheckVerifier()
    prompt     = TsToRustPromptBuilder()
    idioms     = Path("idiom_dictionary.md")
    assembler  = RustAssembler()

# vuemorphic/plugins/react_to_vue.py
@register_plugin("react->vue3")
class ReactToVuePlugin(TranspilerPlugin):
    analyzer   = ReactComponentAnalyzer()
    verifier   = VueTscVerifier()
    prompt     = ReactToVuePromptBuilder()
    idioms     = Path("vue_idiom_dictionary.md")
    assembler  = VueSfcAssembler()
```

CLI becomes:
```bash
transpile phase-a --plugin react->vue3 --source ./my-react-app --target ./my-vue-app
transpile phase-b --plugin react->vue3 --db conversion.db
```

---

## 6. Spec Extraction as a Standalone Tool

The `BehaviorExtractor` concept is independently useful as a documentation tool:
feed it any codebase and it generates behavioral specs for every function/component.
These specs could be used for:
- Code review aids ("here's what this function claims to do")
- Test generation for existing code
- Migration safety net ("before we rewrite this, here's the contract")
- As input to the transpiler to help the LLM understand intent

---

## 7. Potential Future Transpilation Pairs

Ideas for other useful source→target pairs using the same harness:

| Source | Target | Verifier | Notes |
|--------|--------|----------|-------|
| React | Vue 3 | vue-tsc | vuemorphic — immediate use case |
| TS/JS | Python | pytest | API server migrations |
| Python | Go | go build | performance-critical rewrites |
| SQL queries | SQLAlchemy ORM | runtime query | adding ORM to legacy codebase |
| Pandas | Polars | output diff | performance migration |
| REST API | gRPC | proto compile | protocol migration |
| jQuery | vanilla JS | browser lint | modernization |
| Angular | Vue 3 | vue-tsc | similar to React→Vue |

The harness value scales with how many plugins exist. Each new plugin amortizes
the harness infrastructure cost across more use cases.

---

## 8. Open Questions

- Should `transpiler-harness` be a separate PyPI package or just a shared
  internal library between oxidant and vuemorphic?
- How does the behavioral spec handle stateful components with complex
  lifecycle? (Mount → update → unmount sequences)
- Can the spec extraction + test generation be reliable enough to replace
  `vue-tsc` as the primary verifier, or is it always supplementary?
- Playwright comparison: how to handle non-deterministic rendering (animations,
  timestamps, random IDs)? Probably need a snapshot normalization step.
- For the generic harness: how does node granularity vary by language?
  (Rust: per-function, Vue: per-component, Go: per-method, SQL: per-query)
  The manifest schema needs to be flexible enough to handle all of these.
