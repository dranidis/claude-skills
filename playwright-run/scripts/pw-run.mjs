#!/usr/bin/env node
/**
 * pw-run — selective Playwright runs with a persistent pass ledger.
 *
 * Subcommands: run | status | failed | trace | forget | prune
 * See ../SKILL.md for the workflow. Run `pw-run.mjs help` for usage.
 *
 * Design notes (why things are the way they are):
 *  - Skipping already-passing tests uses Playwright's native `--test-list-invert`,
 *    so selection stays in Playwright's hands and dependency projects (the `setup`
 *    project) are never filtered away.
 *  - A pass is only trusted while (spec file hash, ENV, DEV_BRANCH, DEV_BASE_URL)
 *    are unchanged. These tests hit a live dev environment; env identity matters.
 *  - Artifacts go to a per-run directory so traces/videos of an old failure are
 *    never wiped by the next run (Playwright clears its output dir on start).
 */

import { spawn, spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// --- repo-specific configuration -------------------------------------------
const CONFIG = {
    runsDir: '.pw-runs',
    // Used only to re-enumerate tests when one spec fails to load (see listTests).
    testGlobs: ['tests/**/*.spec.ts', 'tests/**/*-test.ts', 'tests/**/*.setup.ts'],
    // Files backing dependency projects. Kept in every explicit test-list so the
    // auth storageState is always refreshed.
    alwaysInclude: ['tests/auth.setup.ts'],
    // Projects with no `dependencies` in playwright.config.ts — they need no auth setup.
    depFreeProjects: ['unit', 'setup'],
    // Hashed to detect POM/helper changes that invalidate recorded passes.
    supportDir: 'tests',
    defaultGrepInvert: '@manual',
    keepRuns: 10,
    envKeyVars: ['ENV', 'DEV_BRANCH', 'DEV_BASE_URL'],
};

const ROOT = process.cwd();
const RUNS = path.join(ROOT, CONFIG.runsDir);
const LEDGER = path.join(RUNS, 'ledger.json');
const ANSI = new RegExp(`${String.fromCharCode(27)}\\[[0-9;]*m`, 'g');

// --- tiny helpers ----------------------------------------------------------
const sha = (s) => crypto.createHash('sha256').update(s).digest('hex').slice(0, 16);
const posix = (p) => p.split(path.sep).join('/');
const rel = (p) => posix(path.relative(ROOT, path.resolve(ROOT, p)));

function die(msg) {
    console.error(`pw-run: ${msg}`);
    process.exit(2);
}

function walk(dir, out = []) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (e.name === 'node_modules' || e.name.startsWith('.')) continue;
        const p = path.join(dir, e.name);
        if (e.isDirectory()) walk(p, out);
        else out.push(p);
    }
    return out;
}

/** Minimal glob support for CONFIG.testGlobs: `**` / and `*` within a segment. */
function globToRe(glob) {
    let re = '';
    for (let i = 0; i < glob.length; i++) {
        if (glob.startsWith('**/', i)) {
            re += '(?:.*/)?';
            i += 2;
        } else if (glob[i] === '*') {
            re += '[^/]*';
        } else {
            re += /[.+^${}()|[\]\\?]/.test(glob[i]) ? `\\${glob[i]}` : glob[i];
        }
    }
    return new RegExp(`^${re}$`);
}

function allTestFiles() {
    const res = CONFIG.testGlobs.map(globToRe);
    return walk(path.join(ROOT, 'tests'))
        .map(rel)
        .filter((f) => res.some((re) => re.test(f)))
        .sort();
}

// --- environment identity --------------------------------------------------
/** Mirrors playwright.config.ts: .env first, then .env.$ENV; process.env wins. */
function resolveEnv() {
    const parse = (file) => {
        const p = path.join(ROOT, file);
        if (!fs.existsSync(p)) return {};
        const out = {};
        for (const line of fs.readFileSync(p, 'utf8').split('\n')) {
            if (line.trim().startsWith('#')) continue;
            const m = /^\s*([\w.-]+)\s*=\s*(.*)?\s*$/.exec(line);
            if (!m) continue;
            out[m[1]] = (m[2] ?? '').trim().replace(/^(['"])([\s\S]*)\1$/, '$2');
        }
        return out;
    };
    const base = parse('.env');
    const selector = { ...base, ...process.env }.ENV;
    const specific = selector ? parse(`.env.${selector}`) : {};
    return { ...specific, ...base, ...process.env };
}

function envKey(env) {
    return CONFIG.envKeyVars.map((k) => `${k}=${env[k] ?? ''}`).join('|');
}

function supportHash() {
    // Everything under tests/ that is not itself a test file: POMs, helpers, fixtures.
    const testFiles = new Set(allTestFiles());
    const parts = walk(path.join(ROOT, CONFIG.supportDir))
        .map(rel)
        .filter((f) => !testFiles.has(f))
        .sort()
        .map((f) => `${f}:${sha(fs.readFileSync(path.join(ROOT, f)))}`);
    return sha(parts.join('\n'));
}

function specHash(file) {
    const p = path.join(ROOT, file);
    return fs.existsSync(p) ? sha(fs.readFileSync(p)) : 'missing';
}

// --- ledger ----------------------------------------------------------------
function loadLedger() {
    if (!fs.existsSync(LEDGER)) return { version: 1, entries: {} };
    try {
        const l = JSON.parse(fs.readFileSync(LEDGER, 'utf8'));
        l.entries ??= {};
        return l;
    } catch (e) {
        die(`ledger at ${rel(LEDGER)} is unreadable (${e.message}). Delete it or fix it by hand.`);
    }
}

function saveLedger(ledger) {
    fs.mkdirSync(RUNS, { recursive: true });
    const tmp = `${LEDGER}.tmp`;
    fs.writeFileSync(tmp, `${JSON.stringify(ledger, null, 2)}\n`);
    fs.renameSync(tmp, LEDGER);
}

// Playwright's --test-list line format: `[project] <sep> file <sep> title <sep> title`
const SEP = '›';
const descriptor = (t) => `[${t.project}] ${SEP} ${t.file}${t.titlePath.map((x) => ` ${SEP} ${x}`).join('')}`;
const ledgerKey = (t, ek) => `${ek} ${descriptor(t)}`;

/** A recorded pass is only honoured when env identity and spec content match. */
function isTrustedPass(entry, ek) {
    return entry?.status === 'passed' && entry.envKey === ek && entry.specHash === specHash(entry.file);
}

// --- failure analysis ------------------------------------------------------
/**
 * Turn a failed result into the facts a reader needs: which step was running,
 * which assertion failed, what it wanted, and where in the call chain it sat.
 * The JSON reporter only serialises steps that carry an error, so the step trail
 * is the failing branch — the surrounding flow comes from the call chain and,
 * in `explain`, from the trace's action timeline.
 */
function describeFailure(result) {
    // Deepest error-bearing step chain, e.g. "Bank: Calypso deposit".
    const trail = [];
    let durationMs;
    let stepError;
    let steps = result.steps ?? [];
    while (steps.length) {
        const failing = steps.find((s) => s.error) ?? null;
        if (!failing) break;
        trail.push(failing.title);
        durationMs = failing.duration ?? durationMs;
        stepError = failing.error ?? stepError;
        steps = failing.steps ?? [];
    }

    // result.errors[] carries only message + location; the stack and source snippet
    // live on the failing step's error, so fall back to it for those.
    const top = result.errors?.[0] ?? result.error ?? {};
    const err = { ...stepError, ...top };
    const message = (err.message ?? '').replace(ANSI, '');
    const stack = (err.stack ?? stepError?.stack ?? '').replace(ANSI, '');
    const lines = message.split('\n');

    // `Locator:` / `Expected:` / `Received:` / `Timeout:` / trailing `Error:` detail,
    // plus the call log and (for equality matchers) the expected/received diff block.
    const fields = {};
    const callLog = [];
    const diff = [];
    let inCallLog = false;
    let inDiff = false;
    for (const raw of lines.slice(1)) {
        const line = raw.trim();
        if (/^Call log:?$/i.test(line)) {
            inCallLog = true;
            inDiff = false;
            continue;
        }
        if (inCallLog) {
            if (line.startsWith('-')) callLog.push(line.replace(/^-\s*/, ''));
            continue;
        }
        if (/^[-+] (Expected|Received)/.test(line)) inDiff = true;
        if (inDiff) {
            // The diff ends where the stack or the source snippet begins.
            if (/^\s*at /.test(raw) || /^\s*>?\s*\d+ \|/.test(raw)) inDiff = false;
            else if (diff.length < 24) diff.push(raw.replace(/\s+$/, ''));
            continue;
        }
        const m = /^(Locator|Expected|Received|Timeout|Error|Expected pattern|Expected string):\s*(.*)$/.exec(line);
        if (m && m[2]) fields[m[1]] = m[2];
    }

    while (diff.length && !diff.at(-1).trim()) diff.pop();

    // The matcher call is on line 1 for locator assertions, but below a custom
    // message for value assertions — find it wherever it is.
    const matcher = lines.find((l) => /^expect\(.*\)\.\w+/.test(l.trim()))?.trim();
    const first = (lines[0] ?? '').replace(/^Error:\s*/, '').trim();

    // Repo frames only — node_modules and playwright internals are noise here.
    const chain = [];
    for (const line of stack.split('\n')) {
        const m = /^\s+at (?:(.+?) \()?(\/[^):]+):(\d+):(\d+)\)?/.exec(line);
        if (!m) continue;
        const file = rel(m[2]);
        if (file.startsWith('..') || file.includes('node_modules')) continue;
        chain.push({ fn: m[1] && !m[1].startsWith('/') ? m[1] : undefined, file, line: Number(m[3]) });
    }

    const loc = err.location ?? result.errorLocation;
    return {
        step: trail.join(' > ') || undefined,
        stepDurationMs: durationMs,
        headline: matcher ?? first ?? 'test failed',
        // A custom assert message (or a thrown error) when it isn't the matcher itself.
        message: matcher && first && first !== matcher ? first : undefined,
        diff: diff.length ? diff : undefined,
        locator: fields.Locator,
        expected: fields.Expected ?? fields['Expected pattern'] ?? fields['Expected string'],
        received: fields.Received,
        timeout: fields.Timeout,
        reason: fields.Error,
        at: loc ? `${rel(loc.file)}:${loc.line}` : chain[0] && `${chain[0].file}:${chain[0].line}`,
        // Outermost (the test) to innermost (the assertion) — reads as the flow.
        chain: [...chain].reverse().map((c) => `${c.file}:${c.line}${c.fn ? ` (${c.fn})` : ''}`),
        callLog,
        stdoutTail: (result.stdout ?? [])
            .map((c) => (typeof c === 'string' ? c : c.text ?? ''))
            .join('')
            .replace(ANSI, '')
            .trimEnd()
            .split('\n')
            .slice(-6),
    };
}

/** Concise, factual failure block. `verbose` adds source, call log and stdout. */
function printFailure(entry, { verbose = false } = {}) {
    const f = entry.failure ?? {};
    const pad = (label) => `    ${label.padEnd(13)}`;
    console.log(`\n  ${descriptor(entry)}`);
    if (f.step) {
        const dur = f.stepDurationMs ? ` (failed after ${(f.stepDurationMs / 1000).toFixed(1)}s)` : '';
        console.log(`${pad('failed in:')}step "${f.step}"${dur}`);
    }
    console.log(`${pad('assertion:')}${f.headline ?? entry.error ?? 'unknown'}`);
    if (f.message) console.log(`${pad('message:')}${f.message}`);
    if (f.locator) console.log(`${pad('locator:')}${f.locator}`);
    if (f.expected) console.log(`${pad('expected:')}${f.expected}${f.timeout ? `   (timeout ${f.timeout})` : ''}`);
    if (f.received) console.log(`${pad('received:')}${f.received}`);
    if (f.reason) console.log(`${pad('why:')}${f.reason}`);
    if (f.at) console.log(`${pad('at:')}${f.at}`);
    if (f.chain?.length > 1) console.log(`${pad('call chain:')}${f.chain.join('  ->  ')}`);

    if (verbose) {
        if (f.diff) {
            console.log(`${pad('diff:')}`);
            for (const l of f.diff) console.log(`      ${l}`);
        }
        if (f.at) printSource(f.at);
        if (f.callLog?.length) {
            console.log(`${pad('call log:')}`);
            for (const l of f.callLog) console.log(`      - ${l}`);
        }
        if (f.stdoutTail?.some((l) => l.trim())) {
            console.log(`${pad('test output:')}`);
            for (const l of f.stdoutTail) if (l.trim()) console.log(`      ${l}`);
        }
    }
    if (entry.trace) console.log(`${pad('trace:')}npx playwright show-trace ${entry.trace}`);
    if (entry.video) console.log(`${pad('video:')}${entry.video}`);
}

function printSource(at, context = 3) {
    const [file, lineNo] = [at.replace(/:\d+$/, ''), Number(at.match(/:(\d+)$/)?.[1])];
    const abs = path.join(ROOT, file);
    if (!fs.existsSync(abs) || !lineNo) return;
    const src = fs.readFileSync(abs, 'utf8').split('\n');
    console.log(`    source:      ${file}:${lineNo}`);
    for (let i = Math.max(1, lineNo - context); i <= Math.min(src.length, lineNo + 1); i++) {
        const marker = i === lineNo ? '>' : ' ';
        console.log(`      ${marker} ${String(i).padStart(4)} | ${src[i - 1]}`);
    }
}

/**
 * Action timeline leading to the failure, read from the trace. Answers "at what
 * point" with real timings. Needs `unzip`; degrades to a note when unavailable.
 */
function traceTimeline(tracePath, limit = 10) {
    const abs = path.join(ROOT, tracePath);
    if (!fs.existsSync(abs)) return { error: `trace not found at ${tracePath}` };
    const listing = spawnSync('unzip', ['-Z1', abs], { encoding: 'utf8' });
    if (listing.error) return { error: 'unzip is not available — open the trace with `npx playwright show-trace`' };
    // One stream per browser context (these tests drive both Dev and Backoffice).
    // Timestamps are not comparable across streams, so instead of merging we show the
    // stream that actually contains the failure, cut at the failing action — actions
    // after it belong to teardown and would only mislead.
    // Browser contexts produce `0-trace.trace`, `1-trace.trace`, …; a browserless
    // test (the `unit` project) produces a single `test.trace`.
    const names = (listing.stdout ?? '')
        .split('\n')
        .map((n) => n.trim())
        .filter((n) => /\.trace$/.test(n) && !n.includes('/'));
    if (!names.length) return { error: 'no trace stream inside the archive' };

    const streams = [];
    for (const name of names) {
        const actions = [];
        const dump = spawnSync('unzip', ['-p', abs, name], { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });
        const before = new Map();
        for (const line of (dump.stdout ?? '').split('\n')) {
            if (!line) continue;
            let e;
            try {
                e = JSON.parse(line);
            } catch {
                continue;
            }
            if (e.type === 'before') before.set(e.callId, e);
            else if (e.type === 'after') {
                const b = before.get(e.callId);
                if (!b) continue;
                const p = b.params ?? {};
                const hint = p.url ?? p.selector ?? p.text ?? p.value ?? '';
                actions.push({
                    title: `${b.class}.${b.method}`,
                    hint: String(hint).slice(0, 90),
                    ms: Math.round((e.endTime ?? 0) - (b.startTime ?? 0)),
                    failed: !!e.error,
                });
            }
        }
        streams.push({ name, actions });
    }

    // Both the test-level stream (`test.trace`) and the per-context streams
    // (`0-trace.trace`, …) record the failure, but only the context streams name real
    // API calls with their URLs/selectors — `test.trace` degrades everything to
    // `Test.pw:api`. Prefer a context stream, then the one with the most actions.
    const isContext = (s) => (/^\d+-trace\.trace$/.test(s.name) ? 1 : 0);
    const rank = (a, b) => isContext(b) - isContext(a) || b.actions.length - a.actions.length;
    const withFailure = streams.filter((s) => s.actions.some((a) => a.failed)).sort(rank)[0];
    const pick = withFailure ?? [...streams].sort(rank)[0];
    if (!pick?.actions.length) return { error: 'trace contains no recorded actions' };
    const lastFailed = pick.actions.reduce((acc, a, i) => (a.failed ? i : acc), -1);
    const end = lastFailed >= 0 ? lastFailed + 1 : pick.actions.length;
    return {
        actions: pick.actions.slice(Math.max(0, end - limit), end),
        total: pick.actions.length,
        contexts: streams.length,
        cutAtFailure: lastFailed >= 0,
        afterFailure: pick.actions.length - end,
    };
}

/** Did the text the locator wanted appear anywhere in the failure snapshot? */
function snapshotEvidence(tracePath, locator) {
    const ctx = path.join(ROOT, path.dirname(tracePath), 'error-context.md');
    const text = locator?.match(/['"]([^'"]{3,})['"]/)?.[1];
    if (!fs.existsSync(ctx) || !text) return null;
    const snap = fs.readFileSync(ctx, 'utf8');
    const present = snap.includes(text);
    const word = text.split(/\s+/)[0].replace(/[^\w]/g, '');
    const near = word.length > 2 ? snap.split('\n').filter((l) => l.includes(word)).length : 0;
    return { file: rel(ctx), text, present, near, word };
}

// --- enumeration -----------------------------------------------------------
/** Walk the JSON reporter tree into flat {project, file, titlePath, ...} records. */
function flattenReport(json, withResults = false) {
    const out = [];
    const visit = (suite, titles) => {
        const file = suite.file ? rel(suite.file) : undefined;
        const own = suite.title && suite.title !== file && suite.title !== suite.file ? [suite.title] : [];
        const trail = [...titles, ...own];
        for (const spec of suite.specs ?? []) {
            for (const t of spec.tests ?? []) {
                const record = {
                    project: t.projectName,
                    file: rel(spec.file ?? suite.file),
                    titlePath: [...trail, spec.title],
                    line: spec.line,
                    tags: spec.tags ?? [],
                };
                if (withResults) {
                    const last = (t.results ?? []).at(-1) ?? {};
                    const attach = (name) => (last.attachments ?? []).find((a) => a.name === name)?.path;
                    // expected | unexpected | flaky | skipped
                    record.status = t.status;
                    record.durationMs = last.duration;
                    record.trace = attach('trace');
                    record.video = attach('video');
                    if (t.status !== 'expected' && t.status !== 'skipped') {
                        record.failure = describeFailure(last);
                        record.error = record.failure.headline;
                    }
                }
                out.push(record);
            }
        }
        for (const child of suite.suites ?? []) visit(child, trail);
    };
    for (const s of json.suites ?? []) visit(s, []);
    return out;
}

function collectionErrors(json) {
    const seen = new Map();
    for (const e of json.errors ?? []) {
        const file = e.location?.file ? rel(e.location.file) : null;
        if (!file) continue;
        if (!seen.has(file)) seen.set(file, (e.message ?? '').replace(ANSI, '').split('\n')[0]);
    }
    return [...seen].map(([file, message]) => ({ file, message }));
}

function pwSync(args, extraEnv = {}) {
    return spawnSync('npx', ['playwright', ...args], {
        cwd: ROOT,
        env: { ...process.env, ...extraEnv },
        encoding: 'utf8',
        maxBuffer: 64 * 1024 * 1024,
    });
}

/**
 * Enumerate selected tests. One spec that throws at module scope (missing env var,
 * for example) aborts collection for the whole suite, so on that failure we retry
 * with the offending files excluded and report them separately.
 */
function listTests(selectors, grep, grepInvert) {
    const tmp = path.join(os.tmpdir(), `pw-run-list-${process.pid}.json`);
    const attempt = (positionals) => {
        const args = ['test', '--list', '--reporter=json'];
        if (grep) args.push('--grep', grep);
        if (grepInvert) args.push('--grep-invert', grepInvert);
        args.push(...positionals);
        pwSync(args, { PLAYWRIGHT_JSON_OUTPUT_FILE: tmp, PLAYWRIGHT_HTML_OPEN: 'never' });
        if (!fs.existsSync(tmp)) return null;
        const json = JSON.parse(fs.readFileSync(tmp, 'utf8'));
        fs.rmSync(tmp, { force: true });
        return json;
    };

    const json = attempt(selectors);
    if (!json) die('could not enumerate tests — `npx playwright test --list` produced no JSON report.');
    const broken = collectionErrors(json);

    if (flattenReport(json).length === 0 && broken.length > 0) {
        // Retry without the files that failed to load.
        const brokenSet = new Set(broken.map((b) => b.file));
        const positionals = selectors.length
            ? selectors.filter((s) => !brokenSet.has(s.replace(/:\d+(:\d+)?$/, '')))
            : allTestFiles().filter((f) => !brokenSet.has(f));
        if (positionals.length === 0) return { tests: [], excluded: broken, broken, selectors };
        const retry = attempt(positionals);
        if (retry) {
            // The run must use the same narrowed file set, otherwise the broken spec
            // is loaded again and takes the whole run down with it.
            return {
                tests: flattenReport(retry),
                excluded: broken,
                broken: collectionErrors(retry),
                selectors: positionals,
            };
        }
    }
    return { tests: flattenReport(json), excluded: [], broken, selectors };
}

// --- run -------------------------------------------------------------------
function runId() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, '0');
    const day = `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`;
    return `${day}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function writeTestList(file, tests, { includeDeps }) {
    const lines = tests.map(descriptor);
    if (includeDeps) lines.unshift(...CONFIG.alwaysInclude);
    fs.writeFileSync(file, `${lines.join('\n')}\n`);
    return lines.length;
}

const escapeGrep = (s) => String(s ?? '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Fold one run's results into the ledger. Returns what passed and what failed. */
function recordResults(ledger, results, { ek, support, id }) {
    const now = new Date().toISOString();
    let passed = 0;
    const failed = [];
    const blocked = [];
    for (const r of results) {
        // A failed dependency project (auth setup) blocks everything downstream. It is
        // never ledgered — re-running "the failure" would be meaningless — but it must
        // be surfaced, or a fully blocked run reads as "0 passed, 0 failed".
        if (r.project === 'setup') {
            if (r.status !== 'expected' && r.status !== 'skipped') blocked.push(r);
            continue;
        }
        if (r.status === 'skipped') continue;
        const common = {
            project: r.project,
            file: r.file,
            titlePath: r.titlePath,
            envKey: ek,
            specHash: specHash(r.file),
            supportHash: support,
            at: now,
            runId: id,
        };
        if (r.status === 'expected') {
            passed++;
            ledger.entries[ledgerKey(r, ek)] = { status: 'passed', ...common, durationMs: r.durationMs };
        } else {
            // unexpected | flaky | timedOut — none of these count as a pass.
            failed.push(r);
            ledger.entries[ledgerKey(r, ek)] = {
                status: r.status === 'flaky' ? 'flaky' : 'failed',
                ...common,
                error: r.error,
                // Kept in the ledger so the diagnosis survives after run dirs are pruned.
                failure: r.failure,
                trace: r.trace ? rel(r.trace) : undefined,
                video: r.video ? rel(r.video) : undefined,
            };
        }
    }
    ledger.meta = { updatedAt: now, supportHash: support, lastRunId: id };
    saveLedger(ledger);
    return { passed, failed, blocked };
}

function streamPlaywright(args, extraEnv, logPath) {
    return new Promise((resolve) => {
        const log = fs.createWriteStream(logPath);
        const child = spawn('npx', ['playwright', ...args], {
            cwd: ROOT,
            env: { ...process.env, ...extraEnv },
            stdio: ['inherit', 'pipe', 'pipe'],
        });
        child.stdout.on('data', (d) => {
            process.stdout.write(d);
            log.write(d);
        });
        child.stderr.on('data', (d) => {
            process.stderr.write(d);
            log.write(d);
        });
        child.on('close', (code) => {
            log.end();
            resolve(code ?? 1);
        });
    });
}

async function cmdRun(argv) {
    const opts = parseArgs(argv, {
        flags: ['all', 'failed', 'manual', 'html', 'headed', 'dry-run'],
        values: ['grep', 'grep-invert', 'project', 'retries', 'max-failures', 'timeout'],
    });
    const ek = envKey(resolveEnv());
    const ledger = loadLedger();
    const support = supportHash();

    // @manual stays excluded even when the caller passes their own --grep-invert.
    const invert = [...(opts.manual ? [] : [CONFIG.defaultGrepInvert]), ...(opts['grep-invert'] ? [opts['grep-invert']] : [])];
    const grepInvert = invert.length ? invert.join('|') : undefined;
    const { tests, excluded, broken, selectors } = listTests(opts._, opts.grep, grepInvert);

    console.log(`env: ${ek}`);
    if (excluded.length) {
        console.log('\ncould not enumerate (spec failed to load — excluded from this run):');
        for (const b of excluded) console.log(`  ${b.file}\n    ${b.message}`);
    }
    for (const b of broken) console.log(`  load error in ${b.file}: ${b.message}`);

    if (!tests.length) {
        console.log('\nno tests selected.');
        return excluded.length ? 1 : 0;
    }

    // Partition the selection against the ledger.
    const skip = [];
    const toRun = [];
    for (const t of tests) {
        if (t.project === 'setup') continue; // dependency project, never ledgered
        const entry = ledger.entries[ledgerKey(t, ek)];
        if (!opts.all && !opts.failed && isTrustedPass(entry, ek)) skip.push({ t, entry });
        else toRun.push(t);
    }

    let selected = toRun;
    if (opts.failed) {
        selected = tests.filter((t) => {
            const e = ledger.entries[ledgerKey(t, ek)];
            return e && e.status !== 'passed';
        });
        if (!selected.length) {
            console.log('\nno recorded failures for this env/selection — nothing to re-run.');
            return 0;
        }
    }

    if (opts.failed) {
        console.log(`\nre-running ${selected.length} recorded failure(s) out of ${tests.length} selected test(s)`);
    } else {
        console.log(
            `\nselected ${tests.length} test(s): running ${selected.length}, skipping ${skip.length} already passing` +
                `${opts.all ? ' (--all: pass list ignored)' : ''}`,
        );
    }
    const staleSupport = skip.filter(({ entry }) => entry.supportHash && entry.supportHash !== support);
    if (staleSupport.length) {
        console.log(
            `\n[!] shared code under ${CONFIG.supportDir}/ changed since ${staleSupport.length} of the skipped pass(es) were recorded.\n` +
                '    Their spec files are unchanged, so they are still skipped. Use --all to re-verify, or `forget --passed`.',
        );
    }
    if (!selected.length) {
        console.log('\nnothing to run — everything selected has already passed. Use --all to force.');
        return 0;
    }

    const dry = !!opts['dry-run'];
    const id = runId();
    const dir = path.join(RUNS, id);
    // --dry-run must leave no trace on disk, so the run dir is created lazily.
    if (!dry) fs.mkdirSync(dir, { recursive: true });
    const listFile = path.join(dir, 'test-list.txt');
    const invertFile = path.join(dir, 'skip-list.txt');
    const writeList = (file, list, o) => (dry ? list.length : writeTestList(file, list, o));

    const args = ['test'];
    if (opts.failed) {
        // Only pull in the auth setup when a selected test actually depends on it.
        const needsDeps = selected.some((t) => !CONFIG.depFreeProjects.includes(t.project));
        writeList(listFile, selected, { includeDeps: needsDeps });
        // Positionals stay as `selectors` — never the tests' own files. Tests declared in
        // shared suites (tests/casinoverseTests/reusableTests/*, paymentProviderSuite.ts)
        // report their declaration file, which matches no project's testMatch and would
        // select zero tests. `selectors` is already narrowed when a spec failed to load.
        args.push(...selectors);
        args.push(`--test-list=${listFile}`);
    } else {
        args.push(...selectors);
        if (opts.grep) args.push('--grep', opts.grep);
        if (grepInvert) args.push('--grep-invert', grepInvert);
        if (skip.length) {
            writeList(
                invertFile,
                skip.map(({ t }) => t),
                { includeDeps: false },
            );
            args.push(`--test-list-invert=${invertFile}`);
        }
    }
    if (opts.project) args.push('--project', opts.project);
    if (opts.retries) args.push('--retries', opts.retries);
    if (opts['max-failures']) args.push('--max-failures', opts['max-failures']);
    if (opts.timeout) args.push('--timeout', opts.timeout);
    if (opts.headed) args.push('--headed');
    // workers is pinned to 1 in playwright.config.ts on purpose — never overridden here.
    args.push('--trace=retain-on-failure', `--output=${path.join(dir, 'artifacts')}`);
    args.push(`--reporter=list,json${opts.html ? ',html' : ''}`);

    const childEnv = {
        PLAYWRIGHT_JSON_OUTPUT_FILE: path.join(dir, 'results.json'),
        PLAYWRIGHT_HTML_OUTPUT_DIR: path.join(dir, 'html'),
        PLAYWRIGHT_HTML_OPEN: 'never',
    };

    console.log(`\nrun dir: ${rel(dir)}${dry ? ' (not created — dry run)' : ''}`);
    // Quote anything the shell would mangle, so the printed command is copy-pasteable.
    const shellSafe = (a) => (/[\s|&;<>()$`\\"'*?[\]]/.test(a) ? JSON.stringify(a) : a);
    console.log(`command: npx playwright ${args.map(shellSafe).join(' ')}\n`);
    if (dry) {
        console.log('--dry-run: nothing executed, nothing written. Tests that would run:');
        for (const t of selected) console.log(`  ${descriptor(t)}`);
        return 0;
    }

    const code = await streamPlaywright(args, childEnv, path.join(dir, 'run.log'));

    // --- record outcomes ---
    const reportPath = path.join(dir, 'results.json');
    if (!fs.existsSync(reportPath)) {
        console.log(`\npw-run: no JSON report at ${rel(reportPath)} — ledger not updated. Exit code ${code}.`);
        return code || 1;
    }
    const results = flattenReport(JSON.parse(fs.readFileSync(reportPath, 'utf8')), true);
    const { passed, failed, blocked } = recordResults(ledger, results, { ek, support, id });
    prune(CONFIG.keepRuns, true);

    console.log(`\n${'-'.repeat(72)}`);
    const notRunCount = results.filter((r) => r.project !== 'setup' && r.status === 'skipped').length;
    if (blocked.length) {
        console.log(
            `run ${id}: BLOCKED — the "${blocked[0].project}" project failed, so ${notRunCount || 'the selected'} test(s) never ran.`,
        );
        console.log('Nothing was recorded: this is not a test failure, and `run --failed` will not help.');
        console.log('\nwhy the run could not start:');
        for (const b of blocked) {
            printFailure({ ...b, trace: b.trace && rel(b.trace), video: b.video && rel(b.video) }, { verbose: true });
        }
        console.log(
            '\nCheck that the environment is reachable and the credentials in .env / .env.$ENV are right,\n' +
                'then re-run the same selection.',
        );
        console.log(`\nartifacts: ${rel(dir)}   ledger: ${rel(LEDGER)} (unchanged)`);
        return code || 1;
    }
    console.log(`run ${id}: ${passed} passed (added to pass list), ${failed.length} failed`);
    if (excluded.length) console.log(`${excluded.length} spec file(s) could not be loaded (see above)`);
    if (failed.length) {
        console.log('\nfailed tests — traces retained:');
        for (const f of failed) {
            printFailure({ ...f, trace: f.trace && rel(f.trace), video: f.video && rel(f.video) });
            console.log(`    debug:       npx playwright test -g "${escapeGrep(f.titlePath.at(-1))}" --debug=cli`);
            console.log(`    explain:     pw-run.mjs explain "${f.titlePath.at(-1)}"`);
        }
        if (notRunCount) {
            console.log(
                `\n${notRunCount} test(s) never ran (serial suite stopped at the failure) — not recorded either way.`,
            );
        }
        console.log('\nfull diagnosis: pw-run.mjs explain    |    re-run once fixed: pw-run.mjs run --failed');
    } else if (passed) {
        console.log('\nall selected tests passed. They will be skipped on the next run.');
    }
    console.log(`\nartifacts: ${rel(dir)}   ledger: ${rel(LEDGER)}`);
    return failed.length ? 1 : code;
}

// --- status / failed / trace / forget / prune ------------------------------
function entriesFor(ledger, ek, { anyEnv = false } = {}) {
    return Object.entries(ledger.entries)
        .filter(([, e]) => anyEnv || e.envKey === ek)
        .map(([key, e]) => ({ key, ...e }));
}

function age(iso) {
    if (!iso) return '?';
    const h = (Date.now() - Date.parse(iso)) / 36e5;
    if (h < 1) return `${Math.round(h * 60)}m ago`;
    if (h < 48) return `${Math.round(h)}h ago`;
    return `${Math.round(h / 24)}d ago`;
}

function cmdStatus(argv) {
    const opts = parseArgs(argv, { flags: ['all-envs', 'verbose'], values: [] });
    const ek = envKey(resolveEnv());
    const support = supportHash();
    const all = entriesFor(loadLedger(), ek, { anyEnv: opts['all-envs'] });

    console.log(`env: ${ek}`);
    if (!all.length) {
        console.log('pass list is empty for this env — the next run will run everything selected.');
        return 0;
    }
    const passes = all.filter((e) => e.status === 'passed');
    const fails = all.filter((e) => e.status !== 'passed');
    const stale = passes.filter((e) => e.specHash !== specHash(e.file));
    const supportStale = passes.filter((e) => e.supportHash && e.supportHash !== support);

    console.log(
        `\n${passes.length} passing, ${fails.length} failing, ${stale.length} stale (spec file changed → will re-run)`,
    );
    if (supportStale.length) {
        console.log(
            `[!] ${supportStale.length} pass(es) predate the current state of ${CONFIG.supportDir}/ helpers` +
                ' — re-verify with `run --all` if that matters.',
        );
    }

    const byFile = new Map();
    for (const e of passes) byFile.set(e.file, (byFile.get(e.file) ?? 0) + 1);
    console.log('\npassing by file:');
    for (const [file, n] of [...byFile].sort()) console.log(`  ${String(n).padStart(3)}  ${file}`);

    if (opts.verbose) {
        console.log('\npassing tests:');
        for (const e of [...passes].sort((a, b) => a.file.localeCompare(b.file))) {
            const flag = e.specHash !== specHash(e.file) ? ', STALE' : '';
            console.log(`  ${descriptor(e)}   (${age(e.at)}${flag})`);
        }
    }
    if (fails.length) {
        console.log('\nfailing:');
        for (const e of fails) {
            console.log(`  ${descriptor(e)}   (${e.status}, ${age(e.at)})`);
            if (e.error) console.log(`      ${e.error}`);
            if (e.trace) console.log(`      npx playwright show-trace ${e.trace}`);
        }
    }
    const oldest = passes.map((e) => e.at).sort()[0];
    if (oldest) console.log(`\noldest recorded pass: ${age(oldest)}`);
    return 0;
}

function cmdFailed(argv) {
    const opts = parseArgs(argv, { flags: ['list-file'], values: [] });
    const ek = envKey(resolveEnv());
    const fails = entriesFor(loadLedger(), ek).filter((e) => e.status !== 'passed');
    if (!fails.length) {
        console.log('no recorded failures for this env.');
        return 0;
    }
    if (opts['list-file']) {
        const out = path.join(RUNS, 'failed.txt');
        fs.mkdirSync(RUNS, { recursive: true });
        fs.writeFileSync(out, `${[...CONFIG.alwaysInclude, ...fails.map(descriptor)].join('\n')}\n`);
        console.log(rel(out));
        return 0;
    }
    for (const e of fails) {
        printFailure(e);
        console.log(`    debug:       npx playwright test -g "${escapeGrep(e.titlePath.at(-1))}" --debug=cli`);
        console.log(`    explain:     pw-run.mjs explain "${e.titlePath.at(-1)}"`);
    }
    return 0;
}

/**
 * Everything known about a failure: the concise block, the source line, the call
 * log, the action timeline from the trace, and whether the awaited text was
 * anywhere in the page snapshot.
 */
function cmdExplain(argv) {
    const opts = parseArgs(argv, { flags: [], values: ['actions'] });
    const needle = opts._.join(' ').toLowerCase();
    const ek = envKey(resolveEnv());
    const fails = entriesFor(loadLedger(), ek)
        .filter((e) => e.status !== 'passed')
        .filter((e) => !needle || descriptor(e).toLowerCase().includes(needle));
    if (!fails.length) {
        console.log(
            needle
                ? `no recorded failure matches "${needle}". \`pw-run.mjs failed\` lists them.`
                : 'no recorded failures for this env.',
        );
        return 1;
    }

    for (const e of fails) {
        console.log(`${'='.repeat(72)}`);
        printFailure(e, { verbose: true });

        const f = e.failure ?? {};
        if (e.trace) {
            const t = traceTimeline(e.trace, Number(opts.actions ?? 10));
            if (t.error) {
                console.log(`    timeline:    unavailable (${t.error})`);
            } else {
                const scope = t.cutAtFailure ? 'ending at the failing action' : 'end of the run (no failing action recorded)';
                console.log(
                    `    timeline:    ${t.actions.length} of ${t.total} actions in this browser context, ${scope}` +
                        (t.contexts > 1 ? `; ${t.contexts} contexts traced` : ''),
                );
                for (const a of t.actions) {
                    const mark = a.failed ? 'FAILED  ' : '        ';
                    const secs = `${(a.ms / 1000).toFixed(1)}s`.padStart(7);
                    console.log(`      ${mark}${secs}  ${a.title}${a.hint ? `  ${a.hint}` : ''}`);
                }
            }
            const ev = snapshotEvidence(e.trace, f.locator);
            if (ev) {
                console.log(`    page state:  snapshot at failure: ${ev.file}`);
                console.log(
                    ev.present
                        ? `      "${ev.text}" IS present in the snapshot — the assertion likely failed on visibility, not existence.`
                        : `      "${ev.text}" does not appear anywhere in the page snapshot.` +
                              (ev.near ? ` ${ev.near} line(s) mention "${ev.word}".` : ''),
                );
            }
        }
        console.log(`\n    recorded ${age(e.at)} in run ${e.runId ?? '?'} under ${e.envKey}`);
    }
    return 0;
}

/**
 * Re-derive ledger entries from a finished run's results.json without re-running
 * anything. Useful when this script's failure analysis improves, or to recover a
 * ledger from run dirs that are still on disk.
 */
function cmdReparse(argv) {
    const opts = parseArgs(argv, { flags: [], values: [] });
    const wanted = opts._[0];
    const runs = fs.existsSync(RUNS)
        ? fs
              .readdirSync(RUNS)
              .filter((n) => /^\d{8}-\d{6}$/.test(n) && fs.existsSync(path.join(RUNS, n, 'results.json')))
              .sort()
        : [];
    const ids = wanted ? runs.filter((n) => n === wanted || n.includes(wanted)) : runs.slice(-1);
    if (!ids.length) {
        console.log(`no run with results.json matches "${wanted ?? 'latest'}". Available: ${runs.join(', ') || 'none'}`);
        return 1;
    }
    const ek = envKey(resolveEnv());
    const ledger = loadLedger();
    const support = supportHash();
    for (const id of ids) {
        const json = JSON.parse(fs.readFileSync(path.join(RUNS, id, 'results.json'), 'utf8'));
        const { passed, failed } = recordResults(ledger, flattenReport(json, true), { ek, support, id });
        console.log(`run ${id}: re-recorded ${passed} passed, ${failed.length} failed (env ${ek})`);
    }
    console.log('\nnote: ledger timestamps now reflect this reparse, not the original run.');
    return 0;
}

function cmdTrace(argv) {
    const needle = argv.join(' ').toLowerCase();
    const ek = envKey(resolveEnv());
    const matches = entriesFor(loadLedger(), ek).filter(
        (e) => e.trace && (!needle || descriptor(e).toLowerCase().includes(needle)),
    );
    if (!matches.length) {
        console.log('no retained trace matches. `pw-run.mjs failed` lists what is available.');
        return 1;
    }
    for (const e of matches) {
        console.log(`${descriptor(e)}\n  ${e.trace}\n  npx playwright show-trace ${e.trace}`);
    }
    return 0;
}

function cmdForget(argv) {
    const opts = parseArgs(argv, {
        flags: ['all', 'passed', 'failed', 'stale', 'all-envs'],
        values: ['file', 'grep'],
    });
    const ledger = loadLedger();
    const ek = envKey(resolveEnv());
    let removed = 0;
    for (const [k, e] of Object.entries(ledger.entries)) {
        if (!opts['all-envs'] && e.envKey !== ek) continue;
        const hit =
            opts.all ||
            (opts.passed && e.status === 'passed') ||
            (opts.failed && e.status !== 'passed') ||
            (opts.stale && e.specHash !== specHash(e.file)) ||
            (opts.file && e.file.includes(opts.file)) ||
            (opts.grep && descriptor(e).toLowerCase().includes(opts.grep.toLowerCase()));
        if (hit) {
            delete ledger.entries[k];
            removed++;
        }
    }
    if (!removed) {
        console.log('nothing matched — pass one of --all --passed --failed --stale --file X --grep X');
        return 1;
    }
    saveLedger(ledger);
    console.log(`forgot ${removed} ledger entr${removed === 1 ? 'y' : 'ies'}.`);
    return 0;
}

function prune(keep, quiet = false, { force = false } = {}) {
    if (!fs.existsSync(RUNS)) return 0;
    const dirs = fs
        .readdirSync(RUNS, { withFileTypes: true })
        .filter((e) => e.isDirectory() && /^\d{8}-\d{6}$/.test(e.name))
        .map((e) => e.name)
        .sort();

    // Never discard the artifacts of a failure that is still open — those traces are
    // the reason the run dirs exist. --force overrides.
    const protectedRuns = new Set(
        force
            ? []
            : Object.values(loadLedger().entries)
                  .filter((e) => e.status !== 'passed' && e.runId)
                  .map((e) => e.runId),
    );

    const candidates = dirs.filter((d) => !protectedRuns.has(d));
    const drop = candidates.slice(0, Math.max(0, dirs.length - keep));
    for (const d of drop) fs.rmSync(path.join(RUNS, d), { recursive: true, force: true });

    const kept = [...protectedRuns].filter((r) => dirs.includes(r) && !drop.includes(r));
    if (!quiet) {
        if (drop.length) console.log(`pruned ${drop.length} old run dir(s), kept ${keep}.`);
        if (kept.length) {
            console.log(`kept ${kept.length} run dir(s) holding traces for open failures: ${kept.sort().join(', ')}`);
            console.log('use `prune --force --keep N` to delete those too.');
        }
    }
    return drop.length;
}

function cmdPrune(argv) {
    const opts = parseArgs(argv, { flags: ['force'], values: ['keep'] });
    const keep = Number(opts.keep ?? 3);
    if (!Number.isInteger(keep) || keep < 0) die('--keep needs a non-negative integer');
    if (!prune(keep, false, { force: !!opts.force })) console.log(`nothing to prune (keeping ${keep}).`);
    return 0;
}

// --- arg parsing / entrypoint ---------------------------------------------
function parseArgs(argv, { flags, values }) {
    const out = { _: [] };
    for (let i = 0; i < argv.length; i++) {
        const a = argv[i];
        if (a === '--') {
            out._.push(...argv.slice(i + 1));
            break;
        }
        if (a.startsWith('--')) {
            const [name, inline] = a.slice(2).split(/=(.*)/s);
            if (flags.includes(name) && inline === undefined) out[name] = true;
            else if (values.includes(name) || flags.includes(name)) out[name] = inline ?? argv[++i];
            else die(`unknown option --${name}`);
        } else if (a.startsWith('-g')) {
            out.grep = a === '-g' ? argv[++i] : a.slice(2);
        } else out._.push(a);
    }
    return out;
}

const USAGE = `pw-run — selective Playwright runs with a persistent pass ledger

  run [selectors...] [-g <grep>]   run selected tests, skipping ones already recorded as passing
      --all                        ignore the pass list, run everything selected
      --failed                     re-run only the tests recorded as failing
      --manual                     include @manual tests (excluded by default, even
                                   when you pass your own --grep-invert)
      --html                       also emit an HTML report in the run dir
      --headed | --retries N | --max-failures N | --timeout MS | --project NAME
      --dry-run                    print what would run; executes nothing, writes nothing
  status [--verbose] [--all-envs]  show the pass list, failures, stale entries
  failed [--list-file]             failures: failing step, assertion, call chain, trace
  explain [text] [--actions N]     full diagnosis: source, call log, action timeline
                                   from the trace, page state at the failure
  trace [text]                     locate retained traces for failing tests
  reparse [runId]                  re-derive ledger entries from a finished run's report
  forget --all|--passed|--failed|--stale|--file X|--grep X [--all-envs]
  prune [--keep N]                 delete old run directories

Selectors and -g are passed through to Playwright unchanged.
Artifacts: ${CONFIG.runsDir}/<runId>/   Ledger: ${CONFIG.runsDir}/ledger.json`;

async function main() {
    if (!fs.existsSync(path.join(ROOT, 'playwright.config.ts'))) {
        die(`run this from the repo root (no playwright.config.ts in ${ROOT}).`);
    }
    const [cmd, ...rest] = process.argv.slice(2);
    const dispatch = {
        run: cmdRun,
        status: cmdStatus,
        failed: cmdFailed,
        explain: cmdExplain,
        reparse: cmdReparse,
        trace: cmdTrace,
        forget: cmdForget,
        prune: cmdPrune,
    };
    if (!cmd || cmd === 'help' || cmd === '--help' || cmd === '-h') {
        console.log(USAGE);
        return 0;
    }
    if (!dispatch[cmd]) die(`unknown command "${cmd}"\n\n${USAGE}`);
    return (await dispatch[cmd](rest)) ?? 0;
}

main().then(
    (code) => process.exit(code ?? 0),
    (err) => die(err?.stack ?? String(err)),
);
