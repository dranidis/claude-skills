#!/usr/bin/env python3
"""Build a local HTML page with animated cube players (cubing.js), and serve it on localhost.

Pages are local files only. Never publish them as an artifact.

Build:
  player.py build --title "Flip one edge on a 4x4" \\
    --player "Pure version|4x4|2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2|end|Changes only the UF edge." \\
    [--intro "..."] [--eyebrow "OLL parity"] [--out DIR]

  --player "TITLE|CUBE|MOVES|START|NOTE"  (repeatable)
     CUBE   3x3, 4x4 or 5x5
     START  end   = start from the case the moves solve, finish solved (default)
            start = start from a solved cube
     NOTE   optional text under the player

Serve (blocks; run it in the background):
  player.py serve [--out DIR] [--port 8765]

Default DIR: $XDG_CACHE_HOME/rubiks-cube/players (usually ~/.cache/rubiks-cube/players).
"""
import argparse
import functools
import html
import http.server
import os
import re
import socketserver
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "player_template.html")
PUZZLES = {"3x3": "3x3x3", "3x3x3": "3x3x3", "3": "3x3x3", "4x4": "4x4x4", "4x4x4": "4x4x4", "4": "4x4x4",
           "5x5": "5x5x5", "5x5x5": "5x5x5", "5": "5x5x5"}
ANCHORS = ("end", "start")


def default_out_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "rubiks-cube", "players")


def parse_player(spec):
    parts = [p.strip() for p in spec.split("|")]
    if len(parts) < 3 or len(parts) > 5:
        raise ValueError(f"player needs 'TITLE|CUBE|MOVES[|START[|NOTE]]', got: {spec!r}")
    title, cube, alg = parts[:3]
    anchor = parts[3] if len(parts) > 3 and parts[3] else "end"
    note = parts[4] if len(parts) > 4 else ""
    if cube.lower() not in PUZZLES:
        raise ValueError(f"cube must be 3x3, 4x4 or 5x5, got: {cube!r}")
    if anchor not in ANCHORS:
        raise ValueError(f"START must be 'end' or 'start', got: {anchor!r}")
    if not alg:
        raise ValueError("MOVES is empty")
    return {"title": title, "puzzle": PUZZLES[cube.lower()], "alg": " ".join(alg.split()),
            "anchor": anchor, "note": note}


def player_html(i, p):
    e = functools.partial(html.escape, quote=True)
    pid = f"p{i}"
    start = "starts from the case" if p["anchor"] == "end" else "starts solved"
    note = f'\n      <p>{e(p["note"])}</p>' if p["note"] else ""
    return f'''    <section class="card">
      <span class="tag">{e(p["puzzle"].split("x")[0])}x{e(p["puzzle"].split("x")[0])} · {start}</span>
      <h2>{e(p["title"])}</h2>
      <twisty-player id="{pid}"
        puzzle="{e(p["puzzle"])}"
        alg="{e(p["alg"])}"
        experimental-setup-anchor="{e(p["anchor"])}"
        background="none"
        control-panel="bottom-row"
        tempo-scale="1.2"></twisty-player>
      <twisty-alg-viewer for="{pid}"></twisty-alg-viewer>{note}
    </section>'''


def render(title, players, intro="", eyebrow=""):
    if not players:
        raise ValueError("need at least one player")
    e = functools.partial(html.escape, quote=True)
    first = players[0]
    with open(TEMPLATE, encoding="utf-8") as f:
        page = f.read()
    values = {
        "TITLE": e(title),
        "EYEBROW": e(eyebrow or "Rubik's cube"),
        "INTRO": e(intro or "Press play, or step one move at a time."),
        "PLAYERS": "\n\n".join(player_html(i, p) for i, p in enumerate(players, 1)),
        "TRY_ALG": e(first["alg"]),
        "TRY_PUZZLE": e(first["puzzle"]),
        "SEL5": " selected" if first["puzzle"] == "5x5x5" else "",
        "SEL4": " selected" if first["puzzle"] == "4x4x4" else "",
        "SEL3": " selected" if first["puzzle"] == "3x3x3" else "",
    }
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], page)


def slug(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "cube"


def build(title, player_specs, out_dir=None, intro="", eyebrow=""):
    out_dir = out_dir or default_out_dir()
    players = [parse_player(s) for s in player_specs]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, slug(title) + ".html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(title, players, intro, eyebrow))
    return path


def serve(out_dir=None, port=8765, tries=20):
    out_dir = out_dir or default_out_dir()
    os.makedirs(out_dir, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=out_dir)
    for p in range(port, port + tries):
        try:
            httpd = socketserver.TCPServer(("127.0.0.1", p), handler)
            break
        except OSError:
            continue
    else:
        raise OSError(f"no free port in {port}..{port + tries - 1}")
    pages = sorted(f for f in os.listdir(out_dir) if f.endswith(".html"))
    print(f"serving {out_dir}")
    for f in pages:
        print(f"  http://127.0.0.1:{p}/{f}")
    sys.stdout.flush()
    with httpd:
        httpd.serve_forever()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--title", required=True)
    b.add_argument("--player", action="append", required=True)
    b.add_argument("--intro", default="")
    b.add_argument("--eyebrow", default="")
    b.add_argument("--out")
    s = sub.add_parser("serve")
    s.add_argument("--out")
    s.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "build":
            path = build(a.title, a.player, a.out, a.intro, a.eyebrow)
            print(path)
        else:
            serve(a.out, a.port)
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
