#!/usr/bin/env python3
"""Small NxN Rubik's cube simulator for checking algorithms (tested on 3x3 and 4x4).

Notation (WCA / SiGN):
  R U F L D B        outer face, clockwise seen from that face
  R' R2 R2'          counter-clockwise, half turn
  2R                 only the 2nd layer from R (inner slice)
  Rw  (= r)          outer 2 layers together
  3Rw (= 3r)         outer 3 layers together
  M E S              3x3 (odd N) middle slices: M like L, E like D, S like F
  x y z              whole cube, like R, U, F
Parentheses and brackets are ignored.

Axes: x points to R, y to U, z to F. Coordinates run -(N-1)..(N-1) in steps of 2.

Usage:
  cube.py apply  [-n N] "ALG"        what ALG does to a solved cube
  cube.py case   [-n N] "ALG"        the state ALG solves (inverse applied to solved)
  cube.py invert "ALG"               print the inverse
  cube.py order  [-n N] "ALG"        how many repeats until solved
  cube.py same   [-n N] "A" "B"      do A and B have the same visible effect?
"""
import argparse
import itertools
import re
import sys

FACES = "UDFBRL"
# face -> (axis index, side sign)
FACE_AXIS = {"R": (0, 1), "L": (0, -1), "U": (1, 1), "D": (1, -1), "F": (2, 1), "B": (2, -1)}
NORMAL_FACE = {(1, 0, 0): "R", (-1, 0, 0): "L", (0, 1, 0): "U", (0, -1, 0): "D", (0, 0, 1): "F", (0, 0, -1): "B"}
FACE_NORMAL = {f: n for n, f in NORMAL_FACE.items()}

TOKEN = re.compile(r"^(\d*)([URFDLBurfdlbMESxyz])(w?)(\d*)('?)(\d*)$")


def rot_cw(v, axis):
    """Rotate vector 90 degrees clockwise, looking from the positive end of axis."""
    x, y, z = v
    if axis == 0:
        return (x, z, -y)
    if axis == 1:
        return (-z, y, x)
    return (y, -x, z)


def rot(v, axis, q):
    for _ in range(q % 4):
        v = rot_cw(v, axis)
    return v


def parse(alg):
    """Split an algorithm into move tokens."""
    alg = re.sub(r"[()\[\]]", " ", alg)
    return [t for t in alg.split() if t]


def invert(alg):
    out = []
    for t in reversed(parse(alg)):
        m = TOKEN.match(t)
        if not m:
            raise ValueError(f"bad move: {t}")
        pre, letter, w, amt, prime, amt2 = m.groups()
        amt = amt or amt2
        if amt == "2":
            out.append(f"{pre}{letter}{w}2")
        else:
            out.append(f"{pre}{letter}{w}{amt}{'' if prime else chr(39)}")
    return " ".join(out)


class Cube:
    def __init__(self, n=3):
        self.n = n
        m = n - 1
        coords = range(-m, m + 1, 2)
        self.home = []  # sticker id -> (pos, normal) when solved
        for p in itertools.product(coords, repeat=3):
            for a in range(3):
                if abs(p[a]) == m:
                    nrm = [0, 0, 0]
                    nrm[a] = 1 if p[a] > 0 else -1
                    self.home.append((p, tuple(nrm)))
        self.cur = list(self.home)

    # ---- moves ----
    def _layers(self, depths, side):
        m = self.n - 1
        return {side * (m - 2 * (d - 1)) for d in depths}

    def move(self, token):
        m = TOKEN.match(token)
        if not m:
            raise ValueError(f"bad move: {token}")
        pre, letter, w, amt, prime, amt2 = m.groups()
        amt = int(amt or amt2 or 1)
        n = self.n
        if letter in "xyz":
            axis = "xyz".index(letter)
            coords = None
            q = 1
        elif letter in "MES":
            if n % 2 == 0:
                raise ValueError(f"{letter} needs an odd cube; use 2R/2L etc on {n}x{n}")
            face = {"M": "L", "E": "D", "S": "F"}[letter]
            axis, side = FACE_AXIS[face]
            coords = {0}
            q = 1 if side > 0 else -1
        else:
            face = letter.upper()
            axis, side = FACE_AXIS[face]
            k = int(pre) if pre else None
            if letter.islower() or w:
                depths = range(1, (k or 2) + 1)
            else:
                depths = [k or 1]
            if max(depths) > n:
                raise ValueError(f"{token}: cube has only {n} layers")
            coords = self._layers(depths, side)
            q = 1 if side > 0 else -1
        q *= -amt if prime else amt
        self.cur = [
            (rot(p, axis, q), rot(nm, axis, q)) if coords is None or p[axis] in coords else (p, nm)
            for p, nm in self.cur
        ]
        return self

    def apply(self, alg):
        for t in parse(alg):
            self.move(t)
        return self

    # ---- inspection ----
    def _rotations(self):
        """All 24 whole-cube rotations as functions on vectors."""
        seen, out = set(), []
        for a, b, c in itertools.product(range(4), repeat=3):
            def f(v, a=a, b=b, c=c):
                return rot(rot(rot(v, 0, a), 1, b), 2, c)
            key = (f((1, 0, 0)), f((0, 1, 0)))
            if key not in seen:
                seen.add(key)
                out.append(f)
        return out

    def normalized(self):
        """Current (pos, normal) list after the whole-cube rotation that looks most solved."""
        best = None
        for f in self._rotations():
            st = [(f(p), f(nm)) for p, nm in self.cur]
            wrong = sum(1 for (hp, hn), (p, nm) in zip(self.home, st) if hn != nm)
            if best is None or wrong < best[0]:
                best = (wrong, st)
        return best[1]

    def wrong_stickers(self):
        st = self.normalized()
        return sum(1 for (hp, hn), (p, nm) in zip(self.home, st) if hn != nm)

    def is_solved(self):
        return self.wrong_stickers() == 0

    def piece_name(self, p):
        m = self.n - 1
        parts = []
        for a, (pos_f, neg_f) in ((1, ("U", "D")), (2, ("F", "B")), (0, ("R", "L"))):
            if p[a] == m:
                parts.append(pos_f)
            elif p[a] == -m:
                parts.append(neg_f)
        name = "".join(parts)
        if self.n <= 3 or len(parts) == 3:
            return name
        # 4x4+: wings and centers need a position tag, e.g. UF[R] = UF wing on the R side
        tag = []
        for a, (pos_f, neg_f) in ((1, ("U", "D")), (2, ("F", "B")), (0, ("R", "L"))):
            c = p[a]
            if abs(c) != m and c != 0:
                depth = f"{(m - abs(c)) // 2 + 1}" if self.n > 4 else ""
                tag.append((pos_f if c > 0 else neg_f) + depth)
        return f"{name}[{''.join(tag)}]" if tag else name

    def changes(self):
        """Visibly changed pieces: list of (piece_home_name, now_at_name, in_place)."""
        st = self.normalized()
        pieces = {}
        for i, (hp, hn) in enumerate(self.home):
            pieces.setdefault(hp, []).append(i)
        out = []
        for hp, ids in pieces.items():
            if any(self.home[i][1] != st[i][1] for i in ids):
                np_ = st[ids[0]][0]
                out.append((self.piece_name(hp), self.piece_name(np_), np_ == hp))
        return sorted(out)

    def facelets(self):
        """Dict face -> NxN grid of colour letters (normalized orientation)."""
        n, m = self.n, self.n - 1
        idx = lambda c: (c + m) // 2
        grid = {f: [["?"] * n for _ in range(n)] for f in FACES}
        for (hp, hn), (p, nm) in zip(self.home, self.normalized()):
            f = NORMAL_FACE[nm]
            x, y, z = p
            if f == "U":
                r, c = idx(z), idx(x)
            elif f == "D":
                r, c = idx(-z), idx(x)
            elif f == "F":
                r, c = idx(-y), idx(x)
            elif f == "B":
                r, c = idx(-y), idx(-x)
            elif f == "R":
                r, c = idx(-y), idx(-z)
            else:
                r, c = idx(-y), idx(z)
            grid[f][r][c] = NORMAL_FACE[hn]
        return grid

    def net(self):
        g, n = self.facelets(), self.n
        pad = " " * (n + 1)
        lines = [pad + "".join(row) for row in g["U"]]
        for r in range(n):
            lines.append(" ".join("".join(g[f][r]) for f in "LFRB"))
        lines += [pad + "".join(row) for row in g["D"]]
        return "\n".join(lines)

    def colors(self):
        """Dict (pos, normal) -> colour letter, normalized orientation."""
        return {(p, nm): NORMAL_FACE[hn] for (hp, hn), (p, nm) in zip(self.home, self.normalized())}

    def unpaired_edges(self):
        """Edge slots (e.g. 'FR') whose pieces do not look like one 3x3 edge. Empty on a 3x3."""
        m = self.n - 1
        col = self.colors()
        slots = {}
        for (p, nm) in col:
            ext = [a for a in range(3) if abs(p[a]) == m]
            if len(ext) == 2:
                key = tuple(p[a] if a in ext else None for a in range(3))
                slots.setdefault(key, set()).add(p)
        out = []
        for key, positions in slots.items():
            looks = set()
            for p in positions:
                ext = [a for a in range(3) if key[a] is not None]
                looks.add(tuple(col[(p, tuple((1 if key[a] > 0 else -1) if a == e else 0 for a in range(3)))] for e in ext))
            if len(looks) > 1:
                out.append(self.piece_name(tuple(0 if k is None else k for k in key)).split("[")[0])
        return sorted(out)

    def centers_solved(self):
        m = self.n - 1
        return all(NORMAL_FACE[nm] == c for (p, nm), c in self.colors().items()
                   if sum(abs(v) == m for v in p) == 1)

    def report(self):
        ch = self.changes()
        lines = [self.net(), "", f"wrong stickers: {self.wrong_stickers()}"]
        if self.n > 3:
            lines.append(f"centers solved: {'yes' if self.centers_solved() else 'no'}")
            lines.append(f"unpaired edges: {', '.join(self.unpaired_edges()) or 'none'}")
        if not ch:
            lines.append("solved (up to whole-cube rotation)")
        for home, now, in_place in ch:
            lines.append(f"  {home}: {'turned in place' if in_place else 'now at ' + now}")
        return "\n".join(lines)


def order(n, alg, limit=5000):
    c = Cube(n)
    for i in range(1, limit + 1):
        c.apply(alg)
        if c.is_solved():
            return i
    return None


def same_effect(n, a, b):
    return Cube(n).apply(a).apply(invert(b)).is_solved()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["apply", "case", "invert", "order", "same"])
    ap.add_argument("alg", nargs="+")
    ap.add_argument("-n", type=int, default=3)
    a = ap.parse_args(argv)
    alg = a.alg[0]
    try:
        if a.cmd == "apply":
            print(Cube(a.n).apply(alg).report())
        elif a.cmd == "case":
            print(Cube(a.n).apply(invert(alg)).report())
        elif a.cmd == "invert":
            print(invert(alg))
        elif a.cmd == "order":
            print(order(a.n, alg))
        elif a.cmd == "same":
            if len(a.alg) != 2:
                ap.error("same needs two algorithms")
            print("same" if same_effect(a.n, a.alg[0], a.alg[1]) else "different")
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
