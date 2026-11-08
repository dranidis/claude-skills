#!/usr/bin/env python3
"""Checks a JSXM specification (the plain XML format) before tests are generated from it.

It copies the model's Java (memory, methods, preconditions, effects, input generators) into one Java class, then
replays every sequence of functions up to a depth, from the initial state, with the inputs the generators give.
It reports:

  UNREACHED  a transition no sequence takes. Either it cannot happen, or no generator gives an input for it.
  NONDET     two functions enabled from one state for one input. Inputs tried: every generator of that input.
  MISSING    a world event whose precondition holds in a state that has no transition for it. The model may lack
             a transition it needs. World events are the functions named with --world; without it, every output
             function that labels only self-loops. The initial state is skipped, since world events usually
             start only after the first input.

It is not JSXM: it reads the model the way JSXM's generated Java does, as far as it was checked against it.
It sees only what the generators give, so UNREACHED can mean "no generator reaches it" rather than "impossible".

Usage: check_model.py <Model.xml> [--depth N] [--world F1,F2,...]      (needs javac and java, JDK 8 or later)
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

NS = '{http://www.jsxm.org/schema}'
XSI_TYPE = '{http://www.w3.org/2001/XMLSchema-instance}type'
JAVA_TYPES = {
    'xs:int': 'int', 'xs:integer': 'int', 'xs:string': 'String', 'xs:boolean': 'boolean', 'xs:float': 'float',
    'xs:double': 'double', 'xs:char': 'char', 'xs:byte': 'byte', 'xs:long': 'long', 'xs:short': 'short',
}


def text(element):
    return (element.text or '') if element is not None else ''


def statement(code):
    # JSXM takes a memory declaration or initial value without its last semicolon, as in "int balance".
    code = code.strip()
    return code if not code or code.endswith((';', '}')) else code + ';'


def java_string(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def read_model(path):
    root = ET.parse(path).getroot()
    memory = root.find(NS + 'memory')
    functions = []
    for f in root.find(NS + 'functions'):
        functions.append({
            'name': f.get('name'),
            'input': f.get('input'),
            'output': f.get('output'),
            'pre': text(f.find(NS + 'precondition')).strip() or 'true',
            'effect': text(f.find(NS + 'effect')),
        })
    generators = {}
    tig = root.find(NS + 'testinputgeneration')
    if tig is not None:
        for g in tig:
            generators[g.get('function')] = text(g)
    return {
        'name': root.get('name'),
        'states': [s.get('name') for s in root.find(NS + 'states')],
        'initial': root.find(NS + 'initialState').get('state'),
        'transitions': [(t.get('from'), t.get('function'), t.get('to')) for t in root.find(NS + 'transitions')],
        'declaration': statement(text(memory.find(NS + 'declaration'))),
        'initial_memory': statement(text(memory.find(NS + 'initial'))),
        'imports': text(memory.find(NS + 'javaImports')),
        'methods': text(root.find(NS + 'methods')),
        'inputs': {i.get('name'): [(a.get('name'), JAVA_TYPES.get(a.get('type'), 'String')) for a in i.findall(NS + 'arg')]
                   for i in root.find(NS + 'inputs')},
        'outputs': {o.get('name'): [(r.get('name'), JAVA_TYPES.get(r.get('type'), 'String')) for r in o.findall(NS + 'result')]
                    for o in root.find(NS + 'outputs')},
        'functions': functions,
        'generators': generators,
    }


def java_source(model, depth, world):
    fs = model['functions']
    out = [model['imports'], 'import java.util.*;', 'public class ModelCheck {']
    out += [model['declaration'], 'void init() {', model['initial_memory'], '}', model['methods']]
    for name, args in model['inputs'].items():
        out.append(f'static class In_{name} {{')
        for a, t in args:
            out.append(f'  {t} {a}; {t} get_{a}() {{ return {a}; }} void set_{a}({t} v) {{ {a} = v; }}')
        out.append('}')
    for name, results in model['outputs'].items():
        out.append(f'static class Out_{name} {{ ' + ' '.join(f'{t} {r};' for r, t in results) + ' }')
    for f in fs:
        i = f['input']
        out.append(f'boolean pre_{f["name"]}(In_{i} {i}) {{ return {f["pre"]}; }}')
        if f['output']:
            o = f['output']
            out.append(f'void eff_{f["name"]}(In_{i} {i}) {{ Out_{o} {o} = new Out_{o}(); {f["effect"]} }}')
        else:
            out.append(f'void eff_{f["name"]}(In_{i} {i}) {{ {f["effect"]} }}')
        out.append(f'void gen_{f["name"]}(In_{i} {i}) {{ {model["generators"].get(f["name"], "")} }}')

    # Dispatch by name.
    out.append('Object newInput(String fn) { switch (fn) {')
    out += [f'case {java_string(f["name"])}: return new In_{f["input"]}();' for f in fs]
    out.append('} return null; }')
    for kind in ('pre', 'eff', 'gen'):
        ret = 'boolean' if kind == 'pre' else 'void'
        out.append(f'{ret} {kind}(String fn, Object in) {{ switch (fn) {{')
        for f in fs:
            call = f'{kind}_{f["name"]}((In_{f["input"]}) in)'
            out.append(f'case {java_string(f["name"])}: ' + (f'return {call};' if kind == 'pre' else f'{call}; return;'))
        out.append('}' + (' return false; }' if kind == 'pre' else ' }'))

    tr = ', '.join('{%s, %s, %s}' % tuple(java_string(x) for x in t) for t in model['transitions'])
    inputs_of = ', '.join(f'{java_string(f["name"])}, {java_string(f["input"])}' for f in fs)
    if world is None:
        has_output = {f['name'] for f in fs if f['output']}
        world = sorted({fn for _, fn, _ in model['transitions']
                        if fn in has_output and all(a == b for a, f2, b in model['transitions'] if f2 == fn)})
    out.append(f'''
static final String[][] TR = {{ {tr} }};
static final String INITIAL = {java_string(model["initial"])};
static final Map<String, String> INPUT_OF = new HashMap<>();
static {{ String[] p = {{ {inputs_of} }}; for (int i = 0; i < p.length; i += 2) INPUT_OF.put(p[i], p[i + 1]); }}
static final String[] WORLD = {{ {', '.join(java_string(w) for w in world)} }};

static String target(String state, String fn) {{
  for (String[] t : TR) if (t[0].equals(state) && t[1].equals(fn)) return t[2];
  return null;
}}

static ModelCheck replay(List<String> seq, String[] state) {{
  ModelCheck m = new ModelCheck(); m.init(); String st = INITIAL;
  for (String fn : seq) {{
    String to = target(st, fn); if (to == null) return null;
    Object in = m.newInput(fn); m.gen(fn, in);
    if (!m.pre(fn, in)) return null;
    m.eff(fn, in); st = to;
  }}
  state[0] = st; return m;
}}

public static void main(String[] args) {{
  int depth = {depth};
  Set<String> fns = new LinkedHashSet<>(); for (String[] t : TR) fns.add(t[1]);
  Set<String> covered = new HashSet<>(); Set<String> nondet = new TreeSet<>(); Set<String> missing = new TreeSet<>();
  List<List<String>> frontier = new ArrayList<>(); frontier.add(new ArrayList<>());
  for (int d = 0; d < depth; d++) {{
    List<List<String>> next = new ArrayList<>();
    for (List<String> seq : frontier) {{
      String[] st = new String[1]; ModelCheck m = replay(seq, st); if (m == null) continue;
      // NONDET: for every input, try the inputs every generator of that input gives.
      Map<String, List<String>> byInput = new HashMap<>();
      for (String f : fns) byInput.computeIfAbsent(INPUT_OF.get(f), k -> new ArrayList<>()).add(f);
      for (Map.Entry<String, List<String>> e : byInput.entrySet()) {{
        for (String g : e.getValue()) {{
          Object in = m.newInput(g); m.gen(g, in);
          List<String> enabled = new ArrayList<>();
          for (String f : e.getValue()) if (target(st[0], f) != null && m.pre(f, in)) enabled.add(f);
          if (enabled.size() > 1) nondet.add(st[0] + " input " + e.getKey() + " (from " + g + "'s generator): " + enabled + "  e.g. after " + seq);
        }}
      }}
      // MISSING: a world event enabled where the state has no transition for it.
      for (String w : WORLD) {{
        if (st[0].equals(INITIAL) || target(st[0], w) != null) continue;
        Object in = m.newInput(w); m.gen(w, in);
        if (m.pre(w, in)) missing.add(st[0] + " " + w + "  e.g. after " + seq);
      }}
      for (String fn : fns) {{
        List<String> s2 = new ArrayList<>(seq); s2.add(fn);
        String[] st2 = new String[1];
        if (replay(s2, st2) != null) {{ covered.add(st[0] + " " + fn + " " + st2[0]); next.add(s2); }}
      }}
    }}
    frontier = next;
    System.out.println("depth " + (d + 1) + ": " + frontier.size() + " sequences");
  }}
  for (String[] t : TR) if (!covered.contains(t[0] + " " + t[1] + " " + t[2])) System.out.println("UNREACHED " + t[0] + " -" + t[1] + "-> " + t[2]);
  Set<String> seen = new HashSet<>();
  for (String x : nondet) if (seen.add(x.substring(0, x.indexOf("  e.g.")))) System.out.println("NONDET " + x);
  seen.clear();
  for (String x : missing) if (seen.add(x.substring(0, x.indexOf("  e.g.")))) System.out.println("MISSING " + x);
  System.out.println("transitions reached: " + covered.size() + "/" + TR.length);
}}
}}''')
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description='Check a JSXM specification before generating tests.')
    parser.add_argument('model')
    parser.add_argument('--depth', type=int, default=6, help='longest sequence to replay (default 6)')
    parser.add_argument('--world', help='comma-separated world-event functions for the MISSING check')
    args = parser.parse_args()

    model = read_model(args.model)
    work = tempfile.mkdtemp(prefix='jsxm-check-')
    try:
        with open(os.path.join(work, 'ModelCheck.java'), 'w') as f:
            world = [w for w in args.world.split(',') if w] if args.world is not None else None
            f.write(java_source(model, args.depth, world))
        compiled = subprocess.run(['javac', '-nowarn', '-Xlint:none', 'ModelCheck.java'], cwd=work,
                                  capture_output=True, text=True)
        if compiled.returncode != 0:
            print(compiled.stderr, file=sys.stderr)
            print('The model\'s Java does not compile (see above).', file=sys.stderr)
            return 2
        run = subprocess.run(['java', '-cp', work, 'ModelCheck'], capture_output=True, text=True)
        print(run.stdout, end='')
        if run.returncode != 0:
            print(run.stderr, file=sys.stderr)
            return 2
        return 1 if any(line.startswith(('UNREACHED', 'NONDET', 'MISSING')) for line in run.stdout.splitlines()) else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
