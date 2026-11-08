# Notation

Hold the cube with one face toward you (F) and one on top (U). Every turn is
**clockwise as seen when looking straight at that face**.

| Move | Meaning |
|---|---|
| `R L U D F B` | outer layer: Right, Left, Up, Down, Front, Back |
| `R'` | counter-clockwise (say "R prime") |
| `R2` | half turn (direction does not matter) |
| `x y z` | turn the whole cube: `x` like R, `y` like U, `z` like F |

## 3x3 only

| Move | Meaning |
|---|---|
| `M` | middle layer between L and R, turns like `L` |
| `E` | middle layer between U and D, turns like `D` |
| `S` | middle layer between F and B, turns like `F` |
| `Rw` or `r` | R plus the middle layer (two layers) |

## 4x4 (and bigger)

| Move | Meaning |
|---|---|
| `R` | only the outer layer |
| `2R` | only the **second** layer from the right (inner slice) |
| `Rw` | outer two layers together (`R` + `2R`) |
| `3Rw` | outer three layers together |

**Lowercase is ambiguous on 4x4.** In WCA/SiGN, `r` means `Rw` (two layers).
Many older 4x4 parity algs use `r` to mean the inner slice only (`2R`).
Reading the wrong way breaks the alg. In answers, always write `2R` or `Rw`,
never lowercase. If a user gives an alg with lowercase moves, test both readings
with the simulator.

There is no `M` on a 4x4. Use `2R`/`2L` (or `Rw R'`).

## Piece names

- Corners: three faces, e.g. `UFR` (up-front-right).
- Edges: two faces, e.g. `UF`. On 4x4 a full edge ("dedge") is two **wings**;
  the simulator names them by side: `UF[L]` is the UF wing on the L side.
- 4x4 centers: `U[FL]` is the U center piece at the front-left.

## Simulator facelet net

`cube.py` prints faces like this (each letter = the face that colour belongs to):

```
    U
L F R B
    D
```

U is shown with B at the top row, F at the bottom. D is shown with F at the top.
L, F, R, B are shown as if you walk around the cube.
