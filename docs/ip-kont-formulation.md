# Exact closed-tour makespan formulation: specification and feasibility

**Status: mathematical specification only.** No model is generated or run by
this document. The formulation below is exact for the discrete cell and
integer-center semantics implemented by the installed
`cgshop2027-pyutils==0.2.0` verifier and by the repository's C++ validator.
The checkout contains no primary CG:SHOP 2027 problem-statement document, so
rules not enforced by those validators are explicitly listed as unresolved.
This is not a claim that the existing `ilp` implementation is exact.

## 1. Input, output, and established semantics

An instance supplies:

- a finite target polyomino with holes;
- a finite orthogonal cutter polyomino;
- an integer `cutter_center` point in the cutter;
- a positive number $k$ of cutters.

Let $R \subset \mathbb{Z}^2$ be the finite set of unit target cells after
rasterizing the region, with holes removed. Let $C \subset \mathbb{Z}^2$ be
the cutter's rasterized unit cells translated so its `cutter_center` is the
origin. Thus cutter-center position $q \in \mathbb{Z}^2$ covers the cells
$q+C = \{q+c:c\in C\}$.

The official solution schema represents exactly $k$ cutter tours. Each tour
is a nonempty ordered list of integer center coordinates, is implicitly closed
from its last point to its first, and has axis-parallel consecutive and closing
edges. A one-point tour is stationary and has length zero. A point can be
visited again later in a tour, but an immediately repeated point is disallowed.
There is no schema restriction that a route stay inside the target region.

The official checker rasterizes the region and cutter into unit cells and
checks their combined swept coverage. The repository's `Problem::isCovered`
also visits every integer lattice center along each rectilinear edge, including
the closing edge. The official checker implements the same discrete sweep
using dilation by segments. These are the semantics used below; they do not
assert additional physical, collision, or timing rules absent from the
validator.

## 2. Coverage while moving

For a cutter with center at $q$, the covered target cells are
$q+C$. For an axis-parallel unit move from $q$ to $q+e$, where
$e\in\{(1,0),(-1,0),(0,1),(0,-1)\}$, the cutter sweeps

$$
(q+C) \cup (q+e+C).
$$

This endpoint identity follows because $C$ is a union of unit grid cells:
translating it continuously through one unit in a grid direction fills exactly
the union of the two adjacent endpoint translations. The official verifier
documents this identity and its segment-dilation implementation. A longer
integer rectilinear edge can be subdivided into unit moves; the union of their
sweeps is unchanged and their total length is unchanged.

Consequently, coverage by a route is exactly coverage by the cutter
translations at all integer lattice positions visited along its edges, not
merely at the listed corner vertices. A graph formulation on unit grid edges
must mark intermediate lattice points as visited. A formulation using only
listed corner positions and their static footprints would be incorrect.

## 3. Finite candidate-position and movement domain

Let the coordinate bounds of the cell sets be

$$
r_x^-=\min_{r\in R} r_x,\quad r_x^+=\max_{r\in R} r_x,\qquad
c_x^-=\min_{c\in C} c_x,\quad c_x^+=\max_{c\in C} c_x,
$$

and define $r_y^-,r_y^+,c_y^-,c_y^+$ analogously. Any center position that
can cover at least one target cell belongs to

$$
Q =
[r_x^- - c_x^+,\,r_x^+ - c_x^-]
\times
[r_y^- - c_y^+,\,r_y^+ - c_y^-]
\cap \mathbb{Z}^2.
$$

**Finite-domain proof for the validated discrete semantics.**

1. If a center $q$ covers any target cell, then $r=q+c$ for some
   $r\in R,c\in C$. The coordinate inequalities imply $q\in Q$.
   Therefore a position outside $Q$ covers no target cell.
2. Consider any feasible integer-coordinate rectilinear closed tour. Clamp
   each point coordinate-wise to the rectangle $Q$. Since $Q$'s bounds are
   integers, clamped vertices remain integer. On any horizontal or vertical
   edge, clamping maps the traversed interval to its intersection with $Q$
   (or to a point); it never increases that edge's length. Every lattice
   position on the original tour that could cover a target cell lies in $Q$
   and is fixed by this map. Positions outside $Q$ contribute no coverage.
   Thus the clamped tour preserves all target coverage and has no greater
   length. Remove consecutive duplicates produced by clamping. The resulting
   route is still a closed rectilinear tour; a one-position route is valid.
3. Subdivide each remaining edge into unit lattice moves. This preserves its
   length and swept cells by the unit-move identity above.

Hence restricting all tour positions to $Q$, and movement to the finite
undirected grid graph on $Q$'s lattice points, does not exclude a feasible
solution or any globally optimal makespan under these semantics. Routes may
leave the target region, but they need not leave $Q$; any excursion outside
$Q$ is coverage-irrelevant and can be projected away without increasing
length.

The domain is nonempty and a finite feasible upper bound exists for every
locally valid instance with nonempty $R,C$ and $k\ge1$. Choose any
$c_0\in C$. For every $r\in R$, visit $q_r=r-c_0\in Q$ with cutter 1;
at that position $r\in q_r+C$. Connect these positions in any order by
horizontal-then-vertical unit grid paths and close the route back to its
start. The rectangle $Q$ contains these paths. Make the other $k-1$
cutters stationary. For an enumeration $r_1,\ldots,r_M$ of the target cells,
write $q_j=r_j-c_0$ and $q_{M+1}=q_1$. The constructed route has the
explicit finite length

$$
U_0=\sum_{j=1}^{M}
\left(|q_{j+1,x}-q_{j,x}|+|q_{j+1,y}-q_{j,y}|\right)
\le M(N_x+N_y-2).
$$

For one target cell, $U_0=0$ is possible. In an implementation, use any
independently validated feasible makespan $U$ when available (and the
construction's $U_0$ as a theoretical fallback); the model can impose
$L\le U$ and $x_{ia}\le U$. This proves that the integer arc multiplicity
domain can be bounded without excluding an optimum.

The size of the finite position domain is determined by bounding-box spans,
not just by the number of target cells. Define

$$
N_x=(r_x^+-r_x^-)+(c_x^+-c_x^-)+1,\qquad
N_y=(r_y^+-r_y^-)+(c_y^+-c_y^-)+1,\qquad N=N_xN_y.
$$

The number of directed unit arcs is

$$
A=2\big((N_x-1)N_y+N_x(N_y-1)\big).
$$

All bounds are mathematical integer bounds. A production implementation must
use checked wide or arbitrary-precision arithmetic when forming these
differences and products; the current C++ `Point` uses `int`, which is not a
safe general-purpose model-index or coefficient type.

## 4. Exact objective and per-cutter route variables

Let $V=Q\cap\mathbb Z^2$ be the graph vertices, and let $D$ contain both
orientations of every undirected unit grid edge. For each cutter $i$:

- $y_{iv}\in\{0,1\}$: vertex $v$ is visited;
- $r_{iv}\in\{0,1\}$: $v$ is the selected root/start vertex;
- $x_{ia}\in\mathbb{Z}_{\ge0}$: number of times directed arc $a$ is
  traversed;
- $w_{ia}\in\{0,1\}$: arc $a$ is used at least once;
- $f_{ia}\ge0$: connectivity flow on used directed arc $a$;
- $s_{iv}\ge0$: linearization variable for root flow supply.

Let $L\ge0$ be the global makespan variable. Each unit arc has length one, so
the exact length and objective are

$$
\ell_i=\sum_{a\in D}x_{ia},\qquad
\min L,\qquad
\ell_i\le L\quad\forall i\in\{1,\ldots,k\},\qquad L\le U.
$$

This is equivalent to minimizing the maximum of the $k$ closed-tour
Manhattan lengths. For an arbitrary rectilinear edge from $p$ to $q$, its
unit subdivision has $|p_x-q_x|+|p_y-q_y|$ arcs. Every listed tour, including
its implicit last-to-first edge, therefore has length exactly the sum of its
arc multiplicities. No closing edge is omitted.

All positions are integer vertices and all route lengths are integer. Although
$L$ may be declared continuous in a linear model, minimization with
$\ell_i\le L$ makes its optimal value the integer $\max_i\ell_i$.

## 5. Coverage, route continuity, and connectivity constraints

For every target cell $u\in R$, require at least one cutter to visit a
position whose footprint contains it:

$$
\sum_{i=1}^{k}\ \sum_{\substack{v\in V\\u-v\in C}} y_{iv}\ \ge 1
\qquad\forall u\in R.
$$

The sums are sparse: for a fixed cell $u$, candidate positions are
$v=u-c$ for $c\in C$, restricted to $V$. Coverage during movement is not
lost: each original edge has been subdivided, every intermediate integer
position is a visited graph vertex, and one-unit continuous sweeps add no
cells beyond the endpoint union. An equivalent model may put the endpoint
coverage coefficient on selected unit arcs, but must not count a long edge
only by its endpoints.

For each cutter $i$, impose one root and make it visited:

$$
\sum_{v\in V}r_{iv}=1,\qquad r_{iv}\le y_{iv}\quad\forall v\in V.
$$

For every vertex, balance directed traversal multiplicities:

$$
\sum_{a\in\delta^+(v)}x_{ia}
-\sum_{a\in\delta^-(v)}x_{ia}=0
\qquad\forall v\in V.
$$

This makes the selected directed multigraph Eulerian but does **not** by
itself prevent disconnected cycles. Enforce arc-use and vertex linkage with
$$
w_{ia}\le x_{ia},\quad
x_{ia}\le U w_{ia},\quad
w_{ia}\le y_{i,\mathrm{tail}(a)},\quad
w_{ia}\le y_{i,\mathrm{head}(a)}.
$$
For $U=0$, no movement arcs are selected. Every active non-root vertex is
linked to an incident used arc; alternatively this follows from the flow
constraints below. An explicit strengthening is
$$
y_{iv}\le r_{iv}+
\sum_{a\in\delta^+(v)\cup\delta^-(v)}w_{ia}.
$$

Use single-commodity flow from the selected root to every other active
vertex. Let $S_i=\sum_v y_{iv}$. Linearize $s_{iv}=S_ir_{iv}$ with

$$
0\le s_{iv}\le N r_{iv},\quad
s_{iv}\le S_i,\quad
s_{iv}\ge S_i-N(1-r_{iv}).
$$

For every vertex, impose

$$
\sum_{a\in\delta^-(v)}f_{ia}
-\sum_{a\in\delta^+(v)}f_{ia}
=y_{iv}-s_{iv},
$$

and for every arc $a$,

$$
0\le f_{ia}\le (N-1)w_{ia}.
$$

At the root, the right side is $1-S_i$, so it supplies one unit to each
other active vertex; every other active vertex consumes one. Unvisited
vertices consume none. The capacity constraint makes flow use only selected
route arcs. Thus every active vertex is reachable from the root through used
arcs. Together with flow balance of the $x$-arcs, the selected directed
multigraph is connected and Eulerian, so it has a closed Euler walk containing
exactly the traversals represented by $x$. A one-point stationary tour is
the special case $S_i=1$, no selected arcs, and zero flow.

The $x$ variables allow repeated traversals, which are required in general
for connecting branches of a route network. A binary “use edge once” model is
not justified for arbitrary instances. Each $x_{ia}$ is bounded by $U$,
because no cutter in a solution of makespan at most $U$ can use more than
$U$ unit arcs in total.

The model does not forbid different cutters from visiting the same position,
overlapping swept cells, or crossing trajectories. The installed checker
checks union coverage and tour count, not collision avoidance. A collision
rule, if present in the primary contest statement, must be added and the model
reassessed before claiming competition-level equivalence.

## 6. Hand-verifiable semantic examples

1. **Coverage between vertices.** Let $C=\{(0,0)\}$, target cells
   $R=\{(0,0),(1,0),(2,0)\}$, and one tour list only the points
   $(0,0),(2,0)$. Its forward edge sweeps all three unit cells; its implicit
   return edge sweeps them again. Its length is $2+2=4$. A static-vertices
   coverage model would incorrectly miss $(1,0)$. The unit graph uses
   $(0,0)\to(1,0)\to(2,0)$ and the reverse return arcs, retaining length 4.
2. **Disconnected cycles are not one cutter tour.** Suppose a route model
   selects a separate directed cycle around each of two distant target
   patches for the same cutter. Degree balance alone accepts both cycles,
   but no single continuous closed tour has that support without connecting
   travel. The rooted flow requires every active vertex to connect to one root;
   the missing connecting route arcs and their length cannot be omitted.
3. **Stationary cutters and multiple cutters.** With $C=\{(0,0)\}$ and one
   target cell at $(5,7)$, one cutter can use the one-point tour
   $(5,7)$ of length zero. If there are two cutters and two target cells,
   each covered by a one-cell cutter at its own stationary position, both
   tours have length zero and makespan is zero. This rules out a positive
   area-only lower bound and confirms that each cutter needs its own
   connected-tour constraints.
4. **Travel outside the target.** With $C=\{(0,0)\}$ and
   $R=\{(0,0),(2,0)\}$, a tour that visits $(0,0),(-5,0),(2,0)$ and
   closes has length $5+7+2=14$. The detour position $(-5,0)$ covers no
   target. Clamping it to $(0,0)$ preserves coverage and gives a tour of
   length $0+2+2=4$. Thus leaving the target is allowed, but positions
   outside the useful-position rectangle cannot improve the objective.

## 7. KONT model-format mapping

The current C++ wrapper writes a linear model with `Minimize`, `Subject To`,
`Bounds`, and `Binary` sections, then invokes `kont_cmd` with `readlp`, `opt`,
and `writesol`. This establishes local use of an LP-style linear model with
binary variables and continuous variables (the existing $z$); it does not
establish every KONT feature or its numeric limits.

The formulation above is linear after the stated root-supply linearization.
It can be mapped to the demonstrated LP form as follows:

| Mathematical component | LP representation |
|---|---|
| Makespan $L$ | Continuous variable with $0\le L\le U$; `Minimize L` |
| Visited/root/arc-use decisions $y,r,w$ | Binary variables |
| Arc multiplicity $x$ | Prefer KONT general-integer variables only if its installed parser and optimizer support is verified; otherwise exact binary expansion $x_{ia}=\sum_{b=0}^{B-1}2^b z_{iab}$, with $B=\lceil\log_2(U+1)\rceil$, binary $z$, and explicit $x_{ia}\le U w_{ia}$. |
| Flow $f$, root supply $s$ | Nonnegative continuous variables with linear balance and capacity constraints |
| Coverage, degree balance, links, capacities | Sparse linear rows in `Subject To` |
| Bounds | Explicit finite bounds for all variables in `Bounds` |

Binary expansion is exact because every integer from 0 through $U$ has a
binary representation and the explicit upper bound removes larger values.
It avoids assuming general-integer syntax but adds up to
$A\lceil\log_2(U+1)\rceil$ binary variables per cutter, in addition to
$A$ arc-use binaries. The expansion variables represent counts and are not
independently tied to directed degree constraints; those constraints use the
weighted sum $x$.

Before any implementation is called KONT-compatible, a disposable tiny model
must verify LP parsing, binary variables, continuous flow, the needed variable
bounds and row sizes, `writesol` extraction, and exact integer recovery. The
local KONT user guide exists at `/Applications/kont72/docs/kont-userguide_en.pdf`,
but its format feature details have not been extracted or verified in this
audit. The existing surrogate is not evidence for the full model's practical
scalability or correctness.

## 8. Solver status, incumbent, and proof interpretation

Keep solver termination, feasibility, and optimality separate:

- A candidate is feasible only after reconstructing each cutter's connected
  Euler tour, including all unit moves and the closing return, and checking
  it with both the official parser/checker and the local objective calculator.
- A solver incumbent is a candidate, not a proof. Record the incumbent
  $L$, independently recomputed makespan, best bound, gap, exit status, and
  termination reason separately.
- An `OPTIMAL` status may certify the original objective only if the exact
  model has been generated without omitted rows/variables, the solver's
  optimality tolerances and integer feasibility are suitable, and the
  independently validated incumbent objective agrees with the reported
  objective/bound. Otherwise call it only solver-reported optimality for the
  encoded model.
- `INFEASIBLE` applies only to the encoded model. Since the finite construction
  above proves feasibility for a locally valid nonempty instance under these
  semantics, such a status should trigger model-generation or numeric
  investigation, not a claim that the contest instance is impossible.
- Time limit, interruption, numerical failure, incomplete assignment, or a
  malformed solution file cannot be promoted to an optimum. A valid incumbent
  may still be retained as a feasible upper bound.

The repository's current wrapper captures KONT logs and process status but
does not configure a MIP-gap tolerance or extract a dual bound. That is
insufficient for an original-objective optimality certificate.

## 9. Model-size and computational feasibility

Let $M=|R|$, $P=|C|$, $N=N_xN_y$, $A$ be the directed unit-arc count,
and $B=\lceil\log_2(U+1)\rceil$ when using binary-expanded arc counts. A
direct implementation has, per cutter, on the order of:

- $2N$ binary vertex/root variables and $N$ continuous root-supply
  variables;
- $A$ used-arc binaries, $AB$ binary multiplicity digits, and $A$
  continuous flow variables;
- $O(N+A)$ route, linkage, flow, and bound rows.

There are $M$ global coverage rows, each with up to $kP$ terms before
sparsity pruning, and $k$ makespan rows. Thus variable and constraint counts
are at least linear in the full bounding-box grid and directed arcs, not merely
in the number of anchors selected by a heuristic. There may be $O(kAB)$
integer variables. Linearizing connectivity avoids exponential subtour cuts,
but adds a large flow network and can weaken the relaxation. Alternative
subtour elimination can be exponential and would require a verified callback
or an explicit cut-generation loop, neither established by the current
wrapper.

The principal bottlenecks are:

1. the area of $Q$, which can be far larger than $|R|$ for sparse or
   irregular regions;
2. directed grid arcs and per-cutter connectivity variables;
3. coverage-incidence generation and memory for rasterized geometry;
4. the weak LP relaxation of grid routing, connectivity, and makespan;
5. binary expansion size through the feasible upper bound $U$, especially
   if $U$ is loose;
6. solver parsing, numerical range, branch-and-bound, and result extraction
   limits not yet established for the installed KONT build.

The formulation is mathematically finite, but this does **not** make it
computationally practical on the contest dataset. There is no validated sparse
exact formulation, decomposition theorem, or evidence that this KONT build can
solve even the tiny connected-routing models efficiently.

## 10. Assumptions, unresolved claims, and next research task

### Established from local source

- Integer polygon coordinates and integer cutter-center route coordinates.
- Region and cutter are interpreted as finite unit-cell sets by the official
  utility package.
- Tours are nonempty, rectilinear, implicitly closed; the last-to-first edge
  is included in length and coverage.
- The official checker counts the swept cutter along all integer lattice
  positions, including positions traversed between listed vertices.
- Feasibility is combined coverage by exactly $k$ tours; the checker does
  not enforce route containment or cutter-cutter collision avoidance.
- Under those semantics, the useful-position rectangle is finite, clamping
  preserves feasibility and cannot increase length, and a finite feasible
  tour exists for each locally valid nonempty raster instance.

### Not established; do not claim without primary-source verification

- Whether the primary contest statement imposes collision avoidance,
  synchronized-motion constraints, or other conditions not implemented by
  `cgshop2027-pyutils`.
- Whether every accepted contest cutter/region is intended to have exactly
  the raster semantics described by the installed package version.
- KONT's exact LP dialect support for all required bounds, continuous flows,
  coefficient ranges, variable counts, and exact integer recovery.
- A practical solve time, useful bound strength, scalability, or numerical
  reliability for this model.
- Any executed original-objective optimum or proof certificate.

The finite-domain and equivalence proof is complete for the validated
discrete semantics above. It is not a proof that an implementation using the
current KONT wrapper would be correct or practical. The smallest next
research/engineering task is to obtain and reconcile the primary contest
statement with the official verifier, then hand-build one tiny instance's
entire bounded graph model, enumerate all routes independently for that tiny
domain, solve the LP-form model with the installed KONT binary, reconstruct
the tour, and compare feasibility and objective with the official checker.
That experiment is a gate before implementing a reusable solver or making any
exactness claim. No solver implementation is included in this stage.

## Local evidence

- Official schema and sweep: `.venv/lib/python3.13/site-packages/cgshop2027_pyutils/schemas/solution.py`,
  `verify.py`, and `grid.py` (`dilate_segments`, `dilate`).
- Repository instance and sweep semantics: `src/io/InstanceReader.cpp`,
  `src/core/Problem.cpp`, `src/core/Solution.cpp`.
- Current KONT LP writer and process commands: `src/algorithms/IlpAlgorithm.cpp`.
- Existing non-equivalence warning: `README.md` (IP-KONT section),
  `docs/ilp-analysis.md`, and `docs/architecture/algorithm-registration-map.md`.

## Prompt 5 implementation gate

**Blocked: do not implement or expose this formulation as the exact public
`ip-kont` backend yet.** The finite-domain proof is conditional on the
installed verifier's discrete semantics; the primary contest statement has
not been reconciled with those semantics, and the installed KONT build has
not been shown to support the complete model dialect and solution extraction.
The mathematical model here is a research specification, not an implemented
or experimentally verified exact backend.

The public `ip-kont` mode must remain explicitly unavailable and must not
fall back to a partition candidate. The legacy `ilp` implementation remains
only the `vertical_column_assignment_surrogate`; any partition fallback must
retain `partition` as its actual implementation and candidate source.

The next gate is to obtain and reconcile the primary contest statement, then
build one tiny bounded-grid model, exhaustively enumerate the same instance's
routes independently, solve that model with the installed KONT executable,
and compare the extracted route, feasibility, and closed-tour makespan with
the official checker. Separately verify KONT's required LP features and
solution-file format. Do not start a reusable exact backend until those checks
pass.
