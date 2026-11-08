"""Tests for cube.py and for every algorithm listed in the reference files.

Run: python3 -m unittest discover -s scripts   (from the skill folder)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from cube import Cube, invert, order, same_effect  # noqa: E402


def effect(n, alg):
    """Set of (piece, now_at) for visibly changed pieces; now_at == piece means turned in place."""
    return {(home, now) for home, now, _ in Cube(n).apply(alg).changes()}


def case(n, alg):
    """Cube in the state that alg solves."""
    return Cube(n).apply(invert(alg))


def top_pattern(c):
    """U face as a string of 1 (U colour on top) / 0, row by row."""
    return "".join("1" if s == "U" else "0" for row in c.facelets()["U"] for s in row)


def swaps(*pairs):
    out = set()
    for a, b in pairs:
        out |= {(a, b), (b, a)}
    return out


def cycle(*pieces):
    """cycle(A, B, C): A goes to B, B to C, C to A."""
    return {(pieces[i], pieces[(i + 1) % len(pieces)]) for i in range(len(pieces))}


def flipped(*pieces):
    return {(p, p) for p in pieces}


class Conventions(unittest.TestCase):
    """Checks that do not depend on remembered algorithms."""

    def test_face_move_directions(self):
        # R moves F stickers to U, U moves F to L, F moves U to R
        self.assertEqual(Cube(3).move("R").facelets()["U"][2][2], "F")
        self.assertEqual(Cube(3).move("U").facelets()["L"][0][1], "F")
        self.assertEqual(Cube(3).move("F").facelets()["R"][1][0], "U")
        # L moves U to F, D moves F to R, B moves U to L
        self.assertEqual(Cube(3).move("L").facelets()["F"][1][0], "U")
        self.assertEqual(Cube(3).move("D").facelets()["R"][2][1], "F")
        self.assertEqual(Cube(3).move("B").facelets()["L"][1][0], "U")

    def test_fourth_power_is_identity(self):
        for n in (3, 4):
            for m in "URFDLB":
                for form in (m, "2" + m, m + "w"):
                    c = Cube(n).apply(" ".join([form] * 4))
                    self.assertEqual(c.cur, c.home, f"{form} x4 on {n}x{n}")

    def test_known_orders(self):
        self.assertEqual(order(3, "R U"), 105)
        self.assertEqual(order(3, "R U R' U'"), 6)
        self.assertEqual(order(3, "R U R' U R U2 R'"), 6)

    def test_rotation_equivalences_3x3(self):
        self.assertTrue(same_effect(3, "x", "R M' L'"))
        self.assertTrue(same_effect(3, "y", "U E' D'"))
        self.assertTrue(same_effect(3, "z", "F S B'"))
        c = Cube(3).apply("x")
        self.assertEqual(c.cur, Cube(3).apply("R M' L'").cur)

    def test_wide_moves_4x4(self):
        for f in "URFDLB":
            self.assertEqual(Cube(4).apply(f + "w").cur, Cube(4).apply(f"{f} 2{f}").cur)
            self.assertEqual(Cube(4).apply(f.lower()).cur, Cube(4).apply(f + "w").cur)
        self.assertEqual(Cube(4).apply("x").cur, Cube(4).apply("Rw Lw'").cur)
        self.assertEqual(Cube(4).apply("3Rw").cur, Cube(4).apply("R 2R 3R").cur)

    def test_invert(self):
        alg = "R U2 R' 2R' Uw2 F'"
        self.assertEqual(invert(alg), "F Uw2 2R R U2 R'")
        self.assertTrue(Cube(4).apply(alg).apply(invert(alg)).is_solved())

    def test_rotation_is_ignored(self):
        self.assertTrue(Cube(3).apply("x y2 z'").is_solved())
        self.assertTrue(Cube(4).apply("x y").is_solved())

    def test_slice_moves_rejected_on_even_cube(self):
        with self.assertRaises(ValueError):
            Cube(4).apply("M")


class ThreeByThree(unittest.TestCase):
    def check(self, alg, expected):
        self.assertEqual(effect(3, alg), expected, alg)

    # --- PLL ---
    def test_t_perm(self):
        self.check("R U R' U' R' F R2 U' R' U' R U R' F'", swaps(("UL", "UR"), ("UFR", "UBR")))

    def test_t_perm_hold_headlights_left(self):
        left = case(3, "R U R' U' R' F R2 U' R' U' R U R' F'").facelets()["L"][0]
        self.assertEqual(left[0], left[2])

    def test_y_perm(self):
        self.check("F R U' R' U' R U R' F' R U R' U' R' F R F'", swaps(("UL", "UB"), ("UFR", "UBL")))

    def test_ua_perm(self):
        self.check("R U' R U R U R U' R' U' R2", cycle("UF", "UR", "UL"))

    def test_ub_perm(self):
        self.check("R2 U R U R' U' R' U' R' U R'", cycle("UF", "UL", "UR"))

    def test_h_perm(self):
        self.check("M2 U M2 U2 M2 U M2", swaps(("UF", "UB"), ("UL", "UR")))

    def test_z_perm(self):
        self.check("M' U M2 U M2 U M' U2 M2 U'", swaps(("UF", "UL"), ("UB", "UR")))

    def test_aa_perm(self):
        self.check("x R' U R' D2 R U' R' D2 R2 x'", cycle("UBL", "UBR", "UFR"))

    def test_ab_perm(self):
        self.check("x R2 D2 R U R' D2 R U' R x'", cycle("UBL", "UFR", "UBR"))

    def test_beginner_corner_cycle_keeps_ufr(self):
        e = effect(3, "U R U' L' U R' U' L")
        self.assertEqual(e, cycle("UBL", "UFL", "UBR"))

    # --- orientation ---
    def test_two_edge_flip(self):
        self.check("M' U M' U M' U2 M U M U M U2", flipped("UF", "UB"))

    def test_corner_twist_repeat(self):
        # R' D' R D twists UFR; repeated 2 or 4 times it only messes the D layer (fixed by more reps)
        self.assertTrue(Cube(3).apply(" ".join(["R' D' R D"] * 6)).is_solved())
        e = effect(3, "R' D' R D R' D' R D")
        self.assertIn(("UFR", "UFR"), e)
        self.assertTrue(all(p == "UFR" or p.startswith("D") or p == "FR" for p, _ in e))

    def test_oll_cases(self):
        # U-face pattern of the case each alg solves: 1 = U colour on top, rows back->front, cols left->right
        cases = {
            "R U R' U R U2 R'": "010111110",             # Sune: oriented corner front-left
            "R U2 R' U' R U' R'": "011111010",           # Antisune: oriented corner back-right
            "R U R' U R U' R' U R U2 R'": "010111010",   # H: cross, no corners
            "R U2 R2 U' R2 U' R2 U2 R": "010111010",     # Pi: cross, no corners
            "R2 D R' U2 R D' R' U2 R'": "111111010",     # Headlights: back corners oriented
            "Rw U R' U' Rw' F R F'": "011111011",        # T / chameleon: right corners oriented
            "F' Rw U R' U' Rw' F R": "011111110",        # Bowtie: diagonal corners oriented
        }
        for alg, pattern in cases.items():
            self.assertEqual(top_pattern(case(3, alg)), pattern, alg)

    def test_h_and_pi_holds(self):
        # top row of each side face in the case: where the U-colour stickers point
        side = lambda alg, f: "".join(case(3, alg).facelets()[f][0])
        h = "R U R' U R U' R' U R U2 R'"
        self.assertEqual((side(h, "L")[0], side(h, "L")[2], side(h, "R")[0], side(h, "R")[2]), ("U",) * 4)
        pi = "R U2 R2 U' R2 U' R2 U2 R"
        self.assertEqual((side(pi, "L")[0], side(pi, "L")[2]), ("U", "U"))
        self.assertNotIn("U", side(pi, "R"))

    def test_edge_orientation_line_and_l(self):
        edges = lambda alg: "".join(top_pattern(case(3, alg))[i] for i in (1, 3, 5, 7))  # UB UL UR UF
        self.assertEqual(edges("F R U R' U' F'"), "0110")      # horizontal line
        self.assertEqual(edges("F U R U' R' F'"), "1100")      # L at back-left
        self.assertEqual(edges("Fw R U R' U' Fw'"), "0011")    # L at front-right

    def test_dot_needs_both(self):
        t = top_pattern(case(3, "F R U R' U' F' Fw R U R' U' Fw'"))
        self.assertEqual((t[1], t[3], t[5], t[7]), ("0", "0", "0", "0"))

    # --- F2L / beginner inserts ---
    def test_edge_insert_right(self):
        e = effect(3, "U R U' R' U' F' U F")
        self.assertIn(("UF", "FR"), e)
        self.assertTrue(all(p.startswith("U") or p == "FR" for p, _ in e))

    def test_edge_insert_left(self):
        e = effect(3, "U' L' U L U F U' F'")
        self.assertIn(("UF", "FL"), e)
        self.assertTrue(all(p.startswith("U") or p == "FL" for p, _ in e))


class MyMethod(unittest.TestCase):
    """Algs in references/my-method.md. Commutators written out: [A, B] = A B A' B', [S: M] = S M S'."""

    def check(self, alg, expected):
        self.assertEqual(effect(3, alg), expected, alg)

    # --- step 3: edges through the working slot (FR) ---
    def test_edge_orientation_example(self):
        # from the page's example state, F' U' F then U' U R U' R' solves the cube
        self.assertTrue(Cube(3).apply("R U R' F' U F" + " F' U' F" + " U' U R U' R'").is_solved())

    def test_all_three_edges_match_keeps_edges(self):
        # swaps the slot edge with UF (R version) or UR (F' version); other edges stay, only corners also move
        for alg, top in (("R U R' U R U R' U2", "UF"), ("F' U' F U' F' U' F U2", "UR")):
            edges = {(p, q) for p, q in effect(3, alg) if len(p) == 2}
            self.assertEqual(edges, swaps(("FR", top)), alg)

    def test_two_edges_match(self):
        self.assertTrue(Cube(3).apply("R U R' U' U R U' R'").is_solved())

    # --- step 4: corner commutators ---
    def test_corner_commutators(self):
        self.check("L D' L' U L D L' U'", cycle("DFR", "UFL", "UFR"))       # [L D' L', U]
        self.check("L D2 L' U' L D2 L' U", cycle("DBR", "UFL", "UBL"))      # [L D2 L', U']
        self.check("R' D R U' R' D' R U", cycle("DFL", "UFR", "UFL"))       # [R' D R, U']
        self.check("R' D2 R U2 R' D2 R U2", cycle("DBL", "UFR", "UBL"))     # [R' D2 R, U2]
        self.check("L D L' U L D' L' U'", cycle("DFL", "UFL", "UFR"))       # [L D L', U]

    def test_r_side_conjugate_same_as_l_d_l(self):
        self.assertTrue(same_effect(3, "U' R' D R U R' D' R U' U", "L D L' U L D' L' U'"))

    def test_b_move_choice(self):
        # where the UFL corner goes with [L D' L', B], and the UFR corner with [R' D R, B]
        where = lambda alg, p: dict(effect(3, alg))[p]
        self.assertEqual(where("L D' L' U L D L' U'", "UFL"), "UFR")
        self.assertEqual(where("L D' L' U' L D L' U", "UFL"), "UBL")
        self.assertEqual(where("L D' L' U2 L D L' U2", "UFL"), "UBR")
        self.assertEqual(where("R' D R U' R' D' R U", "UFR"), "UFL")
        self.assertEqual(where("R' D R U R' D' R U'", "UFR"), "UBR")
        self.assertEqual(where("R' D R U2 R' D' R U2", "UFR"), "UBL")

    def test_setup_cases(self):
        self.check("F U' L D' L' U' L D L' U U F'", cycle("UFR", "UBL", "UBR"))              # [F U': [L D' L', U']]
        self.check("R' L D2 L' U' L D2 L' U R", cycle("DFR", "UFL", "UBL"))                  # [R': [L D2 L', U']]
        self.check("L' F L D2 L D' L' U2 L D L' U2 D2 L' F' L", cycle("DFR", "UFL", "UBR"))  # [L' F L D2: [L D' L', U2]]
        self.check("F' U' R' D2 R U2 R' D2 R U2 U F", cycle("DBL", "UFR", "UBR"))            # [F' U': [R' D2 R, U2]]
        self.check("F U2 L D' L' U L D L' U' U2 F'", cycle("UFR", "UBR", "UBL"))             # F U2 [L D' L', U] U2 F'


class FourByFour(unittest.TestCase):
    def test_oll_parity_pure(self):
        alg = "2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2"
        c = Cube(4).apply(alg)
        self.assertEqual(c.wrong_stickers(), 4)
        self.assertEqual(effect(4, alg), swaps(("UF[L]", "UF[R]")))
        self.assertEqual(order(4, alg), 2)

    def test_oll_parity_pure_lucas(self):
        alg = "2R' U2 2L F2 2L' F2 2R2 U2 2R U2 2R' U2 F2 2R2 F2"
        self.assertEqual(Cube(4).apply(alg).wrong_stickers(), 4)
        self.assertEqual(effect(4, alg), swaps(("UF[L]", "UF[R]")))

    def test_oll_parity_speed_alg_changes_last_layer(self):
        alg = "Rw U2 x Rw U2 Rw U2 Rw' U2 Lw U2 Rw' U2 Rw U2 Rw' U2 Rw'"
        c = Cube(4).apply(alg)
        self.assertTrue(c.centers_solved())
        self.assertEqual(c.unpaired_edges(), [])
        # flips UF, but also swaps UFL/UFR corners and UL/UR edges: only fine before OLL/PLL
        self.assertEqual(effect(4, alg), swaps(("UF[L]", "UF[R]"), ("UFL", "UFR"),
                                               ("UL[B]", "UR[F]"), ("UL[F]", "UR[B]")))
        self.assertTrue(all(p.startswith("U") for p, _ in effect(4, alg)))

    def test_lowercase_is_wide_not_slice(self):
        # the pure parity alg read with wide moves is NOT pure
        self.assertNotEqual(Cube(4).apply("r2 B2 U2 l U2 r' U2 r U2 F2 r F2 l' B2 r2").wrong_stickers(), 4)

    def test_pll_parity_opposite_edges(self):
        alg = "2R2 U2 2R2 Uw2 2R2 2U2"
        self.assertEqual(effect(4, alg), swaps(("UF[L]", "UB[R]"), ("UF[R]", "UB[L]")))
        self.assertTrue(Cube(4).apply(alg).centers_solved())

    def test_pll_parity_with_uw2_needs_u2(self):
        self.assertTrue(same_effect(4, "2R2 U2 2R2 Uw2 2R2 Uw2 U2", "2R2 U2 2R2 Uw2 2R2 2U2"))

    def strangers(self, c):
        """Wings in the FL/FR slots that belong to the other slot, e.g. ['FL[U]', 'FR[D]']."""
        col, out = c.colors(), []
        for x, slot, other in ((-3, "FL", "R"), (3, "FR", "L")):
            side = (1 if x > 0 else -1, 0, 0)
            for y, h in ((1, "U"), (-1, "D")):
                p = (x, y, 3)
                if other in (col[(p, side)], col[(p, (0, 0, 1))]):
                    out.append(f"{slot}[{h}]")
        return out

    def test_edge_pairing_last_two(self):
        a = "Uw' R U R' F R' F' R Uw"   # slice-flip-slice
        b = "Dw R F' U R' F Dw'"
        flip = "R U R' F R' F' R"         # flips the FR edge, keeps centers
        setups = {  # alg -> where the stranger wings are in the state it solves
            a: ["FL[U]", "FR[D]"],
            b: ["FL[D]", "FR[U]"],
            f"{flip} {a}": ["FL[U]", "FR[U]"],
            f"{flip} {b}": ["FL[D]", "FR[D]"],
        }
        for alg, where in setups.items():
            c = case(4, alg)
            self.assertTrue(c.centers_solved(), alg)
            self.assertEqual(c.unpaired_edges(), ["FL", "FR"], alg)
            self.assertEqual(self.strangers(c), where, alg)
            self.assertTrue(Cube(4).apply(alg).centers_solved(), alg)
        self.assertEqual(effect(4, a) & swaps(("FL[U]", "FR[D]")), swaps(("FL[U]", "FR[D]")))
        self.assertEqual(effect(4, b) & swaps(("FL[D]", "FR[U]")), swaps(("FL[D]", "FR[U]")))

    def test_unpaired_detection(self):
        self.assertEqual(Cube(4).unpaired_edges(), [])
        c = Cube(4).apply("2R")
        self.assertEqual(c.unpaired_edges(), ["DB", "DF", "UB", "UF"])
        self.assertFalse(c.centers_solved())
        # a flipped (but paired) dedge is not "unpaired"
        self.assertEqual(Cube(4).apply("2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2").unpaired_edges(), [])


if __name__ == "__main__":
    unittest.main()
