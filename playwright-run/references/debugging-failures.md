# Debugging a failed test

Order matters: understand the failure from the retained artifacts first, reproduce it
live only if the trace is not conclusive. Never "fix" a test by loosening an assertion
you have not understood.

## 1. Start with `explain`

```bash
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs explain "<part of the test title>"
```

This is the fastest complete picture, and usually enough to classify the failure:

- the `test.step` that was running and how long it ran before failing
- the matcher, the locator, expected vs received, and Playwright's reason
- the failing line with source context, and the call chain from test → POM → assertion
- the **action timeline** from the trace — every action with its duration, cut at the
  failing action, so you can see exactly how far the flow got
- whether the awaited text appears anywhere in the page snapshot at failure

`failed` prints the same header block for every failure without the deep detail.

State these facts before theorising. "The step `Bank: Calypso deposit` ran 33.4s; after
`goto /members/bank/deposit/tether` the text `Crypto Address:` never appeared" is a
diagnosis. "The Calypso test is broken" is not.

## 2. Go deeper into the trace when needed

```bash
npx playwright show-trace .pw-runs/<runId>/artifacts/<test-dir>/trace.zip
```

`show-trace` opens a viewer — useful for the user, less so for you. To inspect a trace
non-interactively, read it directly (this repo's history shows both working well):

```bash
unzip -l .pw-runs/<runId>/artifacts/<test-dir>/trace.zip
unzip -p .pw-runs/<runId>/artifacts/<test-dir>/trace.zip 0-trace.network | head -50
# response bodies live in resources/<sha>.json — the network entry gives the _sha1
```

Also read `.pw-runs/<runId>/run.log` for the full reporter output and any
`console.log` from the test's own logger.

What to establish before going further:

- Which action or expectation failed, and what the DOM looked like at that moment.
- Whether the page was in the expected state (logged in, right URL, right currency).
- Whether a backend call failed — check the network entries, not just the UI.

For what a trace contains, see
[../../playwright-cli/references/tracing.md](../../playwright-cli/references/tracing.md).

## 3. Reproduce live with playwright-cli

When the trace is not enough, pause the test at its start and drive the same browser
session by hand. Full instructions:
[../../playwright-cli/references/playwright-tests.md](../../playwright-cli/references/playwright-tests.md).

```bash
# background this, then poll the output until "Debugging Instructions" appears
PLAYWRIGHT_HTML_OPEN=never npx playwright test "<escaped test title>" --debug=cli

playwright-cli attach tw-abcdef      # session name comes from that output
playwright-cli snapshot
```

Keep the test process alive while you explore. Every `playwright-cli` action prints the
equivalent Playwright TypeScript, which is usually what belongs in the fix. Stop the
background run when done.

The wider `playwright-cli` command set is in
[../../playwright-cli/SKILL.md](../../playwright-cli/SKILL.md) — `snapshot`, `eval`,
`console`, `requests` and `generate-locator` are the ones that matter here.

## 4. Classify before editing

- **Test problem** — stale locator, missing wait, changed label, wrong assumption about
  `DEV_BRANCH` layout. Fix the test. Prefer role/testid locators and web-first
  assertions (`expect(...).toHaveText`) over manual waits.
- **Environment problem** — missing env var, dev box down, stale auth state, seeded data
  gone. Fix the environment or report it; do not change the test.
- **App bug** — the test is right and the app is wrong. Do not touch the test. Report it
  with the trace path and the failing step.

Say which of the three it is when you report back.

## 5. Confirm and bank the pass

```bash
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs run --failed
```

Only a green run moves a test into the pass list. If a test passes only sometimes,
re-run it a few times before trusting it:

```bash
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs run -g "<title>" --all --retries 0
```

Editing a spec file automatically invalidates its recorded passes, so a fix never leaves
a stale pass behind.
