# **Structural Synthesis and Agentic Orchestration for Automated TypeScript to Rust Transpilation**

The evolution of software engineering toward memory-safe systems has necessitated a paradigm shift in codebase migration, moving beyond naive syntactic translation toward deep semantic reconstruction. The transition from TypeScript, a garbage-collected language with a sophisticated but unsound type system, to Rust, a systems language governed by strict ownership and linear logic, presents a uniquely complex challenge. While the industry has long relied on rule-based transpilers for language pairs such as C and C++, the current frontier involves agentic harnesses that leverage Abstract Syntax Tree (AST) analysis, topological dependency resolution, and Large Language Model (LLM) orchestration to produce idiomatic, verifiable, and performant code.

## **The DARPA TRACTOR Initiative and the Mandate for Memory Safety**

The impetus for large-scale automated migration has been significantly accelerated by government-led initiatives aimed at securing critical infrastructure. Central to this movement is the Defense Advanced Research Projects Agency (DARPA) "Translating All C to Rust" (TRACTOR) program. Launched in mid-2024, TRACTOR represents a systematic R\&D effort to automate the conversion of legacy C codebases into memory-safe Rust.1 In July 2025, a multi-institution team comprising researchers from the University of Wisconsin-Madison, UC Berkeley, the University of Edinburgh, and UIUC received a $5 million award to spearhead these automation efforts.2

The TRACTOR program's objective is not merely functional equivalence but the generation of "good Rust"—code that is free of undefined behavior (UB) and idiomatic in its handling of memory.2 This initiative reflects a broader consensus among regulatory bodies. The June 2025 joint report from CISA and the NSA cited Google’s Android data—which showed a ![][image1] reduction in memory safety vulnerability density in Rust code compared to C/C++—as primary evidence for the effectiveness of memory-safe languages.3 This has created a "Great Refactor" environment where industry and academia are collaborating to address the challenges of scale and semantic fidelity in migration.1

Despite the focus on C-to-Rust, the lessons and tools emerging from TRACTOR are directly applicable to higher-level migrations, such as the transpilation of graph layout libraries like MSAGL-JS. The fundamental problems identified in TRACTOR—namely, determining array bounds, resolving pointer arithmetic into slices, and mapping object-oriented patterns to Rust's ownership model—are the same hurdles faced when converting TypeScript’s complex, often cyclic, heap-allocated graphs into safe Rust.2

## **State-of-the-Art in Automated Code Transpilation**

The current landscape of code translation is characterized by a transition from rule-based transpilers to hybrid, agent-centric systems. Traditional tools like C2Rust utilize a clang frontend to produce functionally identical Rust, but the output is often "unsafe" and non-idiomatic, essentially re-implementing C semantics using Rust's unsafe blocks.2 This produces code that is difficult for human developers to maintain and fails to leverage Rust's inherent safety guarantees.

In contrast, recent LLM-based approaches attempt to capture program intent rather than just syntax. These systems are evaluated on benchmarks like CRUST-Bench and the TRACTOR battery, with emerging tools demonstrating superior performance in both compilation success and functional correctness.1

### **Comparative Performance Metrics for Rust Migration Tools**

| System | Primary Strategy | Compilation Success Rate | Functional Success (Tests) | Safety Level (Unsafe Blocks) |
| :---- | :---- | :---- | :---- | :---- |
| **C2Rust** | Rule-based / AST-to-AST | 62.5% | 20.8% | High (69.6% unsafe) |
| **CRUST-Bench** | Naive LLM (Single-step) | 45.8% | 25.0% | Moderate |
| **ACToR** | Multi-agent (Translator \+ Discriminator) | 100% | 90.0% | Zero (Fully Safe) |
| **ORBIT** | Expert-Agentic Orchestration | 100% | 91.7% | Near-Zero (0.06%) |
| **Rustine** | Two-tier Prompting \+ Delta Debugging | 100% | 87.0% | Low |
| **SACTOR** | Two-phase (Unidiomatic to Idiomatic) | High | 78% (on libogg) | Low |

1

The data indicates that agentic systems like ACToR and ORBIT substantially outperform both naive LLM prompting and rule-based transpilers. ORBIT, in particular, achieves competitive performance on the hardest programs in the DARPA TRACTOR benchmark, with a pass rate of approximately 70% on programs exceeding ![][image2] lines of code.1 These systems move beyond file-by-file translation, adopting project-wide orchestration that understands the broader structural context of the codebase.

## **AST-Driven Orchestration and Project-Level Decomposition**

A primary failure mode in early LLM-based translation was the lack of repository-wide context. Large language models operate on fixed context windows, making it impossible to process dozens of files and thousands of lines of code in a single generation step.5 To solve this, researchers have developed "program-structure-aware" approaches that decompose the project into smaller, manageable units—such as individual functions, methods, or AST nodes—and translate them in a specific order guided by a dependency graph.10

### **Dependency-Aware Topological Scheduling**

The "His2Trans" framework exemplifies the importance of topological sorting in code migration. It constructs a "Project-Level Skeleton Graph" using static analysis and build traces to establish a strictly typed structure and dependency map.10 This graph is transformed into a linear, bottom-up execution sequence using a topological scheduler. By prioritizing leaf nodes—functions whose dependencies are already resolved—the system ensures that when a higher-level function is being translated, the LLM has access to the already-translated Rust signatures of its callees.10

This strategy addresses the "call-site obligation" problem. In a naive translation, the LLM must simultaneously produce a type-correct function body and a signature compatible with every call site, which is statistically unlikely to succeed in a single generation.13 By presenting only the function's own logic and the safe signatures of resolved dependencies, the individual translation task's difficulty is significantly reduced.10

### **The Skeleton-First Implementation Strategy**

Successful migration agents often employ a two-phase implementation: skeleton construction followed by incremental implementation. The TRAM (Translation with Integrated In-isolation Validation) framework first resolves types across the entire project before attempting to write function bodies. It uses Retrieval-Augmented Generation (RAG) to crawl API documentation and neighboring code context, allowing it to map a single source type (e.g., a Java List) to different target types (e.g., a Python list or tuple) depending on whether the data is mutated or unmodifiable.14

For a TypeScript library like MSAGL-JS, this means the harness can use ts-morph to extract interface definitions and class signatures to build a Rust "skeleton." This skeleton enforces global type constraints and prevents the model from hallucinating non-existent APIs, which is a common error in isolated translation tasks.10 Once the skeleton is verified as compilable, the agent can fill in implementation details node-by-node, using the skeleton as a source of truth for all external references.

## **Idiom Mapping and Pattern Translation Challenges**

Translating TypeScript to Rust is not merely a syntactic transformation but an architectural re-mapping. TypeScript relies heavily on object-oriented programming (OOP) patterns, shared mutability, and a "stringly-typed" ecosystem, all of which clash with Rust’s ownership and borrowing model.16

### **Mapping Object-Oriented Hierarchies to Rust**

TypeScript developers frequently utilize class inheritance to share behavior and state. However, community discussions in platforms like r/rust emphasize that inheritance is often a "design problem" that does not translate well to Rust's trait-based system.19 Rust does not have true inheritance; instead, it utilizes composition, traits, and enums to achieve polymorphism.

* **Behavioral Sharing**: Abstract base classes are typically mapped to Rust traits with default method implementations. However, traits cannot hold state, necessitating a "delegation" pattern where the trait includes a method to return a reference to an inner data struct.20  
* **Data Sharing**: Instead of extending a base class, Rust favor's composition, where a struct holds a common "base" struct as a field. This avoids the "diamond problem" of multiple inheritance and ensures a clear initialization order.19  
* **Sum Types and Enums**: TypeScript's discriminated unions (e.g., type Shape \= Square | Circle) map directly to Rust's tagged unions (enums). Enums are considered one of Rust's most expressive features for modeling application data, often replacing "abstract classes with a fixed list of subclasses".21

A significant architectural hurdle for MSAGL-JS is the handling of cyclic references. TypeScript’s garbage collector allows for complex cyclic graphs where nodes point to edges and vice versa. Rust’s ownership model prohibits this without explicit use of Rc\<RefCell\<T\>\>, Arc\<Mutex\<T\>\>, or an arena-based allocation strategy.4 When Microsoft's TypeScript team evaluated rewriting their compiler in Rust, they ultimately chose Go specifically because Rust's borrow checker made handling the cyclic mutable references in the TypeScript codebase excessively difficult.4 For a graph layout library, this suggests the harness must be instructed to utilize an "arena" pattern (like the typed-arena crate) to manage graph node lifetimes rather than attempting naive reference mapping.

### **Idiomatic Refinement and the "C-style Rust" Pitfall**

Naive LLM translations often produce "C-style Rust"—code that compiles but relies heavily on raw pointers, unnecessary unsafe blocks, and a lack of proper error handling.18 Expert-tier prompts must guide the agent to prioritize "Safety First" and "Think in Rust".18 This involves:

1. Replacing new/delete and raw pointers with ownership and smart pointers (Box, Rc, Arc).  
2. Converting exception-based error handling to Result\<T, E\> and Option\<T\>, using the ? operator for propagation.  
3. Leveraging iterator chains (map, filter, collect) instead of manual for loops.  
4. Implementing the "Newtype" pattern to prevent logical errors by wrapping primitive types in meaningful structs.18

## **Verification and Semantic Correctness Strategies**

Achieving a compilable translation is only the first step; the final output must be semantically equivalent to the original TypeScript. LLMs are prone to "logic omissions"—the subtle removal of edge-case checks or the simplification of mathematical logic—which can lead to catastrophic failures in a library as precise as MSAGL.24

### **The Compiler-in-the-Loop Repair Cycle**

The most effective verification strategy for syntactic and borrow-checker errors is an automated repair loop driven by compiler feedback. Systems like "SafeTrans" and "SmartC2Rust" capture the standard error output from the Rust compiler and feed it back to the LLM.13 Research indicates that this iterative process is a massive performance multiplier. In one study, the first feedback loop boosted performance by up to ![][image3], while multiple runs and loops together increased the success rate by ![][image4].26

The repair process often follows a tiered hierarchy:

* **Rule-Based Repair**: Targets deterministic patterns, such as missing imports or obvious type conversions, without invoking the LLM.10  
* **LLM-Based Repair**: Injects the compiler error message and the relevant code fragment into a reasoning model to suggest structural changes.10  
* **Fallback to Unsafe**: If the repair limit is exhausted, some systems fall back to C2Rust-generated unsafe code to ensure the project still compiles, though this is undesirable for pure-Rust migrations.10

### **Semantic Equivalence Testing**

Beyond compilation, behavioral equivalence is verified through differential testing. For MSAGL-JS, this involves running the original TypeScript code and the translated Rust code against the same graph inputs and comparing the output node coordinates and edge splines.

* **FFI-Based Testing**: SACTOR and other systems embed the translated Rust module back into the original project via the Foreign Function Interface (FFI). This allows existing test suites to run against the new code in situ, providing immediate functional verification.9  
* **Mock-Based In-Isolation Validation**: TRAM serializes I/O pairs and side effects (mutated fields or global states) from original test executions and reconstructs them as mock objects in the target language. This allows individual functions to be tested in isolation, preventing a bug in a low-level utility from causing unrelated failures in high-level callers.  
* **Extraction Equivalence Testing (EET)**: A protocol proposed for high-precision applications involves running a second independent translation on the corpus with no shared state. If the two runs diverge significantly, it flags a likely hallucination or logic omission.27

## **Agentic Harness Engineering: Claude Code and LangGraph**

The architecture of the migration tool itself—the "harness"—is what enables the model to act as a capable coding agent. Anthropic’s "Claude Code" is a prime example of such a harness, providing tools for filesystem access, shell execution, and context management.28

### **LangGraph as an Orchestration Layer**

LangGraph is increasingly used to build controllable, stateful agents for complex migration tasks.30 Unlike a simple chat loop, LangGraph allows for "Hierarchical and Sequential control flows" where tasks can be delegated to specialized subagents.30

| Agent Role | Responsibility | Tools Used |
| :---- | :---- | :---- |
| **Architect** | Builds dependency graph and schedules topological translation. | ts-morph, glob, grep. |
| **Translator** | Converts individual AST nodes/snippets from TS to Rust. | Claude (Haiku/Sonnet/Opus). |
| **Verifier** | Runs compiler and tests; identifies failures. | cargo, cargo check, pytest. |
| **Research Subagent** | Investigates unknown APIs or geometric algorithms. | Web search, documentation fetch. |
| **Repair Agent** | Analyzes compiler errors and applies patches. | sed, edit\_file, LSP info. |

10

A key capability of these "Deep Agents" is the use of a "Planning Tool." Before implementation, the agent uses a "write\_todos" tool to break down the migration into discrete steps, track progress, and adapt the plan as new dependency conflicts emerge.32 This "Plan Mode" is critical for avoiding the "vibe-coding" trap where the agent jumps into coding before understanding the codebase structure.35

### **Harness Primitives and Context Engineering**

The harness must aggressively manage the LLM's context window. Claude Code uses "Context Compaction" and "File System Offloading" to prevent the model from becoming overwhelmed by its own history.28 Primitives like "Auto mode deny-and-continue" allow the harness to recover from blocked paths and try safer implementation strategies autonomously.29

One notable project, "claw-code," provides a clean-room Python implementation of these harness patterns, emphasizing the need for:

1. **Durable State**: Persistence of conversation, approvals, and workspace state across sessions.37  
2. **Protocol-First Design**: Using standard protocols (like MCP or ACP) to connect agents to external tools and documentation.38  
3. **Artifact Memory**: Treating the filesystem as working memory for large tool outputs rather than cramming them into the prompt.38

## **Lessons Learned and Industry Insights**

Large-scale migrations to Rust have revealed several recurring failure modes and areas where human intervention remains non-negotiable.

### **Reported Failure Modes in LLM Code Translation**

* **API Hallucination**: LLMs frequently hallucinate target-language APIs that do not exist or mis-map parameters when source and target APIs have similar names but different semantics.15  
* **Context Window Degradation**: As the context fills up, the model may "forget" earlier architectural instructions or start making more syntactic mistakes.34  
* **Complexity Bottlenecks**: LLMs excel at standard library calls but struggle with domain-specific or private APIs (internal drivers, proprietary math kernels).10  
* **Symbol Density Overload**: Rust's dense syntax—where a single signature can express lifetimes, generic constraints, and mutability simultaneously—can cause immediate cognitive overload for the model, leading to "type soup" errors.41

### **Human Effort and Manual Intervention**

While automation can handle the majority of boilerplate and standard transformations, expert human intervention is typically required for:

1. **Initial Domain Mapping**: Deciding on the fundamental data structures (e.g., Arena vs. Rc/RefCell) that will govern the migrated project.4  
2. **Complex Macros and Inline Assembly**: LLMs have limited success with complex C preprocessor directives or architecture-specific assembly, which often require manual porting.9  
3. **Verification of High-Stakes Logic**: In financial or security-critical systems, manual audit of the generated code is still the gold standard for verifying "semantic fidelity".24  
4. **Performance Optimization**: LLMs are notoriously poor at identifying Big-O improvements, often introducing ![][image5] bottlenecks where ![][image6] is required.42

### **Specific Challenges in TypeScript-to-Rust**

TypeScript's "flexibility" is its greatest hurdle during translation. The "escape hatches" of TypeScript (like any or as unknown as User) cannot exist in safe Rust.17 A TypeScript developer can write code that passes the compiler but throws a "Cannot read properties of undefined" error at runtime—a scenario impossible in Rust if the migration correctly maps null/undefined to Option\<T\>.17

Furthermore, the "web dev" landscape often relies on immature or rapidly shifting libraries. Engineers who have attempted manual migrations report "screeching to a halt" when trying to find Rust equivalents for the plumbing between various JavaScript libraries.16 This highlights a major gap for agentic harnesses: the need for an "API Bridge" or "Database of Equivalents" to guide the model when third-party dependencies have no direct 1-to-1 mapping.

## **Synthesis and Strategic Recommendations**

The proposed approach of building an agentic harness using ts-morph for AST analysis and LangGraph for orchestration is highly aligned with the most successful research efforts in the field (e.g., His2Trans and TRAM). However, several refinements should be considered based on the current gaps in the ecosystem.

### **Key Tactical Suggestions for the MSAGL-JS Harness**

* **Implement a "Two-Phase" Translation**: The first phase should focus on a "safe, unidiomatic" translation using Box and RefCell to handle cyclic references common in graph libraries. The second phase should then perform "idiomatic refinement," looking for opportunities to move toward arena allocation or more efficient borrowing.9  
* **Prioritize a "Skeleton-First" Approach**: Do not attempt to fill in function implementations until the entire Rust project structure (modules, structs, traits) is defined and compiles as a skeleton. This ensures the translator agent always has a consistent reference for callee signatures.10  
* **Incorporate "Delta Debugging" for Verification**: When test suites fail, the harness should use a delta debugging strategy to isolate the specific translation unit responsible for the failure, rather than trying to re-translate the entire file.7  
* **Address Geometric Complexity via E-Graphs or Formal Checks**: For a library as mathematically sensitive as MSAGL, consider using equality saturation (e-graphs) or specialized property-based tests to ensure that geometric invariants are preserved across the migration.45  
* **Model Tiering and Cost Management**: Utilize the tiered routing system to send routine boilerplate to Haiku, but use Sonnet or Opus for "Symbol Density" repair tasks where the model must navigate complex lifetime and generic bounds.7

The synthesis of AST-driven topological ordering and LLM-powered semantic reasoning represents the first viable path toward the fully automated, repository-level migration of complex libraries like MSAGL-JS. While challenges in handling cyclic references and performance bottlenecks remain, the integrated verification loops and "compiler-in-the-loop" paradigms developed under programs like TRACTOR provide the necessary guardrails to produce production-ready, memory-safe code.

#### **Works cited**

1. ORBIT: Guided Agentic Orchestration for Autonomous C-to-Rust Transpilation \- arXiv, accessed April 15, 2026, [https://arxiv.org/html/2604.12048v1](https://arxiv.org/html/2604.12048v1)  
2. DARPA TRACTOR program: C to Rust conversion \- community, accessed April 15, 2026, [https://users.rust-lang.org/t/darpa-tractor-program-c-to-rust-conversion/133653](https://users.rust-lang.org/t/darpa-tractor-program-c-to-rust-conversion/133653)  
3. Forcing Rust: How Big Tech Lobbied the Government Into a Language Mandate \- Medium, accessed April 15, 2026, [https://medium.com/@ognian.milanov/forcing-rust-how-big-tech-lobbied-the-government-into-a-language-mandate-40ee80cbc148](https://medium.com/@ognian.milanov/forcing-rust-how-big-tech-lobbied-the-government-into-a-language-mandate-40ee80cbc148)  
4. A 10x Faster TypeScript \- Reddit, accessed April 15, 2026, [https://www.reddit.com/r/typescript/comments/1j8s467/a\_10x\_faster\_typescript/](https://www.reddit.com/r/typescript/comments/1j8s467/a_10x_faster_typescript/)  
5. C2SaferRust: Transforming C Projects Into Safer Rust With NeuroSymbolic Techniques, accessed April 15, 2026, [https://www.computer.org/csdl/journal/ts/2026/02/11285862/2ckf0ZHkjfy](https://www.computer.org/csdl/journal/ts/2026/02/11285862/2ckf0ZHkjfy)  
6. Adversarial Agent Collaboration for C to Rust Translation \- OpenReview, accessed April 15, 2026, [https://openreview.net/forum?id=5gLUzPYBv4](https://openreview.net/forum?id=5gLUzPYBv4)  
7. Translating Large-Scale C Repositories to Idiomatic Rust \- arXiv, accessed April 15, 2026, [https://arxiv.org/pdf/2511.20617](https://arxiv.org/pdf/2511.20617)  
8. Translating Large-Scale C Repositories to Idiomatic Rust \- arXiv, accessed April 15, 2026, [https://arxiv.org/html/2511.20617v1](https://arxiv.org/html/2511.20617v1)  
9. SACTOR: LLM-Driven Correct and Idiomatic C to Rust Translation with Static Analysis and FFI-Based Verification \- arXiv, accessed April 15, 2026, [https://arxiv.org/html/2503.12511v3](https://arxiv.org/html/2503.12511v3)  
10. His2Trans: A Skeleton First Framework for Self Evolving C to Rust Translation with Historical Retrieval \- arXiv, accessed April 15, 2026, [https://arxiv.org/html/2603.02617v1](https://arxiv.org/html/2603.02617v1)  
11. C2RustXW: Program-Structure-Aware C-to-Rust Translation via Program Analysis and LLM, accessed April 15, 2026, [https://arxiv.org/html/2603.28686v1](https://arxiv.org/html/2603.28686v1)  
12. Dual Code-Test C to (safe) Rust Translation using LLMs and Dynamic Analysis \- Syzygy, accessed April 15, 2026, [https://syzygy-project.github.io/assets/paper.pdf](https://syzygy-project.github.io/assets/paper.pdf)  
13. ENCRUST: Encapsulated Substitution and Agentic Refinement on a Live Scaffold for Safe C-to-Rust Translation \- arXiv, accessed April 15, 2026, [https://arxiv.org/html/2604.04527v1](https://arxiv.org/html/2604.04527v1)  
14. Advancing Automated In-Isolation Validation in Repository-Level ..., accessed April 15, 2026, [https://alirezai.cs.illinois.edu/assets/pdf/tram.pdf](https://alirezai.cs.illinois.edu/assets/pdf/tram.pdf)  
15. Validated Code Translation for Projects with External Libraries \- arXiv, accessed April 15, 2026, [https://arxiv.org/html/2602.18534v1](https://arxiv.org/html/2602.18534v1)  
16. Moving from TypeScript to Rust / WebAssembly \- Hacker News, accessed April 15, 2026, [https://news.ycombinator.com/item?id=23776514](https://news.ycombinator.com/item?id=23776514)  
17. Rust vs TypeScript for Full-Stack Development in 2026, accessed April 15, 2026, [https://rustify.rs/articles/rust-vs-typescript-full-stack-2026](https://rustify.rs/articles/rust-vs-typescript-full-stack-2026)  
18. How to Move from C++ to Idiomatic Rust Using AI | by Ranga Seshadri | Medium, accessed April 15, 2026, [https://medium.com/@rangabb/how-to-move-from-c-to-idiomatic-rust-using-ai-b21aef9d699e](https://medium.com/@rangabb/how-to-move-from-c-to-idiomatic-rust-using-ai-b21aef9d699e)  
19. What's the Rustacean way to handle inheritance? : r/rust \- Reddit, accessed April 15, 2026, [https://www.reddit.com/r/rust/comments/rzvx8b/whats\_the\_rustacean\_way\_to\_handle\_inheritance/](https://www.reddit.com/r/rust/comments/rzvx8b/whats_the_rustacean_way_to_handle_inheritance/)  
20. With composition over inheritance in Rust, how does one implement shared state to go with shared behaviour? \- help \- The Rust Programming Language Forum, accessed April 15, 2026, [https://users.rust-lang.org/t/with-composition-over-inheritance-in-rust-how-does-one-implement-shared-state-to-go-with-shared-behaviour/47357](https://users.rust-lang.org/t/with-composition-over-inheritance-in-rust-how-does-one-implement-shared-state-to-go-with-shared-behaviour/47357)  
21. How should I think of enums in rust? \- Reddit, accessed April 15, 2026, [https://www.reddit.com/r/rust/comments/1lawklx/how\_should\_i\_think\_of\_enums\_in\_rust/](https://www.reddit.com/r/rust/comments/1lawklx/how_should_i_think_of_enums_in_rust/)  
22. Trait-based enum Variants \- language design \- Rust Internals, accessed April 15, 2026, [https://internals.rust-lang.org/t/trait-based-enum-variants/19825](https://internals.rust-lang.org/t/trait-based-enum-variants/19825)  
23. TypeScript Goes Go: What Does This Mean for Us? \- cekrem.github.io, accessed April 15, 2026, [https://cekrem.github.io/posts/typescript-goes-go/](https://cekrem.github.io/posts/typescript-goes-go/)  
24. An End-to-End Agentic Pipeline for Smart Contract Translation and Quality Evaluation, accessed April 15, 2026, [https://arxiv.org/html/2602.13808v1](https://arxiv.org/html/2602.13808v1)  
25. Automating Computational Reproducibility in Social Science: Comparing Prompt-Based and Agent-Based Approaches \- arXiv, accessed April 15, 2026, [https://arxiv.org/html/2602.08561v2](https://arxiv.org/html/2602.08561v2)  
26. Feedback Loops and Code Perturbations in LLM-based Software Engineering: A Case Study on a C-to-Rust Translation System \- arXiv, accessed April 15, 2026, [https://arxiv.org/html/2512.02567](https://arxiv.org/html/2512.02567)  
27. Breaking the Extraction Bottleneck: A Single AI Agent Achieves Statistical Equivalence with Human-Extracted Meta-Analysis Data Across Five Agricultural Datasets | bioRxiv, accessed April 15, 2026, [https://www.biorxiv.org/content/10.64898/2026.02.17.706322v2.full-text](https://www.biorxiv.org/content/10.64898/2026.02.17.706322v2.full-text)  
28. How Claude Code works \- Claude Code Docs, accessed April 15, 2026, [https://code.claude.com/docs/en/how-claude-code-works](https://code.claude.com/docs/en/how-claude-code-works)  
29. Claude Code Harness for AI Pentesting \- Penligent, accessed April 15, 2026, [https://www.penligent.ai/hackinglabs/claude-code-harness-for-ai-pentesting/](https://www.penligent.ai/hackinglabs/claude-code-harness-for-ai-pentesting/)  
30. The Best Open Source Frameworks For Building AI Agents in 2026 \- Firecrawl, accessed April 15, 2026, [https://www.firecrawl.dev/blog/best-open-source-agent-frameworks](https://www.firecrawl.dev/blog/best-open-source-agent-frameworks)  
31. Claude Code Advanced Patterns: Subagents, MCP, and Scaling to Real Codebases, accessed April 15, 2026, [https://resources.anthropic.com/hubfs/Claude%20Code%20Advanced%20Patterns\_%20Subagents%2C%20MCP%2C%20and%20Scaling%20to%20Real%20Codebases.pdf](https://resources.anthropic.com/hubfs/Claude%20Code%20Advanced%20Patterns_%20Subagents%2C%20MCP%2C%20and%20Scaling%20to%20Real%20Codebases.pdf)  
32. langchain-ai/deepagentsjs at bookmrks.io \- GitHub, accessed April 15, 2026, [https://github.com/langchain-ai/deepagentsjs?ref=bookmrks.io](https://github.com/langchain-ai/deepagentsjs?ref=bookmrks.io)  
33. 5 Claude Code Agentic Workflow Patterns: From Sequential to Fully Autonomous, accessed April 15, 2026, [https://www.mindstudio.ai/blog/claude-code-agentic-workflow-patterns-4](https://www.mindstudio.ai/blog/claude-code-agentic-workflow-patterns-4)  
34. Best Practices for Claude Code, accessed April 15, 2026, [https://code.claude.com/docs/en/best-practices](https://code.claude.com/docs/en/best-practices)  
35. Beyond Vibe Coding: Building an Agentic Engineering Team | by Christopher Montes, accessed April 15, 2026, [https://levelup.gitconnected.com/beyond-vibe-coding-building-an-agentic-engineering-team-adc0283d1937](https://levelup.gitconnected.com/beyond-vibe-coding-building-an-agentic-engineering-team-adc0283d1937)  
36. Common workflows \- Claude Code Docs, accessed April 15, 2026, [https://code.claude.com/docs/en/common-workflows](https://code.claude.com/docs/en/common-workflows)  
37. What Is Claw Code? The Claude Code Rewrite Explained | WaveSpeedAI Blog, accessed April 15, 2026, [https://wavespeed.ai/blog/posts/what-is-claw-code/](https://wavespeed.ai/blog/posts/what-is-claw-code/)  
38. Modern Agent Harness Blueprint 2026 · GitHub, accessed April 15, 2026, [https://gist.github.com/amazingvince/52158d00fb8b3ba1b8476bc62bb562e3](https://gist.github.com/amazingvince/52158d00fb8b3ba1b8476bc62bb562e3)  
39. When Code Crosses Borders: A Security-Centric Study of LLM-based Code Translation, accessed April 15, 2026, [https://arxiv.org/html/2509.06504v2](https://arxiv.org/html/2509.06504v2)  
40. Unseen-Codebases-Domain Data Synthesis and Training Based on Code Graphs, accessed April 15, 2026, [https://www.researchgate.net/publication/401177677\_Unseen-Codebases-Domain\_Data\_Synthesis\_and\_Training\_Based\_on\_Code\_Graphs](https://www.researchgate.net/publication/401177677_Unseen-Codebases-Domain_Data_Synthesis_and_Training_Based_on_Code_Graphs)  
41. Experienced in C/C++/Java but feeling lost looking at Rust code. Does the readability 'click' eventually? \- Reddit, accessed April 15, 2026, [https://www.reddit.com/r/rust/comments/1pljx57/experienced\_in\_ccjava\_but\_feeling\_lost\_looking\_at/](https://www.reddit.com/r/rust/comments/1pljx57/experienced_in_ccjava_but_feeling_lost_looking_at/)  
42. Can LLMs write better code if you keep asking them to “write better code”? | Hacker News, accessed April 15, 2026, [https://news.ycombinator.com/item?id=42584400](https://news.ycombinator.com/item?id=42584400)  
43. Why should a high-level programmer use Rust? \- Reddit, accessed April 15, 2026, [https://www.reddit.com/r/rust/comments/154io4c/why\_should\_a\_highlevel\_programmer\_use\_rust/](https://www.reddit.com/r/rust/comments/154io4c/why_should_a_highlevel_programmer_use_rust/)  
44. Whenever I write Rust, I have a lot of fun, but I'm still not sold on it for mos... | Hacker News, accessed April 15, 2026, [https://news.ycombinator.com/item?id=23776855](https://news.ycombinator.com/item?id=23776855)  
45. An opinionated list of awesome compiler frameworks, libraries, software and resources. \- GitHub, accessed April 15, 2026, [https://github.com/hummanta/awesome-compilers](https://github.com/hummanta/awesome-compilers)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADYAAAAXCAYAAABAtbxOAAACDUlEQVR4Xu2VOyxlURSGl8EkGhERzRQUColGIqIgUZhkeoVKp/EIIdFSKSRGIfFoTKYbBYXWq5FIUCFiiuk8ChHi/RiC9dt7X+usu7d7xY3qfMmfu/5/nbP3Xu45F1FMTMxn08tq06Ggj3XOuma1qJ6jjLXGemItqp5kmPWfdcyqU72MMEVmAxwEao+2E+ywFoTfZq0ID+rJrOGoVN5xxhoQ/oY1KHzGCQ2WT/4DIitQXn/j+KOtCt9AyWsVerKMEhpsg/wbI5u0dbH1+JTM29zhng4NsmaV1Sjvo1wHPkKDIQ8dxuX9opb8pmiO+l54B/ItleWwHlUm8e3n5SODzYpaMkbJg+EHSIMc75rmK/nX9WVBcHGHDim9wZZFLRkhk3+zHvXJaztBaA+ghwtdFwQ3dOqQwpvK/I+oJaNkcjxWAPXpazsB8rceOzcclKV6KcFNXTqk9AYLvWO/KJqjvhPegfyfDgVfKHyOlOCmbh0yF+RfENlfW9dan+pXMXQ4ZBM6tLihQLao0wY39OiQaSL/YsiqlG8UHlxS9J0ap+S18Gghy1U5cD3Ju4YrInPxT92woNcq/JDNJHOsB+HdoUpFBpBVCL9O/l9KoPdwyG/RyzTriLXP2rOfh2T+kUryyCyEQ2yybsn/EqN3xZohc/33aPuFEjK9JdYu6yDaTvBDBwrsX63DmJiYmBjJM0i1qgPxF46eAAAAAElFTkSuQmCC>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAC8AAAAXCAYAAACbDhZsAAACHUlEQVR4Xu2WP0hXURTHT2KEtKm0NOhgkxDRImLoUEujoi4lbUKGouDU4BANDjkoZVO4KaKDLoJSi5Nai60t4p9BRFFR8k9p5+s59777jlf6/X5OP/x94Ms753ve+b3L9bz7JCpQoEAv67U1s+Aua451zvrOupUuewZYJ6xt1hNTc1SxFkl+66upecZIfgg3QR3pcsbcJ+kv0bxM8yJ/h7DHeh/kv1n9QQ4aSHodj0we5TqLP2SNG+8H6yjIn9LlRZRGPOR2ArDBC8ZLcZ3Fo7fVeG/Vd7i/sAXeS43vaY5riBvHK8l18fUkvXZ+X6mP3QWIT5OyB/5Pjfs0t4xQ3Pfkuvhukt7Hxm9Rv0ZzxPtJ2QMfsw+mNLd8orjvQfGNNTPgHUnvQ+M3qv9Cc8Q7SdkD3y1sPohDBkl8HAxRUOy0Zga0k/TiVAhpVh8vKkC8m5Q98M80HtXc8pHEL7YFB4pd1swAN/O1xm9T3+0W4uOk7IH/S+OrZv4LxX0PipjfbLlD0vu/0wZxbAHwPmtcp3lOp02PNZXnrGprBqB3yHgz6juGTQ7wFYZ3O/CQNwU5OKD4+3JBOUnTB1ug5AH2wSF2l0FsEfDCTViiyyfQLOtPkLvnVwbeBROsLdY6a02vmyQflJBp1orxLPhX469e8bDYCFaQ1L6xVlkb6bJnmeSrPUly/7N0OXuwS3mLHYu8AW873ou85IE1CtxE/gHysJqx7m7D3gAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACMAAAAXCAYAAACBMvbiAAABu0lEQVR4Xu2UvyuGURTHDwlRSjHIRilZDMrAJpMk2QyyYLPYjCwGA4nFyF8gK4uFMkm9kcmviCIDkl/f4977OM95z329CaXeT3177vmee5/nPM89zyUq8Pf0asOgVRs/TQv06K/PUFs6nXAI9Wsz0AldQ2/QNlScTpvcQQPK4/WNflwNPUAv0ATUDS37ORd+ThYL0JKI78ktaBCeZozcHKuYWFznr/zlovCCdsPTN5ZcUXYxNd6T6HiScmxPJdkPtrzArb/qYoIXi0sox/YEpqEO5cWKGYKG/dgq5gka9OMuaETlvgU/6FWb5Jo2YBXDsL9K7ocITEF9Is6bPXI3rFD+JVQk4lgxmlLoXMTN5H6STeGZcCPzQ2qV3wONKy/fYvi8CVTR5/Zzv2ZELgWfCzyxTCfInReafIqZIfcigWNoTcRHYpzAh5xu2BUx3lLaJTef34xji3LoVHm8ZlHEc2KcYDUrn5wxmujrL2Ot18XMi/EH/MvxJEsx+Cjg/KhOeGbJ/dqaHWhdxKltqqfsAoKsPmFuoDPohNw2cCzh7TF7gVw/hpfkBt4XuV/hQBsK3mLejQ2dKFDg3/IOOTV5+WyC9XwAAAAASUVORK5CYII=>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACMAAAAXCAYAAACBMvbiAAAB0klEQVR4Xu2VyytFURTGl8gjJYqBKeU5UfwBJCNJJgamUoYeGXilPEoxQBmIkjIxlYnEzIAJSkRGkgyYUEjEt87e+9511jnn3sml1P3V19nft9fZ+9yzz96XKM3f06aDEOp0kGpqoXd7/YQa/N0xrqEOHTL90BZUY30VtAn1xSrijEPP0CvUrfqYb6jctougN+gLGoRaoFVb82BrAkyTKZA68VUYLqA94c+hQ+EZvjfKl9orv7lIJqAlaAMagzL93R4FFJyI4azQtoutl2g/QhHL4+AHaNKh4pSCAzOcrSkvkT6LEiyPY5SSP4xbPo3OP6Au226GelRfUoahGTKDrtvriq8iOKkjLGfPG+BRZJNQu/CRDEC7KuMBp5TXkzJRuSQbuhe+msxuPBBZQvQk2juicgmfNw65EfKhS9HnkaEDMmdDKh5mFmoV/hbaFv5GtD14sKeQTE7yoryDs8Cvs+RCdyrj+mXhF0TbgwuGQjI5eafyDs7qdWjht6vRD7Mo2h78MZUI30jmpkqRMZz1Cj9nszDmyWxtzRG0I3xgmRheJvc2WGX+bo88Mn3H0BmZYz3se+PlCZ0E5FD8B/AHzH8pv8qVDhQVZA7Afd2RJs2/5QdYv4HytBjN3AAAAABJRU5ErkJggg==>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAYCAYAAAC4CK7hAAACXElEQVR4Xu2WzUsVURjG31JDEzVBamVBf0Arw9RFaBCuLSoiuhYEuXEjiLpw5wdtKgipRYtsoSD1F7TIRSBI0MemD3AREVEuDAyV0nwfzxk995kzc+cOd7DF/cHDnfm958ydOTPnzIiUyYRFzT/NKy7sB+dZJGTZ2Z7W/HH2wRXaL4oTmoeaB5p6qvm4rRlimRDciUm7fcDuu5zUvCVXkHtiDnTd7h/X/NCs77YI06z5xjIlpyV8IeC+5hFLHwfFHGCeC5a/mi2WFvSrZpkSPFZXWVp8FxgCjZZYOnSJaXOOfLtmg1xaHkv8fHgqBR6xr1L4aoM7NkceI5h2brjc1Jyx2x1uwaFBYs7zrJjiS/JMo5h2K+ThasgFzGh6nP1LmlnZO+GAFjGTvVdzS/Mxr5oP/s+7+GBEkzzj18S0e+O4Out8bNpf1C+IGYAjYi4azn2EsM+JArVhlqBQx4BPYtphmQ3otI7ByWKVAahjoXCBe0EuKej7hOVRW/CdDONrd8PjwClNheaYmPrh/PKOGyCXlDXNAkv8GQ6KYhwXxbTjpTlnfRRTEq63WYcXXxp+a16zBL6RZqLaYNL6fABq/Lnx3fq0oO9zluCXxB/4i5h6FRdkbyWLArUJjxt3tosFfUZYBqD4jqXyU8IjyqDvIZZKk5gaL81weCfhbvZRLQnojwGMBF+gaISJhDmD7da8Fn7QzjdxL4t/xN+L8Xe5kIBa8R+zJAxqVllmBL7Gn7EsJRilSpYZkNndCOjWfGZZYkY1Yyyz4I6Y76QswIv1A8ssybEoEf0syvzPbAMOhpRP83ejOwAAAABJRU5ErkJggg==>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFUAAAAYCAYAAACLM7HoAAADnElEQVR4Xu2YWchNURTHlzGUWYiQBynKiwfDy5chlCezIl+U6YkSKa+G8oLI8OLRPDyIJw+k8CAZHpSpzEKhjBnX/+69bvv+7zrnfr7v6n4+91ere/Z/rXPOPuvsvfY+V6ROnf+VaSy0MTqq9WHxTximtl9tj1oP8nmsUtvIYjPpoDaSxVbCO7XuLFZip9ovtSWxPVTtldqXYkQ5Q9Ses9hM0GncH9ZaaXLf2ksIvsiOyHe1nyxGcF4XFlsAXmiTO14DtqpdY9EDD/GQxYTJEmKmkD5R7StpLWW+tO6kAvSvHYspT6XyQ9hIPk76N6leLTVmS+X+1JofaptZNBokPMAF0pneEuJQ81KgdSXNOCwhQQZG4BG18YnmMUuyk7pe7YWEBbQT+Qxc/5DamtjGPVG6ehYjSjmgtjxpz1A7pjYv0Rgs4iiJLhhpTamJiyXE3Ug0rIJZD483CeCfI+Fl9JLwAqAtjH4PL6mDojY8tm3mLCpGBD6pnYzH2JEgBsn/qLbCghIeSZjGiNsioZSNSDQkzwNlj/tYBI5MZ8JdCXHoqDEpagwStysew89vFNp50lK8pKK9j7RRUUeCAaajd17eonIz/np5QBuDzmOglMcX6C/+xTy8uKWOBsZI2GsOkODvVuouaOtIS+GkTo9tb/pCx/QFqPfcH7Q/k2bgeugjQNzUxGfaGdJS+F4F8OB5NzXmSojj7VZj1LPYK+X+CVHLWzk5qQdj26uhaf/7xjZ+gZWImbGdhbfbQDmENpr0FD6nCByZzkhWDBYETzfg4+nzMup5cFLXxrbV0xToD5L2m6i9jb8LEl8Wd6S8TyccLcVmoct7yXEqjyX4vVFiO4Is4NvmaNg827EHEpH6bNHgkmH3x6IBsMBkLSx54BpXHO1yPMYix1QaUAXnLRaV11I+0hic25lFpZ8EH2+3oGFaolOryWdARxzKk4GXww+Bz+f7pCHmutoltXNquyV8RueBc/BxwxpKFeruUfIBXJf7U4ZNm6sSahSOx5VE+CCORxDg0WbclqDvYEcEo+KZ2hMJpeJ04hsrYcuD82ErEx/Av0i2RWRDoj1sq8ackqDzOmLgPjwLq8YGtQ8s1ggkoYFFZbD4iWsJ1b5eGbgBRkmtQT/wgeFRzSRsEr9cVhV81t1jsQbY1i/9ykLtxlTFp2q1qOYLymW7lH4/15JlEr7dz0oYVdUE/zt4HyF/jUYW2hjYyVTaSdSp8w/wG5GJ+yTtesLLAAAAAElFTkSuQmCC>