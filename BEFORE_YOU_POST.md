# Before You Post on r/rust or HN

This file exists because the Rust community is knowledgeable and blunt. They will
look at 5 random snippets, ask one question you haven't answered, and decide in 30
seconds whether to engage or sneer. This checklist is how you make sure the answer
is "engage."

---

## The Non-Negotiables (Fix These First)

### 1. The Empty Loop Problem

`snippets/entity/` contains a function where an event loop was translated as:

```rust
for _ in &self.events { }
```

This passed all three verification layers (no stub, structure matches, compiles).
It is semantically wrong — it does nothing. This is a smoking gun that your
verification is structural, not semantic, and **one commenter finding this will
define the whole thread**.

**Fix:** Audit the 493 converted snippets. Find every empty body, every `todo!`
that snuck through, every suspiciously short translation of a long source function.
Either fix them or honestly document that Phase B produces structural correctness
only, not semantic correctness, and that human review is required.

---

### 2. The 89.8% Problem

493 converted. 4,301 not started. The first HN comment will be:
*"So it's 10% done on one codebase?"*

You need a prepared answer before you post. Options:

- **Frame it as a proof of concept:** "We ran it on the easy/medium tier to prove
  the pipeline. The remaining nodes are Opus-tier complexity and intentionally
  deferred pending cost analysis."
- **Show the tier breakdown:** What fraction of not-started nodes are Haiku vs
  Sonnet vs Opus tier? If 80% of remaining are Haiku-tier, that's different from
  80% being Opus.
- **Give a cost estimate:** "At our observed rate, completing the corpus would cost
  approximately $X." If you don't say this, someone will assume $50k.

---

### 3. The Snippet Quality Is Uneven

The good snippets (`edge/remove`, `edge/isInterGraphEdge`) look like real Rust.
The bad ones look like TypeScript with braces. Specifically:

- `Color__Xex` does string-slicing gymnastics for what should be `format!("{:02x}", i)`.
  A Rust dev will look at this and think "Phase C didn't run, or didn't help."
- `Edge__add` clones `self` to wrap it in `Rc<RefCell<>>`. This is almost certainly
  wrong — the original TypeScript probably appends a reference, not a clone.
- Raw `as_ptr()` pointer comparisons in `Edge__remove`. Works, but Rust devs will
  ask why you're not using `.position()` + `.swap_remove()`.

**Fix:** Before posting, run the translated snippets through a real Rust developer
(or Claude with a strict idiomatic Rust prompt) and flag the mechanically-translated
ones. You don't need to fix all of them — you need to know which ones are bad and
say so honestly.

---

## Important Gaps to Fill

### 4. Add a "Scope & Limitations" Section to README

Right now the README reads as though this works on any TypeScript codebase. It
doesn't — not yet. The idiom dictionary is tuned to graph algorithms (arena
allocation, `Rc<RefCell<>>` graphs, slotmap patterns). It would do poorly on:

- Async/event-driven TypeScript
- DOM manipulation code
- HTTP/networking libraries
- Generic SaaS application code

Add a section that says this clearly. The Rust community respects honesty about
scope far more than they respect overclaiming.

### 5. Show Real Failure Cases

You have 26 nodes in `human_review`. Pick 3-5. For each one, show:
- What the source TypeScript was
- Why it failed verification
- What a human would need to do to fix it

This is your most credibility-building content. It shows you understand where
the tool breaks, and it shows the tool is honest about its limits (it didn't
silently produce garbage — it flagged things for review).

### 6. Cost Transparency

You strip `ANTHROPIC_API_KEY` and use subscription auth, so you may not have
exact billing data. That's fine — estimate. Something like:

- "Phase B ran approximately N Claude calls to produce 493 conversions"
- "Estimated API cost equivalent: $X if billed at API rates"

Without this, someone will assume the answer is embarrassing.

---

## Your Actual Strengths — Lead With These

The things that are genuinely novel and defensible:

**The verification loop is the real contribution.** Stub check → branch parity →
`cargo check` as a tight feedback loop that rejects bad translations before moving
on. Most people doing LLM translation just vibe-check the output. You have a
machine-checkable correctness gate.

**You did the manual port first.** 236 commits, 21k lines, msagl-js → Rust by
hand. Oxidant is you encoding what you learned. That's a completely different
credibility position from "I prompted GPT and called it a translation tool."
Lead with this story.

**The dependency graph is real.** Type dependencies + call dependencies +
topological ordering means the LLM always has its dependency context already
resolved when it translates a node. This is non-obvious and genuinely solves
a real problem (Claude skipping things it doesn't understand).

**The cascade detection.** Distinguishing "this node is broken" from "this node
failed because a dependency is broken" is subtle and most naive approaches miss
it. Worth a paragraph.

**X→Rust generality.** Python frontend now exists alongside TypeScript. The
architecture (separate AST extractor + idiom dict per language, shared
verification/translation loop) is a real design, not a hack.

---

## The Demo You Should Build First

Before posting anything, have one self-contained demo that a reader can run in
under 5 minutes and verify themselves. The `fit_text_to_cell` Python function is
perfect:

- Input: a readable 40-line Python function with type annotations
- Output: the Rust equivalent in `title_block.rs`
- Verification: `cargo test` passes, `cargo clippy` is clean
- Side-by-side: show Python and Rust in the post body

This demo proves Python→Rust works end-to-end, is small enough to read in full,
and is verifiable by anyone. It sidesteps the "but 89% isn't converted" problem
because it's presented as a demonstration, not a claim of completeness.

---

## Framing That Works

> "I spent a year manually porting msagl-js (21k lines of TypeScript) to Rust
> by hand. I learned every place LLMs fail at this task — they skip things, they
> write stubs and call them done, they produce code that looks right but doesn't
> compile. So I built a harness that encodes everything I learned: dependency-ordered
> translation, machine-checkable verification at every step, and automatic escalation
> when a model tier fails. Here's what it produces, here's where it still needs
> humans, and here's the architecture."

## Framing That Gets You Mocked

> "AI translates TypeScript to Rust automatically"

The difference is: the first framing is honest about what it takes. The second
one sounds like every other LLM wrapper project posted in 2024.

---

## Checklist

- [ ] Audit 493 snippets — find and document the empty/wrong ones
- [ ] Add "Scope & Limitations" section to README (what codebases this is NOT for)
- [ ] Add "Real Failure Cases" section (3-5 human_review examples with explanation)  
- [ ] Add cost estimate (even rough)
- [ ] Prepare the `fit_text_to_cell` Python→Rust demo, end-to-end, clippy-clean
- [ ] Write one paragraph explaining verification is structural (compiles + structure
  matches) not semantic (correct behavior) — be explicit that human review remains
  necessary
- [ ] Decide your framing: research project vs. tool. Own it. Don't try to be both.
- [ ] Run `cargo clippy` on your best 5-10 snippets and check the output before
  posting any of them as examples

---

*Written 2026-05-15 after a pre-post audit of the repo.*
