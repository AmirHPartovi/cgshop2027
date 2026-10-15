# Geometry rasterization performance

`Problem::raster` now rasterizes valid orthogonal rings by scanline. It
activates vertical boundary crossings at integer y coordinates and fills cell
centers between crossing pairs. Across the outer ring and hole rings, the
even-odd rule is equivalent to the previous point-in-polygon test for valid,
non-intersecting CG:SHOP inputs. The previous point-in-polygon implementation
remains in the algorithm regression test as a differential reference. Region
and cutter cell sets are still recomputed on demand; no mutable geometry cache
was added because the `Problem` geometry fields are publicly mutable.

## Local measurement

Measured on macOS 27.2 / Apple M1 Pro, Release build, using
`data/test/pla34k_75k_1p.instance.json` (79,527 rasterized region cells, 602
outer-boundary vertices, 60 holes). Each timing is a complete `partition`
solver process with `--algorithm-timeout 10`, measured by Python
`time.perf_counter`; output went to a temporary directory under `build/`.

| Rasterizer | Wall-time samples (seconds) | Median | Peak RSS |
|---|---:|---:|---:|
| Point-in-polygon baseline | 1.375444, 1.337779, 1.342559 | 1.342559 | 17.84 MB in one `/usr/bin/time -l` run |
| Scanline | 0.145984, 0.144673, 0.150000 | 0.145984 | 15.83–17.97 MB across three `/usr/bin/time -l` runs; median 17.58 MB |

The measured median wall time decreased by about 89% (9.2x faster). The RSS
measurements do not show a meaningful memory reduction; both versions used
roughly 16–19 MB. Since the baseline RSS is one sample and peak RSS is
environment-sensitive, no memory improvement is claimed.

Representative command:

```sh
/usr/bin/time -l build/bin/solver \
  -i data/test/pla34k_75k_1p.instance.json \
  -o build/profile-output.solution.json \
  --algorithm partition --algorithm-timeout 10
```

Both the baseline and scanline solver outputs for this instance were accepted
by the official `cgshop2027_pyutils` validator. The solver's exact coverage
semantics are unchanged. The scanline implementation stores only boundary
events and the rasterized cell set; repeated calls still rerasterize, but the
dominant per-cell scans over all ring edges have been removed.
