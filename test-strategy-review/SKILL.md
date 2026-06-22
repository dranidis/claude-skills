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

The normative rules live in a Markdown file. **Read it in full every run** — do
not rely on memory of it, and do not paraphrase rules you haven't just read.

Locate it by searching the **current directory tree** (the repo/working dir being
reviewed). Try, in order:

```
fd -t f -i "testing.strategy" . 2>/dev/null
fd -t f -i "test.strateg|testing.guidelines" . 2>/dev/null
# fallback if fd is unavailable:
find . -type f -iname "*test*strateg*.md" 2>/dev/null
```

- **Exactly one match** → that's the source of truth; read it in full.
- **Several matches** → list them and ask the user which is the governing
  strategy (don't guess).
- **No match** → **ask the user for its location** (an absolute path or a path to
  search). Do not review against remembered or guessed rules. Once given, read it
  in full.

Record which file you used in the report's Summary.

**Override hierarchy (apply before judging anything):** a company-wide strategy
is the default, but a *stack chapter* may publish a project-local testing
document that extends or overrides it. If Step 0's search surfaced more than one
candidate — e.g. a company-wide strategy plus a project-local `TESTING*.md` /
`testing-strategy*.md` / `CONTRIBUTING*` / `docs/**/test*` — the project-local
(stack-chapter) doc **wins where they conflict**. Read both, and note which
source governed each finding.

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
   test. Flag the design, don't write a contorted test around it:
   - Logic in Controllers / UI Components (should be none) or heavy logic in
     Services that belongs in Domain/Helper classes.
   - Reliance on global state / global functions not wrapped in injectable
     abstractions.
   - "No observable outcome to assert on" → a design smell (per the
     state-vs-behavior decision tree), not license for behavior verification.
   - For each, give a **concrete refactor** that increases testability (move
     logic down a layer, introduce a port/interface, inject the dependency,
     return state instead of relying on side effects).

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

Structure:
- **Summary** — scope, frameworks, governing source (strategy vs. stack-chapter
  override), and a **Counts** line: one number per category.
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
- Scale the depth to the scope: a quick diff review may fold Steps 4–6 into one
  lightweight pass; a whole-suite audit warrants the full draft → per-finding
  verification (with subagents) → consistency reconciliation.
