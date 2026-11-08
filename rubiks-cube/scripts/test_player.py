"""Tests for player.py.

Run: python3 -m unittest discover -s scripts   (from the skill folder)
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import player  # noqa: E402

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PURE = "2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2"


class ParsePlayer(unittest.TestCase):
    def test_full_spec(self):
        p = player.parse_player(f"Pure|4x4|{PURE}|end|Only UF changes.")
        self.assertEqual(p, {"title": "Pure", "puzzle": "4x4x4", "alg": PURE, "anchor": "end",
                             "note": "Only UF changes."})

    def test_defaults(self):
        p = player.parse_player("T-perm|3x3|R U R'  U'")
        self.assertEqual((p["puzzle"], p["anchor"], p["note"], p["alg"]), ("3x3x3", "end", "", "R U R' U'"))

    def test_start_anchor(self):
        self.assertEqual(player.parse_player("A|3x3|R|start")["anchor"], "start")

    def test_rejects_bad_input(self):
        for spec in ("A|6x6|R", "A|3x3|R|middle", "A|3x3|", "A|3x3", "A|3x3|R|end|n|extra"):
            with self.assertRaises(ValueError, msg=spec):
                player.parse_player(spec)


class Render(unittest.TestCase):
    def test_contains_players(self):
        page = player.render("Flip one edge", [player.parse_player(f"Pure|4x4|{PURE}|end|note one"),
                                               player.parse_player("Sune|3x3|R U R' U R U2 R'|start")])
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("<title>Flip one edge</title>", page)
        self.assertIn('puzzle="4x4x4"', page)
        self.assertIn('puzzle="3x3x3"', page)
        self.assertIn("alg=\"2R2 B2 U2 2L U2 2R&#x27; U2", page)
        self.assertIn('experimental-setup-anchor="start"', page)
        self.assertIn('<twisty-alg-viewer for="p2">', page)
        self.assertIn("note one", page)
        self.assertNotIn("{{", page)

    def test_escapes_text(self):
        page = player.render('<b>x</b>', [player.parse_player('<img src=x>|3x3|R" onload="bad|end|<script>')])
        self.assertNotIn("<b>x</b>", page)
        self.assertNotIn("<img src=x>", page)
        self.assertNotIn('" onload="', page)
        self.assertIn("&lt;script&gt;", page)

    def test_try_box_uses_first_player(self):
        page = player.render("x", [player.parse_player("A|3x3|R U")])
        self.assertIn('value="R U"', page)
        self.assertIn('<option value="3x3x3" selected>', page)

    def test_5x5(self):
        page = player.render("x", [player.parse_player(f"Parity|5x5|{PURE}")])
        self.assertIn('puzzle="5x5x5"', page)
        self.assertIn('<option value="5x5x5" selected>', page)

    def test_needs_a_player(self):
        with self.assertRaises(ValueError):
            player.render("x", [])


class Build(unittest.TestCase):
    def test_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = player.build("Flip one edge on a 4x4!", [f"Pure|4x4|{PURE}"], out_dir=d)
            self.assertEqual(path, os.path.join(d, "flip-one-edge-on-a-4x4.html"))
            with open(path, encoding="utf-8") as f:
                self.assertIn("twisty-player", f.read())

    def test_default_out_dir_is_outside_skill(self):
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": ""}):
            d = player.default_out_dir()
        self.assertEqual(d, os.path.join(os.path.expanduser("~"), ".cache", "rubiks-cube", "players"))
        self.assertFalse(os.path.abspath(d).startswith(SKILL_DIR))

    def test_default_out_dir_follows_xdg(self):
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/xdg"}):
            self.assertEqual(player.default_out_dir(), "/tmp/xdg/rubiks-cube/players")


if __name__ == "__main__":
    unittest.main()
