---
name: playwright-run
description: In a repository with a playwright.config.ts, run a subset of its Playwright tests, keep a persistent list of tests that already passed so they are not re-run, retain traces for failures, and debug failures with playwright-cli. Use when asked to run/rerun Playwright tests, run one suite or provider, continue a test run, check which tests still fail, or debug a failing test. Not for unit-test runners (jest, vitest, mocha) or repos without Playwright.
allowed-tools: Bash(node ~/.claude/skills/playwright-run/scripts/pw-run.mjs:*) Bash(npx playwright:*) Bash(playwright-cli:*) Read Edit Grep Glob
---

# Selective Playwright runs with a pass ledger

These are E2E tests against a live dev environment. A full run takes a long time and
costs real state (campaigns, deposits), so **never run the whole suite by default**.
Run what was asked, record what passed, and re-run only what is unresolved.

Everything goes through one script:

```bash
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs <command> [...]
```

`pw-run.mjs help` prints usage. Run it from the repo root — every path the script
resolves (`tests/`, `.env`, `.pw-runs/`) is relative to the current directory, not to
where the script lives.

## Before the first run in a repo

This is a personal skill, so it is offered in every repository. It was written against
the `playwright-sites` layout and assumes:

- a `playwright.config.ts` at the repo root (the script refuses to run without one)
- specs under `tests/`, with shared code in `tests/pom/**` and `tests/helpers/**`
- an auth dependency project backed by `tests/auth.setup.ts`, and projects named
  `unit` / `setup` that need no auth
- `@manual` as the tag for tests excluded by default
- environment selection through `.env` / `.env.$ENV` with `ENV`, `DEV_BRANCH`,
  `DEV_BASE_URL`

These live in the `CONFIG` block at the top of `scripts/pw-run.mjs`. In a repo that
differs, check `--dry-run` first and edit `CONFIG` rather than fighting the selection.

The script writes run artifacts to `.pw-runs/` in the repo it runs from. **Confirm
`.pw-runs/` is in that repo's `.gitignore` before the first real run** — traces and
videos are large and must not be committed.

## The loop

```bash
# 1. See what is already known to pass (and what still fails) before running anything
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs status

# 2. Run a scoped selection — already-passing tests are skipped automatically
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs run -g @calypso
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs run tests/bonusTests/freespins.spec.ts
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs run -g "Rollover: create and deplete"

# 3. Debug each failure (see references/debugging-failures.md)

# 4. Re-run only what failed; passes accumulate
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs run --failed
```

Selectors and `-g` are handed to Playwright unchanged, so anything from the README
works (`@bonus`, `@casinoverse`, `@payments`, `@apcopay`, a file, a `file:line`).

**Always scope the run.** If the request is vague ("run the tests"), pick the
narrowest selection that matches the work in progress — the suite touched by the
current branch or the last failures — and say which selection you chose. Only run
unscoped after the user confirms.

Add `--dry-run` to any `run` to see the exact selection and Playwright command without
executing anything or writing to disk — use it to confirm scope before a long run.

Runs are long. Start them in the background (or with a generous timeout) and follow
`.pw-runs/<runId>/run.log`; the summary at the end lists every failure with its trace.

## What the pass ledger does

`.pw-runs/ledger.json` records one entry per test. On the next run, a test is skipped
only when **all** of these hold:

- it is recorded as `passed`
- its spec file is byte-identical to when it passed
- `ENV`, `DEV_BRANCH` and `DEV_BASE_URL` match the current `.env` / `.env.$ENV`

Otherwise it runs again. Passing is per-environment: passes recorded on `ENV=8` are
never reused for `ENV=82`, because URLs, credentials and `DEV_BRANCH` behaviour differ.

A `flaky` or timed-out result is **not** a pass. Skipped tests are not recorded.

Changes to shared code (`tests/pom/**`, `tests/helpers/**`) cannot be attributed to
individual tests, so they do not auto-invalidate. The script warns when skipped passes
predate the current helper state; when helpers changed materially, re-verify:

```bash
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs run -g @payments --all   # ignore pass list once
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs forget --passed          # or drop passes for this env
```

`forget` also takes `--failed`, `--stale`, `--file <substr>`, `--grep <substr>`, `--all`.

## What you get for a failure

Every failure is reported as facts, not just a stack trace — from the run summary,
`failed`, and `explain`:

- **failed in** — the `test.step` trail that was running (`Bank: Calypso deposit`) and
  how long it ran before failing
- **assertion** — the matcher call (`expect(locator).toBeVisible() failed`), plus a
  custom assert **message** when the test supplied one
- **locator / expected / received / why** — what it looked for, what it wanted, what it
  got, and Playwright's reason (`element(s) not found`, `timeout`)
- **at / call chain** — the failing line, and the path into it from the test through the
  POM (`paymentProviderSuite.ts:193 -> calypso.spec.ts:81 -> bankPage.ts:89 -> :97`)

`explain [text]` adds the rest: the value **diff**, the **source** around the failing
line, Playwright's **call log**, the test's own stdout, the **action timeline** from the
trace (each action with its duration, cut at the failing action — so you see the flow
that led there), and whether the awaited text was anywhere in the **page snapshot**.

```bash
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs failed
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs explain "Calypso Deposit"
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs explain --actions 25   # longer timeline
```

Report these facts to the user in this shape — failing step, assertion, what was
missing, where — before proposing any cause. The timeline answers "at what point",
the page-snapshot line answers "what was missing".

The diagnosis is stored in the ledger, so `failed` and `explain` still work after the
run directory is pruned (the trace, video and timeline need the artifacts). If this
script's analysis improves, `reparse [runId]` re-derives ledger entries from a finished
run's `results.json` without re-running anything.

## Traces and other artifacts

Each run writes to `.pw-runs/<runId>/` (must be gitignored) — `results.json`, `run.log`,
`artifacts/` with the trace/video per test, and `html/` with `--html`. Because the
output dir is per-run, **a failure's trace is never wiped by the next run**.

```bash
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs failed    # failures + ready-made trace/debug commands
node ~/.claude/skills/playwright-run/scripts/pw-run.mjs trace calypso   # find a retained trace by substring
npx playwright show-trace .pw-runs/<runId>/artifacts/<test-dir>/trace.zip
```

The config keeps `trace: 'retain-on-failure'` and `video: 'on'`, so run dirs grow.
The script keeps the last 10 automatically; `prune --keep 3` trims harder.

## Rules that come from this repo

- **Never pass `--workers`.** It is pinned to `1` in `playwright.config.ts`; bonus
  campaigns and payment providers share global state that breaks under parallelism.
- **`@manual` tests are excluded** by default (they also need `RUN_MANUAL_TESTS=true`).
  Pass `--manual` to include them.
- **No retries by default.** Retries would hide flakiness and only the last attempt's
  trace survives. Use `--retries N` deliberately when checking for flakiness, and note
  that a flaky outcome is never ledgered as a pass.
- **The `setup` project always runs** (it refreshes `playwright/.auth/user.json`) and is
  never recorded in the ledger.

## When the auth setup fails, the run is BLOCKED

`chromium` depends on the `setup` project, so if `auth.setup.ts` fails (environment
unreachable, Cloudflare/WAF block, wrong credentials, BO login changed), every selected
test is skipped. That is **not** a test failure:

- the run reports `BLOCKED — the "setup" project failed, so N test(s) never ran`,
  with the same failure detail (assertion, why, source, trace) for the setup step
- **nothing is recorded** — no passes, no failures. `run --failed` will not help
- fix the environment, then re-run the same selection

Check the setup's page snapshot before blaming credentials — a WAF interstitial or an
error page looks exactly like "the username field never appeared".

## When a spec cannot even be loaded

Several specs throw at module scope when env vars are missing (e.g.
`calypso.spec.ts` requires `DEV_USER_USD`, `DEV_USER_USD_PASSWORD`,
`CALYPSO_DEPOSIT_INVOICE_ID`). One such file aborts collection for the *whole* suite.

The script detects this, re-enumerates with the offending files excluded, and reports
them as **"could not enumerate"** — distinct from a failure and never ledgered. Fix by
adding the missing vars to `.env` / `.env.$ENV` (see `.env.example`), or scope the run
to files that do load. Report these to the user; do not silently ignore them.

## Debugging failures

Read [references/debugging-failures.md](references/debugging-failures.md) before
touching a failing test. Short version: read the trace first, reproduce live with
`--debug=cli` + `playwright-cli attach`, fix the locator/expectation (or report an app
bug), then `run --failed` to confirm and move the test into the pass list.
