---
name: jsxm
description: Write, check and test against JSXM stream X-machine specifications (the jsxm-maven-plugin XML format) - installing JSXM, generating tests, choosing k, checking a model before generating, running the generated tests against a system in any language, and proving the tests can fail. Use when the user mentions JSXM, a stream X-machine (SXM) model, a _sets.xml state cover or characterization set, jsxm:generate, or model-based tests from an X-machine.
---

# JSXM

JSXM turns a stream X-machine written in XML (states, transitions, memory, and Java preconditions and
effects) into tests.

Everything below was checked in a working session unless marked **unverified**.

## Setup

The install guide is <http://jsxm.org/jsxm-maven-plugin/guide/installation.html>. Fetch it with `curl` if the
web tool fails; the site resets some connections.

- **Maven 3.0.5 exactly**, from `https://archive.apache.org/dist/maven/maven-3/3.0.5/binaries/`
  (`apache-maven-3.0.5-bin.tar.gz`, sha256 `d98d766be9254222920c1d541efd466ae6502b82a39166c90d65ffd7ea357dd9`).
  Unpack it to `~/apache-maven-3.0.5` and call it by full path. Leave the user's default `mvn` alone.
- **JDK 8.** Point `JAVA_HOME` at a full JDK, not a JRE folder.
- **Maven Central over https.** Maven 3.0.5 asks Central over http, which Central refuses. Pass a settings file
  with `-s`, and leave the user's `~/.m2/settings.xml` alone:
  ```xml
  <settings><mirrors>
    <mirror><id>central-https</id><mirrorOf>central</mirrorOf><url>https://repo.maven.apache.org/maven2</url></mirror>
  </mirrors></settings>
  ```
- The plugin comes from `http://www.jsxm.org/maven2/`, declared as a `pluginRepository` in the pom. Copy the pom
  of an example (Account: `http://www.jsxm.org/jsxm-maven-plugin/examples-downloads/Account.zip`). Version
  1.4.11-RC4 worked.
- Check the install: `mvn -B -s settings.xml clean jsxm:compile` on the Account example ends with BUILD SUCCESS.

## Project layout

```
pom.xml
src/spec/<package path>/<Model>/specification/<Model>.xml        the model
src/spec/<package path>/<Model>/specification/<Model>_sets.xml   state cover and characterization set
src/spec/<package path>/<Model>/tests/<Model>_test.xml           written by jsxm:generate
src/spec/<package path>/<Model>/testAdapters/<Model>Adapter.java optional, for the JUnit step
```

Several models in one project each get their own folder, and one `jsxm:generate` handles them all. Keep the
models in the user's own repo and copy them into a temporary JSXM project from a script.

## Goals

`mvn jsxm:help` lists them: animate-console, animate-gui, banimate, classpath, compile, compile-repast,
copy-external-package, copy-package, create-prototype, create-sample, generate, help, profile, validate.

- `jsxm:compile` validates the XML against the schema and compiles the model's Java. It catches Java errors in
  preconditions, effects and methods.
- `jsxm:generate` compiles, then writes `<Model>_test.xml`, then writes a JUnit class if
  `testAdapters/<Model>Adapter.java` exists. Without one it says "Implementation of <Model>Adapter required" and
  still succeeds.
- `create-prototype` and `create-sample` only make templates for a new model. They make no adapter for an
  existing one.
- `jsxm:banimate` (with `<banimateAll>true</banimateAll>`) reads `<Model>/animation/<Model>_input.xml` and
  writes `<Model>_output.xml` next to it. It gives outputs only, with no states. Input file:
  ```xml
  <sequence xmlns="http://www.jsxm.org/schema"><call><input name="create"><outcome type="xs:string">ok</outcome></input></call>...</sequence>
  ```
  A rejected input comes out as `<output name="<input>_Error"/>`.
- `jsxm:animate-console` is interactive, and reads stdin. It prints `STATE` and `MEMORY` (the `<display>`
  expression) before and after each input, then the output as `<output>_<result>_<result>`. Inputs are typed as
  `send()`, `create("ok")`, `repeat("ok","refuse","pending",false)`. Commands end with a dot: `.h.` help, `.i.`
  inputs, `.r.` reset, `.s.` less or more detail, `.log.` save. `.q.` did not quit when stdin was piped. To
  script it, pipe lines with short sleeps, since Maven takes a few seconds to start:
  `(sleep 8; printf 'send()\n'; ...) | mvn ... jsxm:animate-console`. Choose models with
  `<animateList><param>Model</param></animateList>` and `<animateAll>false</animateAll>`. Neither animator
  showed which function fired.
- `animate-gui` was not tried.

## Choosing k

k is the estimated number of extra states the code has beyond the model: k = n' − n, where n is the model's
states and n' the code's (Dranidis, Bratanis, Ipate, "JSXM: A Tool for Automated Test Generation", SEFM 2012).
The tests are `((Sr Φ[k+1]) ∩ L) Ws`: reach each state by the state cover, run every accepted sequence of up to
k+1 functions, then probe with the separating set. Sequences that are a prefix of another are dropped. The
guarantee that every fault is found holds only if the code really has at most n + k states.

The paper's advice: k is usually below 5. Larger k rarely finds new errors unless the code is very wrong. Test
count and length grow exponentially with k (the paper's account example: 143 / 841 / 5293 / 35151 tests for
k = 0..3). In the paper's web-service case studies, k ≤ 2 was enough to find real errors. Large k also makes
input generators more likely to fail on models that are not input-uniform, because the function sequences get
longer.

**Raising k does not fix memory problems.** k only lets the tests reach states that the code may have but the
model does not describe. Behaviour that depends on memory values the tests never reach stays untested at any k.
Fix that in the model instead (see "Writing a model that tests well").

The web pages do not say how to set k. The plugin descriptor (`META-INF/maven/plugin.xml` in the plugin jar) does:

- `<kInput>` in the plugin's `<configuration>` sets k for every model. The default is 2. It has no `-D` property.
- `<kList>` sets it per model: `<kList><property><name>Model</name><value>0</value></property></kList>`. The name
  must be the model's name exactly.

Size grows fast. One model with 7 states and about 40 functions gave 316 tests at k=0 and 11,239 at k=2 (5 to 6
minutes to generate). Start at k=0 when every test drives a real system.

**`jsxm:generate` does not write the tests again while `<Model>_test.xml` is there.** It reports success in
milliseconds and leaves the old file, with its old `k`. Delete the tests folder before every run.

## Reading the generate output

- **WARN "Not admitted function X ... not applicable in seq [...]"**: a sequence whose preconditions fail with the
  generators' inputs. JSXM drops it. Many of these are normal when functions depend on memory.
- **ERROR "Unhandled input: ..."**: an expected rejection. The test step expects `<input>_Error` (or the fault
  name). In one run these ERROR lines matched the `_Error` steps one for one. They are not faults in the model.
- The test XML: `<set k=".."><sequences><sequence name="F1_F2_..."><call><function name/><input name><arg
type>value</arg></input><output name><result type>value</result></output></call>...`. In that run, an
  `_Error` step came only last in its sequence.

## Writing a model that tests well

The k=0 tests are: reach each state by its state-cover sequence, take one function, then probe with the
characterization set. They reach states, not memory. In one run they caught only 1 of 5 deliberate code breaks,
because the breaks sat behind memory. After the changes below they caught all 5. Raising k would not have
helped: it adds paths through extra states in the code, not memory values the tests never reach.

- **Memory that decides the next function hides behaviour from the tests.** Make it states, or separate models.
  - A configuration flag that changes behaviour throughout (for example, "the gateway dedups") is better as
    two models than as a memory flag. Each model's state cover then runs that configuration through every
    state, and each model drops the functions it never uses. The cost: shared functions are written twice, since
    `<dependencies>` composes machines and does not share functions.
  - A remembered fact that changes a later answer (for example, "a refusal is stored") is better as states
    (`writingRefused`, `doneRefused`), so the state cover reaches it.
- **Split a function whose output depends on memory into one function per answer** (`FindsRefusal` and
  `FindsAcceptance`, not one `Finds`). The tests then cover each answer by name.
- **The generators decide what is tested.** Each function has one generator, so it gives one kind of input. A
  case only another input reaches is never tested. Give that case its own function and generator, as with a
  repeat the gateway refuses.
- **The characterization set may hold extra sequences** that tell no states apart. Use them to probe outputs that
  depend on memory, such as what the caller is told when a write fails.
- **Model the environment's choices as inputs.** For code under test that waits on a database or a remote
  service, each step's input is the result that dependency gives (`ok`, `fail`, `commitThenFail`;
  `accept`, `refuse`, `none`, `lost`). Events from outside (a retry, a callback) are self-loop "world events" in
  every state where they can happen.
- **Every pair of functions on one input from one state must have disjoint preconditions**, or the model is not
  deterministic.

## Checking a model before generating

`scripts/check_model.py <Model.xml> [--depth N] [--world F1,F2]` (needs Python 3 and a JDK). It is not JSXM. It
copies the model's Java into a class, replays every sequence up to the depth with the generators' inputs, and
prints:

- `UNREACHED`: a transition no sequence takes. Either it can never happen (remove it), or the depth is too small,
  or no generator gives an input that reaches it. Before you remove one, check by hand that it is impossible for
  any input, not just for the generators'.
- `NONDET`: two functions enabled from one state for one input.
- `MISSING`: a world event whose precondition holds in a state with no transition for it. This catches a
  transition removed by mistake.

Exit code 0 is clean, 1 means findings, and 2 means the model's Java does not compile. In a session, a
transition was removed because the generator-only replay never reached it. The tests against the real system
then failed on it. The `MISSING` check now finds that mistake.

Also check the sets by hand, or with the same replay: each state's cover sequence must reach that state, and
each pair of states must accept different characterization sequences.

## Running the generated tests against a system

- **JUnit path:** write `<Model>Adapter.java` with one method per input, taking the input's arguments and
  returning a string: the output name joined with its result values, as in `"depositOut_" + x`, or the fault
  name. Then `mvn clean jsxm:generate test`. The format was read from the Account2 example; the multi-result
  format is **unverified**.
- **Any other language:** read `<Model>_test.xml` directly and make one test per sequence. For each call, pass the
  input to an adapter and compare its output name and result values with the expected ones. A parameterised test
  over (model, sequence name) keeps each sequence a separate test case.
- **Driving the steps of running code:** put a gate before each step the model names, such as a wrapper around
  the data layer or a fake of the remote service. The gate holds the request under test until the adapter
  releases it with the input's result. Tell the request under test apart from others, for example by a request
  header read through the framework's request context. After releasing, wait until the request is held at the
  next gate or has finished. Then read the observed state for the output.
- **Rejecting inputs:** the adapter must give `<input>_Error` when the model would not accept the input. Examples:
  a stage input when the request is not held at that gate, or a callback for a payment the fake service never
  finished. Otherwise every negative step fails.
- After each test, release any request still held, so it cannot run into the next test.

## Proving the tests can fail

Passing tests do not show they would catch a fault. Break the code on purpose, one decision at a time, and run
the generated tests each time.

- Keep each break as a small patch: `git apply` it, build, run the tests, then `git apply -R`.
- Refuse to start if the file has uncommitted changes, and rebuild clean code at the end.

A break no test catches points to memory the model hides, or to a missing generator. See "Writing a model that
tests well".
