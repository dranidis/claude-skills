---
name: test-strategy-review
description: >-
  Review and evaluate a repository's tests against the organization's Testing
  Strategy. Finds non-conforming tests, missing tests, and redundant tests;
  spots design/testability problems and suggests improvements. Produces a
  persistent TEST-STRATEGY-REVIEW.md, then verifies each finding against the
  real code and existing tests and reconciles the whole document for
  consistency. Use when the user asks to review tests, audit the test suite,
  check test coverage quality, evaluate testability, or verify tests follow the
  testing strategy. Works in any betadvanced repository.
---

# Test Strategy Review

Evaluate the tests of the current repository (or a named subset) against the
organization-wide **Testing Strategy** and report conformance gaps, missing
coverage, redundancy, and design/testability problems.

## Step 0 — Load the source of truth

The normative rules live in the company **qa-docs** repository. **Read them in
full every run** — do not rely on memory of them, and do not paraphrase rules you
haven't just read.

**Ask the developer where the testing-strategy document (or the qa-docs folder)
is located.** Do not assume a path and do not review against remembered or guessed
rules. Ask for an absolute path to the qa-docs folder (or directly to the strategy
file). If a previous run in this session already established the location, reuse it
rather than re-asking.

Once you have the folder, read these two files from it, in full, every run:

- **`Testing Strategy (AI).md`** — the primary, normative rules for this skill.
  They are written as machine-actionable directives (MUST / MUST NOT / SHOULD /
  SHOULD NOT / MAY) with explicit decision procedures. Judge against these.
- **`Scoping Testing.md`** — the risk → testing-depth table used in Step 3
  category 2 (risk-vs-depth) and the Coverage-vs-risk table in Step 4.

The human-facing `Testing Strategy.md` in the same folder is a prose mirror of the
AI version — consult it only to disambiguate a rule, never as the primary source.
If the path the developer gives doesn't contain the expected files, say what you
found and ask again rather than guessing.

Record which files you used in the report's Summary.

**Override hierarchy (apply before judging anything).** The qa-docs strategy is
the company-wide default, but it layers — for any single rule, apply the **most
specific document that addresses it**:

1. **Repository override** (most specific) — a testing doc *in the repo under
   review* (`TESTING*.md` / `testing-strategy*.md` / `CONTRIBUTING*` /
   `docs/**/test*`).
2. **Stack-chapter document** — if the chapter publishes one.
3. **qa-docs `Testing Strategy (AI).md`** (default).

An override is **not** wholesale: a repo-local or stack-chapter doc overrides only
the rules it explicitly states; for everything else the next level down still
applies. Before judging a finding, check whether a more specific doc addresses it;
if so, follow that one. Note which source governed each finding.

## Step 1 — Establish scope

- If the user named a path, module, or "the changes/this branch", scope to that.
- If the user gave no scope, ask once: whole suite, a directory/module, or just
  the current diff (`git diff` / branch vs `develop`)? Default to the current
  branch's changes if they say "just review it" and a diff exists; otherwise the
  whole suite.
- Identify the test framework, test locations, and how unit vs. integration vs.
  acceptance/E2E tests are distinguished in this repo (config, folders, naming,
  tags). State what you found before reviewing.

## Step 2 — Map the architecture to layers

The strategy's judgments depend on which architectural layer code lives in:

```
APIs: (Infrastructure - DB) - Controller - Service - Domain (Helper functions/classes)
UIs:  UI Component - View - Service - Domain
```

For the code under review, identify each unit's layer. This drives:
- **What may be mocked** — unit tests must not cross layer boundaries; mock only
  cross-layer ports, infrastructure, and external APIs. Mocking a class in the
  *same* layer is a violation.
- **Which test type should cover a concern** (see the test-type decision tree in
  the strategy, section F).
- **Where logic belongs** — Controllers/UI Components should have *no* logic;
  Services minimal coordinating logic; Domain/Helper classes hold the majority.

## Step 3 — Evaluate, producing findings in four categories

Walk the tests and the code-under-test. Classify every finding into exactly one
of these, and tie each to a **specific rule** from the strategy (quote or cite
the rule) plus a `file:line`:

1. **Non-conforming tests** — tests that exist but violate a rule. Common ones:
   - Mocking within the same layer, or mocking the code under test (faking the
     implementation to make a test pass). MUST NOT.
   - Behavior verification (asserting a method *was called*) where an observable
     outcome exists to assert on. Prefer state-based verification.
   - Unit tests crossing layer boundaries / not using real same-layer classes.
   - Integration tests duplicating branch/business-rule logic that belongs at the
     unit level; integration tests not exercising real DB / real cross-layer
     behavior.
   - Acceptance tests carrying implementation detail instead of business terms;
     mocking more than external APIs.
   - Missing ARRANGE/ACT/ASSERT structure; multiple logical ACT/ASSERT.
   - Pact: consumer test that isn't a unit test, provider test that isn't
     integration.

2. **Missing tests** — coverage the strategy requires but that is absent:
   - Uncovered branches / boundary values at the **unit** level (target: 100%
     statement w/ pure-delegation exception, 100% branch).
   - A bug caught only by an integration test with no corresponding failing unit
     test.
   - Real-DB behaviors not integration-tested (persistence, constraints,
     rollback, concurrency, cascade, data mapping) where relevant.
   - Missing acceptance tests for main success + key alternative business
     scenarios; missing Pact tests for any consumer/provider interaction.
   - Apply the **risk → depth** table (Low→Unit, Medium→Unit+Integration,
     High [money/external integrations]→Unit+Integration+BDD+Pact) to judge
     whether the *depth* present matches the feature's risk.

3. **Redundant tests** — duplication that the strategy says to avoid:
   - Branching/business logic re-tested at integration or acceptance level when
     already covered by unit tests.
   - Multiple tests asserting the same behavior with no added boundary/branch.
   - Note redundancy as a cleanup, not a correctness defect.

4. **Design / testability problems** — when the obstacle is the *design*, not the
   test. Flag the design; don't write a contorted test around it. Every item below
   maps to the strategy's **Design for testability** section (or the
   state-vs-behavior procedure under General guidelines); cite that rule, tag its
   normative force (**MUST**/**SHOULD**), and name the layer it belongs in. For
   each finding give a **concrete refactor** — a before → after, not just "improve
   testability".

   - **Service calls the DB or an external API directly** (MUST NOT). The boundary
     isn't isolated behind an interface, so the service can't be unit-tested
     without crossing layers or mocking infrastructure ad hoc.
     *Refactor:* extract a `Repository` / `DataLayer` / `APIClient` interface for
     the boundary call and inject it; the unit test mocks only that interface.
     ```
     // before — service reaches the boundary itself
     class PricingService { run(id){ const row = db.query(...); /* logic */ } }
     // after — boundary behind an injected port
     class PricingService {
       constructor(repo){ this.repo = repo }
       run(id){ const row = this.repo.find(id); /* logic */ }
     }
     ```

   - **Logic in a Controller / UI Component** (SHOULD be none).
     *Refactor:* move it into a Service (coordination) or, better, a Domain/Helper
     class (pure logic). The controller just wires input → service → response.

   - **Heavy / branchy logic in a Service that belongs in Domain/Helper** (SHOULD).
     Business rules sitting in a service force every branch to be exercised at the
     service level with mocks instead of a fast, mock-free unit test.
     *Refactor:* extract a pure Domain/Helper class that takes plain inputs and
     returns a value; unit-test it directly with no mocks; the service calls it.
     ```
     // before — branches live in the service
     class OrderService { total(o){ let t=0; for(const i of o.items) t+=i.p;
                                     if(o.vip) t*=0.9; return t } }
     // after — pure helper holds the branches, tested directly
     class OrderTotal { static of(o){ /* same logic, no deps */ } }
     class OrderService { total(o){ return OrderTotal.of(o) } }
     ```

   - **Reliance on global state or global functions** (SHOULD NOT). Static
     singletons, module-level mutable state, or direct calls to globals (clock,
     random, env, `fetch`) can't be substituted in a test.
     *Refactor:* wrap the global in an injectable abstraction (e.g. a `Clock` /
     `Random` port) and inject it. A DI container is acceptable **only** if it
     still allows mocking/intervention during testing.
     ```
     // before — non-deterministic, untestable
     class Token { issue(){ return { id: uuid(), exp: Date.now()+3600 } } }
     // after — time/id injected, assertable
     class Token {
       constructor(clock, ids){ this.clock = clock; this.ids = ids }
       issue(){ return { id: this.ids.next(), exp: this.clock.now()+3600 } }
     }
     ```

   - **No observable outcome to assert on** → a design smell per the
     state-vs-behavior decision procedure, **not** license for behavior
     verification. First rule out the legitimate exception: if the side effect
     *is* the outcome (an external call with nothing returned or persisted),
     behavior verification is acceptable and this is **not** a design finding.
     Otherwise the design is hard to test on purpose.
     *Refactor:* return or expose observable state — return the computed value,
     mutate and expose a domain object, or persist + read it back — so the test
     asserts on an outcome instead of on whether a method was called.

Use the strategy's decision procedures verbatim where they apply
(pure-delegation exemption; state-vs-behavior; risk→depth; test-type selection).
Do not improvise around a documented procedure.

For the pure-delegation exemption, only treat a method as legitimately
unit-untested if **all three** hold: single delegation call with no branching,
no caught/handled error, and return value is the direct unmodified result.

The output of Step 3 is a **draft**: a first, pattern-matched pass. Its line
numbers, "untested" claims, and severities are hypotheses, not facts. Steps 4–6
turn it into a verified, internally consistent document. **Do not stop at the
draft** — the verification and consistency passes are where most of the value is.

## Step 4 — Write the findings to a review file (first pass)

Don't just print findings to chat — write a structured Markdown report to a
persistent file at the root of the scope under review:
`<scope-root>/TEST-STRATEGY-REVIEW.md` (e.g. `apps/backend/TEST-STRATEGY-REVIEW.md`,
or the repo root for a whole-repo review). Tell the user the path. This file is
the working artifact that Steps 5–6 edit in place.

> **MUST persist the draft to the file BEFORE doing any verification (Step 5).**
> The whole method depends on the written draft getting an *independent second
> look*. Write down the pattern-matched findings — line refs, "untested" claims,
> severities, classifications — as your best first guess, save the file, **then**
> start verifying. This holds even for a small diff and even if you already have
> a hunch each finding is correct.
>
> **Anti-pattern (do NOT do this):** verifying findings first (grepping, reading
> tests, checking diffs) and only then writing an already-refined report in one
> shot. That collapses the draft and the verification into a single act, so no
> finding ever gets re-examined against a written claim — exactly the error this
> process exists to prevent. Orientation reads needed to *produce* the draft are
> fine; confirming/refuting a specific finding is verification and belongs in
> Step 5, after the draft is on disk. If you catch yourself proving a claim
> before the draft is written, stop and write the draft.

Structure:
- **Summary** — scope, frameworks, governing source (qa-docs strategy files used,
  plus any repo-local/stack-chapter doc that overrode them), and a **Counts** line:
  one number per category.
- **Category 1–4** — findings grouped by the four categories above. Each finding:
  `file:line`; the rule it implicates (cite the strategy section); why it's a
  problem; a concrete fix (for design issues, the testability refactor); and
  severity — **MUST-fix** / **SHOULD-fix** / **consider**.
- **Coverage vs. risk** — a small table: per module/area, risk level, required
  depth, what's present, the gap.
- **Quick wins** — the few highest-value changes first.

Prefer a short, prioritized list of real problems over an exhaustive nitpick
dump. If the suite is in good shape, say so.

## Step 5 — Verify and deepen each finding (correct the draft in place)

This is a **separate pass that begins only after the draft from Step 4 is saved
to disk.** Read each finding *as written in the file* and treat it as a claim to
be proven or refuted against fresh evidence — that independence is the point.

The first pass *will* contain errors: wrong line refs, "uncovered" claims that
are actually covered, lumped severities, and items that resolve on inspection.
Go finding-by-finding (or category-by-category) and verify each against **the
actual code AND the existing tests**, then edit the file in place. For each
finding confirm:

- **The code claim** — open the cited `file:line`; confirm the branch / transform
  / logic exists and the line refs are right.
- **The coverage claim (most error-prone)** — read the *existing* tests that might
  cover it, unit *and* api/integration. "Untested" is often really "covered at
  acceptance but not at unit", or "covered with trivial inputs but not this
  branch", or already satisfied (e.g. a "verify Pact tests exist" item where they
  do exist → resolve it). Before asserting zero coverage, `grep` the suite to
  prove a `409` / error-path / null-case genuinely has no hits.
- **The severity** — don't let one bullet lump items of different severity. If
  "all N handlers (MUST)" is really 2 genuine MUST holes + 2 trivial ones, split
  and rank them.
- **The classification** — re-judge against the strategy's procedures. A
  "non-conforming" test may be conforming under the rare-and-deliberate
  behavior-verification exception; a flagged class may be a pure data holder
  that's legitimately delegation-exempt; a log-only side effect with no observable
  state is an acceptable gap, not a finding. **Apply exemptions consistently** —
  if you exempt one pure data holder, exempt the structurally identical ones.

When a finding changes, don't delete it silently: mark reclassified items
"reviewed — conforming / resolved" and **keep them as documented decisions** (so a
later pass doesn't re-flag them), but make the headline **counts reflect only
genuine findings**. Relocate any genuine residual to the correct category.

**Fan out with subagents when scope warrants** (whole suite / many modules):
spawn one subagent per category or per module, each given the relevant draft
findings plus the strategy rules, tasked to verify against code + tests and
return corrected findings *with the evidence* (the grep/read that proves each
claim). You remain the integrator — synthesize their corrections into the single
file; don't let each subagent rewrite the whole document.

## Step 6 — Holistic consistency pass

With findings verified, read the **whole file** once more and reconcile it with
itself:
- **Counts vs. body** — each headline count must equal the number of *live*
  findings in that category (cleared/removed items don't count).
- **Cross-references** — every "see 2e / D6 / N3" must resolve to a real,
  correctly-numbered finding.
- **Conflicts** — the same item must not be described two ways (e.g. a table
  saying "Pact-partial" while a finding says all Pact tests exist; a quick win
  saying "3 entities" while the body excludes two of them).
- **Redundancy** — consolidate a point stated in several places to one home with
  cross-refs, *unless* each instance adds a distinct angle (then it's fine).

Fix what you find, then report the final file path and a short changelog of what
the verification and consistency passes changed.

## Notes

- This is a **review** skill: report and recommend; do not modify tests or code
  under review unless the user explicitly asks you to apply fixes afterward.
  (Editing the `TEST-STRATEGY-REVIEW.md` artifact itself is expected — that's the
  deliverable, not the code under review.)
- Scale the *depth* to the scope, but never the *ordering*. The sequence
  **draft-to-file → independent per-finding verification → consistency
  reconciliation** is mandatory on every run, including a single-file diff. What
  scales is how much work each step takes: for a small diff, Steps 5 and 6 may be
  a single quick edit pass over the file (rather than a subagent fan-out and a
  separate reconciliation read), and the draft itself may be short. "Folding"
  means compressing Steps 5–6 into one lightweight edit — it does **not** mean
  skipping the draft, and it does **not** license verifying before writing (see
  the Step 4 anti-pattern). A whole-suite audit warrants the full draft →
  per-finding verification (with subagents) → consistency reconciliation.
