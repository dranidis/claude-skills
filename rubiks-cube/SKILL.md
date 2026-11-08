---
name: rubiks-cube
description: >
  Advice and move sequences (algorithms) for solving 3x3 and 4x4 Rubik's cubes:
  beginner method, CFOP basics (cross, F2L, 2-look OLL/PLL), the user's own
  no-memorization method (empty F2L slot + corner commutators), 4x4 reduction
  (centers, edge pairing, OLL parity, PLL parity), and fixing single problems
  like "flip the last edge on a 4x4 without changing anything else", "two
  corners are swapped", or "what does this alg do". Includes a simulator to
  check every algorithm before giving it. Use for any Rubik's cube, speedcubing,
  cube notation, parity, or "how do I solve / fix" cube question.
---

# Rubik's cube helper

Help people solve 3x3 and 4x4 cubes. Give moves that are **checked**, not
remembered: algorithms are easy to get wrong by one move or one layer.

## Files

- `references/notation.md`: move notation, piece names. Read when a user's
  notation is unclear, or before writing 4x4 moves.
- `references/3x3.md`: beginner method, 2-look OLL/PLL, single fixes, impossible states.
- `references/my-method.md`: the user's own 3x3 method (3 F2L pairs, edges via the
  empty slot, corners with commutators). Use when they say "my method" or ask about
  commutators / the empty-slot trick. `cube.py` does not read `[A, B]`: expand it
  to `A B A' B'` (and `[S: M]` to `S M S'`) before checking.
- `references/4x4.md`: reduction, edge pairing, OLL parity, PLL parity.
- `scripts/cube.py`: simulator (stdlib Python). Tested on 3x3 and 4x4 only.
- `scripts/player.py`: builds a local animation page (cubing.js players) and serves it on localhost.

Read the reference file for the cube size in question before answering.

## Simulator

Use the full path, the working folder will usually be somewhere else:

```
python3 ~/.claude/skills/rubiks-cube/scripts/cube.py apply  -n 4 "ALG"   # what ALG does to a solved cube
python3 ~/.claude/skills/rubiks-cube/scripts/cube.py case   -n 4 "ALG"   # the state ALG solves (how to hold the cube)
python3 ~/.claude/skills/rubiks-cube/scripts/cube.py invert "ALG"
python3 ~/.claude/skills/rubiks-cube/scripts/cube.py order  -n 3 "ALG"   # repeats until solved
python3 ~/.claude/skills/rubiks-cube/scripts/cube.py same   -n 3 "A" "B" # same visible effect?
```

The report shows a facelet net, the number of wrong stickers, the pieces that
visibly moved (e.g. `UF[L]: now at UF[R]`), and for 4x4: centers solved and
unpaired edge slots. Whole-cube rotations are ignored.

## Animation

When an animation would help, or the user asks for one, build a **local** page.

**Never publish a cube animation (or any page from this skill) with the Artifact
tool.** Pages stay on this machine: a local file plus a local server.

1. Check the moves with `cube.py` first (same as any answer).
2. Build the page. Each `--player` is `TITLE|CUBE|MOVES|START|NOTE`, where CUBE is
   `3x3`, `4x4` or `5x5`, START is `end` (start from the case, finish solved; default) or
   `start` (start solved):

   ```
   python3 ~/.claude/skills/rubiks-cube/scripts/player.py build \
     --title "Flip one edge on a 4x4" --eyebrow "OLL parity" \
     --intro "Hold the flipped edge at the front of the top face." \
     --player "Pure version|4x4|2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2|end|Changes only the UF edge."
   ```

   It prints the file path. Default folder: `~/.cache/rubiks-cube/players/`.
3. Serve the folder with Bash `run_in_background: true` (skip if a server from
   this session is still running; the folder is the same):

   ```
   python3 ~/.claude/skills/rubiks-cube/scripts/player.py serve
   ```

   It binds to 127.0.0.1, uses port 8765 or the next free one, and prints one
   URL per page. Read its output, then give the user the `http://127.0.0.1:...` link.
4. Tell the user: the link works only on this machine and while the server
   runs (they can restart it with the same command), and the page loads
   cubing.js from cdn.jsdelivr.net, so it needs internet.

The page also has a "Try any moves" box. Write 4x4 moves as `2R` / `Rw` there too.

## How to answer

1. **Find the case.** Work out what the user sees. If it is unclear which face is
   on top/front or which pieces are wrong, ask one short question, or state the
   hold you assume ("hold the flipped edge at front-top").
2. **Check if it is possible.** On a 3x3, one flipped edge, one twisted corner, or
   just two swapped pieces cannot happen on a correctly assembled cube: tell the
   user it was reassembled wrong (see `3x3.md`). On a 4x4 these are parity
   cases and have fixes.
3. **Pick an alg** from the references. If the user wants "nothing else changes",
   pick a pure alg (fewest wrong stickers in `apply`).
4. **Verify before answering.** Run `apply` (and `case` for the hold) on every alg
   you give, including ones you adapt, mirror, or add setup moves to. Confirm the
   effect matches what you claim. If a user gives their own alg, run it too; for
   4x4 lowercase moves run both readings (`r` = `Rw` and `r` = `2R`).
5. **Answer simply:**
   - how to hold the cube,
   - the moves, grouped in short chunks,
   - what it changes (and what it keeps),
   - one line on why this case happened, if useful.
   Write 4x4 moves as `2R` (inner slice) or `Rw` (two layers), never lowercase.
   Explain notation once if the user seems new.

If no reference alg fits, you may build one (setup moves + known alg + undo
setup, or a commutator), but only give it after the simulator confirms it.
If you could not verify something, say so.

## Example

> How can I flip the last wrong edge on a 4x4 without changing anything else?

That is OLL parity. Check it: `cube.py apply -n 4 "2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2"` → 4 wrong stickers, only `UF[L]` ↔ `UF[R]`.

Answer: Hold the cube so the flipped edge is at the front of the top face (UF).
Do:

`2R2 B2 U2 2L` · `U2 2R' U2 2R` · `U2 F2 2R F2` · `2L' B2 2R2`

(`2R` = only the inner slice next to R, `2L` = inner slice next to L.)
Only that edge flips. Centers, corners and all other edges stay the same.
This happens because on a 4x4 the two halves of an edge can swap places, which
cannot happen on a 3x3. If eleven edges are paired, the last one is never
"half wrong": it is either fine or fully flipped, so this is the fix.
