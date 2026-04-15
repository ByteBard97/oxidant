# Transpiling TypeScript to Rust via agentic harness: the state of the art

**Your approach — AST-driven dependency ordering, skeleton-first translation, and tiered LLM routing through LangGraph — aligns with the emerging consensus in 2025–2026 research, but no system has attempted it for TypeScript-to-Rust at the scale of MSAGL-JS.** The closest analogues are ORBIT and His2Trans (C-to-Rust agentic systems with dependency-aware scheduling), Skel (skeleton-first Python-to-JavaScript with formal decomposition guarantees), and vjeux's recent 100K-line Pokemon Showdown JS-to-Rust port using Claude Code. The field has exploded: at least 15 new C-to-Rust tools appeared in 2024–2025 alone, but **no mature general-purpose TypeScript-to-Rust transpiler exists**, and repository-level translation from dynamic to static languages remains the hardest unsolved problem, with best-case success rates under 10% on benchmarks like RepoTransBench.

---

## The C-to-Rust pipeline is now crowded; everything else is frontier

The C-to-Rust translation space has reached a level of maturity unmatched by any other language pair targeting Rust. Beyond the tools you already know (C2Rust, ENCRUST, SACTOR, EvoC2Rust, RustMap), a wave of new systems appeared in 2024–2026:

**ORBIT** (April 2025) is the most architecturally relevant to your project. It's an autonomous agentic framework that builds a dependency-aware translation graph, deploys multiple specialized agents, and iterates through verification loops. It achieves **100% compilation and 91.7% test success** on CRUST-Bench, and handles 70% of the hardest DARPA TRACTOR programs. Its dependency-graph-driven orchestration directly parallels your topological ordering approach.

**Rustine** (late 2025) demonstrated that fully automated pipelines can be remarkably cheap: it translates C repositories of up to 13,200 lines at an average cost of **$0.48 per repository** using DeepSeek-V3/R1, achieving 100% compilability and 87% assertion-level equivalence across 23 projects. **His2Trans** (early 2026) introduced a topological scheduler dispatching parallel translation tasks from a project-level skeleton graph, achieving 99.75% incremental compilation pass rate — the closest architectural parallel to your ts-morph dependency graph approach.

**Syzygy** took a different route: dual code-test translation guided by dynamic analysis, successfully translating Zopfli (3,000 lines of C) to ~4,500 lines of Rust, though at **~$800 in API costs** using GPT-4o. **VERT** pioneered formal verification by compiling C to WebAssembly, lifting to Rust via rWasm as an oracle, then using LLMs to generate idiomatic candidates verified through property-based testing and bounded model checking with Kani. **LAC2R** applied Monte Carlo Tree Search to organize intermediate translation steps, outperforming C2SaferRust on CoreUtils benchmarks. **C2SaferRust** itself (January 2025) introduced a neurosymbolic pipeline that uses C2Rust as a preprocessing step, then decomposes output into slices for LLM refinement, reducing raw pointers by 38%.

For non-C language pairs, Amazon's work on **Go-to-Rust** (PLDI 2025) is the most rigorous: a hybrid approach combining predefined feature mapping rules with Claude 3, translating real-world codebases up to 9,700 lines with **73% of functions validated for I/O equivalence**. **AlphaTrans** and its successor **TRAM** tackle repository-level Java-to-Python translation using GraalVM's polyglot runtime for cross-language validation, achieving 25–43% functional equivalence. **RepoTransBench** (2024) established the sobering baseline: across 13 language pairs and 1,897 repositories, the best method achieves only **32.8% success**, and dynamic-to-static language translation specifically scores **under 10%**.

---

## Skeleton-first with dependency ordering is the winning architecture

Your plan to generate stubs first and fill implementations in topological order matches the architecture that has proven most effective across the literature. Three systems formalize this approach:

**Skel** (PLDI 2025) provides the strongest theoretical foundation. It translates Python to JavaScript by first generating a program skeleton retaining lexical scopes, function signatures, and symbol tables while abstracting code fragments as placeholders. An Execution-Order Translation loop then synthesizes each placeholder using LLMs. The key insight is "sound decomposition": if each fragment is correctly translated, the whole translation is provably correct. Skel achieves **95% automatic translation** with GPT-4 on programs exceeding 1,000 lines.

**EvoC2Rust** (2026) applies this to C-to-Rust specifically: it decomposes C projects into functional modules, transforms definitions and macros, generates type-checked function stubs forming a compilable Rust skeleton with `unimplemented!()` placeholders, then incrementally translates functions in dependency order. It outperforms the strongest LLM baseline by **17.24% in syntax accuracy** and 14.32% in semantic accuracy.

**His2Trans** (2026) adds build-trace-based skeleton reconstruction with a topological scheduler that dispatches parallel translation tasks. Successfully translated modules use their compiled artifacts to unlock dependents for scheduling. When LLM translation fails after exhausting repair attempts, it falls back to C2Rust-generated unsafe code as a safety net — a pragmatic design choice worth considering for your system.

**CodePlan** (Microsoft Research, 2024) is the most complete framework for using dependency graphs to drive LLM code changes at repository scale. It builds dependency graphs using tree-sitter AST parsing and Jedi static analysis, creates a plan graph (DAG) with dependency and cause edges, and employs incremental dependency analysis with change-may-impact propagation. Though designed for refactoring rather than cross-language translation, its architecture directly informs the kind of system you're building.

Google's internal migration system (FSE 2025) validates the hybrid AST+LLM approach at massive scale: 39 migrations, 595 code changes, 93,574 edits, with **74.45% generated by LLM** and developers reporting 50% time reduction. Their key principle: "Many code migrations can be split into discrete steps where each step can either be LLM generation, LLM introspection, or traditional AST-based techniques." Your ts-morph integration fits this pattern exactly.

---

## Agentic harnesses and tier routing are production-ready building blocks

The ecosystem for wrapping LLM coding agents in larger orchestration systems has matured significantly. **Anthropic's Claude Agent SDK** (formerly Claude Code SDK) exposes Claude Code's agentic capabilities as a Python/TypeScript library, supporting subagents running in isolated conversations with scoped tool access, parallel execution, session persistence, and budget controls via `max_budget_usd`. This is the natural substrate for your LangGraph orchestration layer.

For tier routing specifically, the **Triage** paper (April 2026) directly validates your Haiku/Sonnet/Opus approach. It routes software engineering tasks to cost-effective LLM tiers using code health signals — cyclomatic complexity, coupling, file size, duplication across **25+ factors**. Clean code routes to cheaper models; messy, complex code requires frontier models. **RouteLLM** (UC Berkeley/LMSYS) achieves **40–85% cost reductions** while maintaining 95% of GPT-4 performance using four different router architectures. **Morph Router**, trained on millions of coding prompts, reports **40–70% cost reduction** with under 2% quality loss, routing across Easy (Haiku, $0.25/M tokens), Medium (Sonnet, $3/M), and Hard (Opus, $15/M) tiers.

Several open-source projects demonstrate Claude Code as a subprocess. **OpenClaw** turns Claude Code CLI into a programmable, headless coding engine with a "Council system" coordinating multiple agents across different LLM engines. **Claude Code Workflow Orchestration** provides multi-step workflow orchestration with automatic task decomposition and parallel agent execution. **Wshobson/agents** packages 182 specialized Claude Code agents with 16 workflow orchestrators supporting model routing via `--model opus/sonnet`.

For LangGraph specifically applied to code: **Aviator** documented a Java-to-TypeScript migration case study using LangChain as the orchestration layer with multiple specialized agents (reader, planner, migrator), vector databases for context memory, and CI/CD validation. LangGraph's durable execution, human-in-the-loop state inspection, and composable subgraph architecture make it well-suited for the checkpoint-and-resume workflow your translation pipeline needs.

Other agentic coding frameworks worth monitoring: **OpenHands** (65K+ GitHub stars, top SWE-bench performer) explicitly markets codebase modernization and supports COBOL-to-Java migration. **Aider** maps entire codebases using tree-sitter RepoMap and offers an Architect mode with two-model workflows. **AutoCodeRover** uses AST-aware program structure search with spectrum-based fault localization. **GPT-Migrate** attempts full codebase migration with Docker-based isolation but is experimental and reportedly expensive.

---

## Verification requires a layered strategy, not a single approach

No single verification method is sufficient. The literature converges on a layered approach combining multiple techniques at different granularities:

**Compiler-in-the-loop** is the minimum viable verification. Every successful system uses the target compiler as the first gate. For Rust specifically, the compiler's strictness is an advantage — errors caught at compile time rather than runtime make Rust paradoxically well-suited for LLM-assisted development. Iterative compiler feedback loops improve translation success from 54% to 80% in SafeTrans's experiments.

**I/O equivalence testing** is the standard for functional correctness. Amazon's Oxidizer instruments source functions to log inputs/outputs during test execution, then creates Rust unit tests from collected snapshots. Syzygy mines specifications via dynamic analysis. The practical challenge: this only exercises code paths covered by existing tests (typically **56% average method coverage**).

**Property-based testing and fuzzing** extend coverage beyond fixed test suites. VERT uses Proptest for randomized differential testing between a WebAssembly oracle and LLM-generated Rust, improving verification from 31% to 54%. FLOURINE applies differential fuzzing with 5-minute timeouts per function. MatchFixAgent specifically synthesizes inputs targeting cross-language semantic differences — for instance, detecting that Rust's `.len()` counts bytes while Python counts characters by generating emoji test inputs.

**Formal verification** provides the strongest guarantees but limited applicability. **Kani** (AWS's bounded model checker for Rust) checks for undefined behavior, panics, and arithmetic overflows. **Miri** dynamically checks unsafe code for Stacked Borrows violations — essential if your translated code includes any `unsafe` blocks. **LLMLift** (NeurIPS 2024) generates both translations and proofs of correctness, but currently only targets domain-specific languages.

**Detecting LLM simplification** remains an open problem. The HalluCode benchmark categorizes hallucination types: behavior-conflicting code, useless statements, redundant logic, and API hallucinations. **FORGE** (2026) achieves 100% precision and 87.6% recall for API-level hallucinations by validating ASTs against a knowledge base. The Berkeley position paper argues that testing alone cannot detect semantic correctness issues — formal compositional reasoning is necessary for complex translations.

The **Self-Debugging** approach (ICLR 2024) showed up to 12% improvement on TransCoder benchmarks through "rubber duck debugging" where the LLM explains its own code. However, "Is Self-Repair a Silver Bullet?" (also ICLR 2024) demonstrated that self-repair gains are often modest when accounting for compute cost, and that spending budget on diverse initial samples frequently outperforms extensive repair of a single attempt. This suggests your tier routing should consider generating multiple independent translations at lower tiers before escalating to Opus for repair.

---

## MSAGL-JS presents several Rust-hostile patterns

MSAGL-JS's architecture contains patterns that are specifically difficult to translate to Rust, and understanding these will be critical for your system's success.

**Bidirectional graph references** are the most fundamental challenge. MSAGL's `Node` objects reference their `Edge` objects via `inEdges` and `outEdges`, while `Edge` objects reference their source and target `Node` objects. This mutual reference pattern directly violates Rust's ownership model. The idiomatic Rust solutions are arena-based allocation (the `typed-arena` or `slotmap` crate, where nodes and edges are indices into a shared arena), `Rc<RefCell<T>>` for single-threaded reference counting, or `petgraph`'s approach of storing nodes and edges as indices into vectors. Your system should detect this pattern early and apply a consistent strategy globally rather than letting the LLM make ad-hoc decisions per function.

**Deep class inheritance** from MSAGL's `Entity` → `GeometryObject` → `Node`/`Edge`/`Label` hierarchy has no direct Rust equivalent. The three standard translation patterns are: enums for closed hierarchies (when all variants are known at compile time), trait objects (`dyn Trait`) for open extensibility, and struct composition with a shared base field. For MSAGL, the Entity-Attribute system likely maps best to a combination: an `Entity` trait with a `GeometryAttributes` associated type, plus an enum for the concrete node/edge/label variants.

**Mutable shared state during layout** is pervasive. Layout algorithms mutate node positions, edge routes, and boundary curves in-place while referencing shared graph state. Rust requires either single-ownership mutation, interior mutability (`RefCell`), or careful lifetime management. For computational geometry algorithms like Sugiyama layout, the pragmatic approach is often to structure computation as transformation pipelines: read input → compute → write output, rather than mutating shared state.

**TypeScript's `null | undefined` duality** maps to Rust's `Option<T>`, but MSAGL uses optional chaining (`obj?.prop`) extensively. Each instance requires either `.map()`, `if let Some(x)`, or the `?` operator. The `number` type must be resolved to specific Rust numeric types (`f64` for coordinates, `usize` for indices, `i32` for counts), and TypeScript's silent numeric coercion has no Rust equivalent.

**Async patterns**, if present in MSAGL's rendering code, face the lazy-vs-eager future difference: TypeScript Promises execute immediately while Rust Futures do nothing until polled. Cancellation semantics differ fundamentally — dropping a Rust future cancels it, while TypeScript promises cannot be cancelled. Recursive async functions require `Box::pin()` in Rust.

No complete Sugiyama-scheme layout library exists in Rust. **petgraph** provides graph data structures and basic algorithms but no visual layout. **fdg** implements only Fruchterman-Reingold force-directed layout. A successful MSAGL translation would fill a significant gap in the Rust ecosystem.

---

## Vjeux's Pokemon Showdown port is your closest real-world precedent

In April 2026, Christopher Chedeau (vjeux, creator of Prettier) publicly documented porting **100,000 lines of JavaScript to Rust using Claude Code over 4 weeks**, generating 5,000 commits with ~$200 in API fees. This is the most directly relevant precedent for your project, and his lessons are invaluable:

**The naive approach failed.** Simple prompts asking Claude to "port this file to Rust" produced code with wrong abstractions, hardcoded values, and shortcuts. Claude repeatedly tried to "improve" code during translation, introducing bugs despite explicit instructions for line-by-line translation. The LLM's tendency to optimize or simplify is a persistent, well-documented failure mode across all studies.

**The borrow checker was the primary obstacle.** Pokemon/Battle objects had circular references that don't map to Rust's ownership model — the same pattern MSAGL's graph nodes and edges exhibit. Vjeux's solution required manual architectural decisions about ownership that the LLM couldn't make autonomously.

**Results were impressive but imperfect.** The final system had 80 divergences out of 2.4 million battle seeds (0.003% error rate), with the Rust version significantly faster than JavaScript. But Hacker News commenters noted that Claude's "self-reflection" about its own errors is itself often hallucinated — the model predicts plausible explanations rather than accurately diagnosing root causes.

**Rust's compiler as guardrail was a recurring theme.** Multiple practitioners and researchers observed that Rust is paradoxically well-suited for LLM-assisted development: the strict compiler catches drift and inconsistencies that would be silent bugs in dynamically typed languages. This supports your approach of using compiler feedback in the refinement loop.

Other major migration case studies reinforce selective, incremental strategies. Figma achieved **10x performance improvement** rewriting only their multiplayer syncing engine from TypeScript to Rust. Discord eliminated GC-caused latency spikes by rewriting their Read States service from Go to Rust. Cloudflare replaced NGINX with Rust-based Pingora, achieving **70% less CPU and 67% less memory**. But Prisma's reverse migration — from Rust back to TypeScript — demonstrates that FFI boundary costs can negate Rust's performance advantage when serialization overhead dominates.

---

## The DARPA TRACTOR program is active but results are limited

DARPA's TRanslating All C TO Rust (TRACTOR) program, announced July 2024 with ~$14 million in funding, aims to automate C-to-Rust translation at the quality of a skilled Rust developer. The program is managed by Dan Wallach, with MIT Lincoln Laboratory handling evaluation.

Only **one primary contract was awarded**, to a university consortium using "Verified Lifting" (MetaLift) — an approach that searches for matching idioms in the target language and uses proof techniques to verify equivalence. Seven teams are reportedly involved. DARPA released a **test battery of 150 C programs** that has become a de facto benchmark: ORBIT evaluates against it, achieving ~70% on the hardest programs, competitive with the six official performer systems.

Wallach has noted publicly: "You can ask an LLM to translate C to Rust and something comes out, often very good, but not always." DARPA experimented with translating a C-based AV1 implementation to Rust and found it still required significant manual work. The consensus among observers is that even partial automation would significantly reduce cost and improve security outcomes.

---

## Known failure modes your system must handle

The literature identifies consistent failure patterns across all LLM code translation systems:

**Semantic errors despite syntactic correctness** are the dominant failure mode. Studies report correct translation rates ranging from **2.1% to 47.3%** across LLMs. Code compiles but behaves incorrectly because LLMs optimize local token likelihood, not global semantic preservation. The "Lost in Translation" study (ICSE 2024) found that **38.5% of failures stem from lack of source comprehension** and 41.4% from ignoring cross-language semantic discrepancies.

**Code "improvement" during translation** is the most insidious pattern. LLMs consistently attempt to refactor, optimize, or simplify code during translation rather than performing faithful conversion. Vjeux documented this extensively, and it appears across all studies. Your system should include AST-level diffing to detect when the LLM has added, removed, or restructured logic beyond what the translation requires.

**Repair loops and local minima** occur when iterative refinement gets stuck. The LLM produces the same or similar incorrect code repeatedly. The evidence suggests that restarting from scratch often outperforms extended repair — your tier routing could implement a "restart at higher tier" strategy after N failed repair attempts at a lower tier.

**Class-level translation degrades dramatically** compared to function-level translation across all LLMs. This validates your AST-node-level approach: translating individual functions and type definitions rather than entire files preserves more semantic accuracy.

**Feature mapping gaps** are predictable and systematic. The Amazon PLDI 2025 paper found that LLMs are "unreliable when translating features that do not have a direct mapping." For TypeScript-to-Rust, the predictable gaps are: class inheritance, null/undefined handling, union types, dynamic object manipulation, prototype patterns, and error handling (try/catch to Result). Pre-defining translation rules for these patterns and injecting them as context will significantly improve LLM accuracy.

**Human intervention is consistently required** for ownership model design (who owns shared mutable state), module boundary decisions, build system configuration, and making code genuinely idiomatic. Amazon's best approach still needs manual review for 27% of functions. The fish shell project migrated C++ to Rust entirely manually, citing the need for idiomatic code.

---

## Gaps your approach fills and risks to watch

**What's novel in your approach:** No existing system combines TypeScript-specific AST analysis (via ts-morph), dependency-graph-driven topological ordering, skeleton-first stub generation, and Haiku/Sonnet/Opus tier routing in a single pipeline for cross-language translation. The closest systems are ORBIT and His2Trans for C-to-Rust, and Skel for Python-to-JavaScript, but none target the TypeScript-to-Rust pair or use ts-morph's rich type-aware AST. Your approach would be the first agentic harness specifically designed for translating a garbage-collected, dynamically-dispatched OOP language to Rust at repository scale.

**Gaps to fill:** No existing tool addresses the global architectural decisions that TypeScript-to-Rust translation requires — particularly the choice of graph representation strategy (arena vs. Rc<RefCell> vs. index-based). Your system should make these decisions once, encode them as translation rules, and enforce consistency across all generated code. Consider implementing a "translation rulebook" that the LLM receives as context, similar to Amazon's feature mapping approach.

**Risks to monitor:** RepoTransBench's finding that dynamic-to-static language translation succeeds under 10% of the time should calibrate expectations. MSAGL's bidirectional graph references, deep inheritance, and pervasive mutable shared state represent the hardest patterns in the literature. Your system's fallback strategy — what happens when the LLM cannot produce correct code after N attempts — should be planned from the start. His2Trans's approach of falling back to unsafe code (analogous to keeping TypeScript via WASM) is pragmatic. The Prisma reverse-migration cautionary tale suggests carefully benchmarking whether FFI boundaries between remaining TypeScript and translated Rust code negate performance gains.

**Immediate tactical recommendations:** Implement FORGE-style AST validation to detect API hallucinations. Use differential fuzzing (FLOURINE's approach) rather than only fixed test suites. Consider VERT's WebAssembly oracle strategy — compile both TypeScript and Rust to WASM and compare outputs. Start with MSAGL's leaf-node utility functions and geometry primitives, which have the simplest ownership patterns, before tackling the graph data structures. And instrument your pipeline to detect the "improvement during translation" failure mode — AST structural comparison between source and target can flag unexpected additions or deletions of control flow.