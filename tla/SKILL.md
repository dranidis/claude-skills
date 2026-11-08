---
name: tla
description: Write, check and use TLA+ specs with TLC - running SANY and TLC from the command line, configs and model sizes, writing properties that find real bugs, modelling outside parties such as gateways, turning a TLC counterexample into a failing test and a fix, and checking recorded test traces against a spec. Use when the user mentions TLA+, TLC, SANY, a .tla or .cfg file, a model checking counterexample, an invariant or liveness property, or trace checking.
---

# TLA+

Everything below was checked in a working session unless marked **unverified**. A repo's own formal-spec
docs win over this file.

## Running

- `tla2tools.jar` needs Java 11 or later. The VS Code TLA+ extension ships one under
  `~/.vscode/extensions/tlaplus.vscode-ide-*/out/tools/tla2tools.jar`. Use that before downloading one.
- Parse only: `java -cp tla2tools.jar tla2sany.SANY Spec.tla`.
- Check: `java -XX:+UseParallelGC -cp tla2tools.jar tlc2.TLC -workers auto -metadir <scratch>/tlc -config X.cfg Spec.tla`.
  Put `-metadir` in a scratch folder so the states folder stays out of the repo.
- With `-workers 1`, a config that breaks two properties always reports the same one. Scripts that compare
  results with an expected result should use one worker.
- On a failure TLC writes trace files beside the spec. Keep them out of git.

## Configs and sizes

- **One config is one set of facts about the world**, such as "the gateway dedups" or "repeating is safe".
  Write the expected result in its first line: `Expected: pass.` or `Expected: <Property> fails.`.
- **Keep a config that is meant to fail.** If it starts to pass, the spec has become too weak. A trace check
  cannot catch that.
- TLC cannot be told to expect a liveness failure by name. It does not say which temporal property failed.
- **Have a fast size and a deep size.** Run the fast size on every change. Run the deep size before changing
  actions. For the deep size, copy the spec and configs to a scratch folder and raise the limit there.
- Liveness checks are much slower than safety checks. When reporting a pass, say which properties ran at which
  size, and that a pass at small sizes is not a proof.

## Modelling

- **Keep each outside party in its own section and its own action**, such as a Gateway's answer, apart from
  the call your system makes. The system's action then shows only what the system decides and what the
  network does, for example `GatewayAnswers(resp) /\ (Got(resp) \/ Got(Lost))`.
- **A history variable can stand for an outside party's memory.** For example, the first answer a Gateway gave
  for an id is enough to model its duplicate check.
- **A write that can fail:** list the success and failure branches with `\/`, each with its own `UNCHANGED`.
  This is easier to read and review than `\E ok \in BOOLEAN`.
- **One database statement is one atomic step.** A decision in code is taken on the row as the request read
  it, which may be out of date. Model that read as its own step when a race matters.
- **Use `LET` names** for parts of an action used more than once, such as `WriteRow` or `Respond`.

## Properties

- **Properties come from intent: ADRs, docs, and the human. Never from the code.** A property read off the
  code holds by construction. The human approves each new property.
- **The properties that find bugs link what a caller was told to what is true somewhere else.** Examples:
  "told refused => the row stores refused", "told refused => the gateway refused", "told accepted => the
  gateway has a money transfer". A property about one variable alone rarely finds anything.
- **"Never both answers" needs a temporal formula:** `[](toldA => [](~toldB))`. Add the mirror conjunct too.
  An invariant cannot say it, because the two answers happen in different states.
- **Bound side effects with exact counts**, for example `Len(transfers) <= 1`, not just "is paid".
- **"Once set, never changes"** as an action property: `[][x # "none" => UNCHANGED x]_vars`. `UNCHANGED rec.field`
  works.
- **Leads-to for progress**: `paid ~> settled`. It needs fairness on the steps that make progress.
- **Never weaken or remove a property to make TLC pass.** Report the counterexample.

## From counterexample to fix

1. Read the TLC trace and name, in plain words, what happened at each step.
2. Find the code line behind each step. Check the paths in the code before calling it a bug.
3. Check the ADRs and the code comments. The behaviour may be a recorded decision. If the property shows that
   the decision breaks something the ADR did not consider, say so and ask before going against it.
4. Write a test that forces that interleaving and fails. Show that it fails.
5. Fix the code. Update the spec action, the ADR and the docs in the same commit.
6. Run everything again: parse, every config at the fast size, the deep size, and the traces.

To get a test case on purpose, add a scratch invariant saying "this state is never reached". TLC prints the
shortest trace to it. Keep that invariant in a scratch config, never in the spec.

## Trace checking

- A test records its run, and a trace spec checks that the run is a behaviour the spec allows.
- An accepted trace only covers what the tests did. A spec that allows everything accepts every trace.
- On a rejected trace there are three possible causes: the code is wrong, the spec is too strict, or the test
  does something that cannot happen. Show the first state that did not match, and let the human decide.

## Gotchas

- `[][x \in {...} => ...]_vars` failed to parse. Wrapping both sides of `=>` in parentheses fixed it.
- Editors on some setups save `.tla` files with CRLF, so git shows the whole file as changed. Run
  `sed -i 's/\r$//'` before committing, and tell the user.
