# Research Background

Oxidant's approach is grounded in the academic literature on LLM-assisted code translation. The key references and lessons:

---

## Key papers

| Paper | Lesson applied |
|-------|---------------|
| **ORBIT** (2024) | AST-driven, dependency-ordered approach substantially outperforms file-by-file LLM prompting |
| **His2Trans** | Skeleton-first approaches dramatically outperform node-by-node translation that builds from nothing |
| **SACTOR** | Splitting into a correctness-first pass followed by an idiomaticity pass produces better results than doing both simultaneously |
| **EvoC2Rust** | Topological ordering and real compiler feedback are the two biggest drivers of conversion quality |
| **ENCRUST** | Using `cargo check` for verification rather than an AST library catches borrow checker issues that static analysis misses |

Full citations in [RESEARCH_ACADEMIC.md](https://github.com/ByteBard97/oxidant/blob/main/docs/RESEARCH_ACADEMIC.md).

---

## Prior manual translation

Before Oxidant, the project authors attempted a manual translation of msagl-js to Rust over 236 commits. That experience provides direct ground truth about where agents cut corners and what the hard patterns are:

- Agents consistently simplify code rather than faithfully translating it ("improvement during translation" — documented in vjeux's Pokemon Showdown port study)
- The bidirectional Node↔Edge reference pattern is specifically hostile to Rust's ownership model and must be decided architecturally before any translation begins
- Deep class hierarchies require the scaffold (skeleton) to encode the correct Rust representation before agents touch the code — agents left to invent their own produce inconsistent results

These lessons directly shaped Oxidant's design: the skeleton-first approach, the branch parity verification check, and the hierarchy classification system.
