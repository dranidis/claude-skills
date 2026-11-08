# My method (3x3, no algorithms to learn)

The user's own method. Not for speed (their record: 30 s). Source page:
`~/Obsidian/myStack/Rubic's cube/My solution method.md`. Use this file when the
user says "my method", or asks about the empty-slot edge trick or corner
commutators. All algs below were checked with `cube.py`.

Hold: white cross on the bottom, yellow on top. "Working slot" = the one F2L
slot left empty, here front-right (FR edge, DFR corner).

## Outline

1. White cross.
2. F2L, but solve only 3 pairs. The empty slot is the working slot.
3. Solve the rest of the edges (orient, then permute) using the working slot.
4. Solve the rest of the corners (up to 5) with 3-corner commutators.

## Step 3.1: orient the edges

Swap edges between the top and the working slot, one at a time, with
`R U-turn R'` or `F' U-turn F`.

- Look at the edge in the working slot. Choose the first move that lifts it to
  the top with yellow facing up: `R` if its yellow is on the F side, `F'` if its
  yellow is on the R side.
- Turn U to bring a wrongly oriented top edge to where the undo move takes it:
  `UR` before `R'`, `UF` before `F`.
- Undo the first move (`R'` or `F`). The good edge stays on top, the bad one is
  now in the slot.

Example (only the edge that belongs in the slot is flipped, at UF): `F' U' F`.

## Step 3.2: permute the edges

First turn U to see how many of the 3 top yellow edges can match their centers
at the same time.

- **All 3 match.** The slot edge only has to go into the top layer without
  changing the order.
  - Slot edge lifted with `R`: put the non-yellow top edge at `UF`, do
    `R U R' U R U R' U2`.
  - Slot edge lifted with `F'`: put the non-yellow top edge at `UR`, do
    `F' U' F U' F' U' F U2`.
  - Finish with a U turn. Each alg swaps the slot edge with the edge at `UF`
    (or `UR`) and leaves the other top edges where they are. It also moves
    4 corners (DFR, UFR and two more); step 4 fixes those.
- **2 match.** Turn U so a wrong top edge lines up with the slot edge, then
  `U R U' R'` (or front version `U' F' U F`): lift with `R`/`F'`, U-turn,
  undo.
- **1 matches.** Swap any wrong top edge with the slot edge (`R U R'` style).
  This gives the "2 match" case.

## Step 4: corners with commutators

All edges are done. At most 5 corners are wrong (4 top + DFR).

Notation: `[A, B]` = `A B A' B'` (commutator), `[S: M]` = `S M S'` (conjugate).
A is `R' D R`, `R' D2 R`, `L D' L'` or `L D2 L'`. B is `U`, `U'` or `U2`.
Each one cycles exactly 3 corners and nothing else.

### Basic case

Needs:
- two cycle corners on top, one on the bottom,
- one top corner has yellow on U (call it the "good top corner"),
- the bottom corner belongs where the good top corner is, and its yellow is on
  a side face, not on D.

A brings the bottom corner up into the good top corner's place. B brings that
corner's target spot into the same place first.

Checked effects (hold yellow up, "X → Y" = piece at X moves to Y):

| Alg | Cycle |
|---|---|
| `[L D' L', U]` | DFR → UFL → UFR → DFR |
| `[L D2 L', U']` | DBR → UFL → UBL → DBR |
| `[R' D R, U']` | DFL → UFR → UFL → DFL |
| `[R' D2 R, U2]` | DBL → UFR → UBL → DBL |
| `[L D L', U]` | DFL → UFL → UFR → DFL |
| `[U': [R' D R, U]]` | same as `[L D L', U]`, with the R-side move |

Choosing B (from where the good top corner must go):
- good top corner at UFL (L-side A): target UFR → `U`, UBL → `U'`, UBR → `U2`.
- good top corner at UFR (R-side A): target UFL → `U'`, UBR → `U`, UBL → `U2`.

(The user's page has UBL/UBR the other way round for the UFL case; the
simulator shows the rule above is right.)

### Setup moves (then undo them)

- **All 3 wrong corners on top.** Move one down so its yellow ends on a side
  face, without touching the other two. Example: `[F U': [L D' L', U']]`
  cycles UFR → UBL → UBR → UFR.
- **Bottom corner has yellow on D.** Turn it so yellow is on a side, without
  touching the other two. Example: `[R': [L D2 L', U']]` cycles
  DFR → UFL → UBL → DFR. Longer example: `[L' F L D2: [L D' L', U2]]` cycles
  DFR → UFL → UBR → DFR.
- **No top corner has yellow on U, on any side you rotate to.** Move a corner so
  its U color shows on top, and remember which of its colors now plays the role
  of "U color". Example (hold with `y2` from the page): `[F' U': [R' D2 R, U2]]`
  cycles DBL → UFR → UBR → DBL.
- **Only 2 corners wrong.** Use a solved corner as a helper: one commutator
  with the 2 wrong corners plus the helper, then a second one to fix the
  rest. Don't let the first setup touch the wrong bottom corner (if it is at
  DFR, avoid starting with R or F moves; use `[L D' L', U]` style).
  Example: `F U2 [L D' L', U] U2 F'` cycles UFR → UBR → UBL → UFR.

## Tip from the user

In step 4, rotate the cube to look for a top corner with yellow (U color) on U,
then check if the corner that belongs there is at the bottom with yellow on a
side. When you find one, do the cycle.
