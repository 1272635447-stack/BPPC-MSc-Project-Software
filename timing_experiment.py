"""
timing_experiment.py
A separate, smaller experiment that measures runtime vs n.

Why a separate driver? The main experiments.py reports gap (solution quality),
not raw runtime trends. To produce the runtime-vs-n plot for Section 4.3
of the report, we want to vary n over a wide range while holding the conflict
density and family fixed. We use d=0 (conflict-free) so that the heuristics
are measured on the same workload across n: at d>0 the conflict-graph
construction itself is O(n^2) and would dominate the runtime, masking the
heuristic's own scaling.

Usage:
    python timing_experiment.py --out timing.csv

Output CSV columns:
    n,seed,heuristic,bins_used,lb,gap,runtime_ms

For each n in N_LIST, we run REPS_PER_N independent instances per family,
each with a deterministic seed.
"""

__VERSION__ = "2026-05-07-fix1"

import argparse
import csv
import sys
import time

# Cross-file version sync check (same pattern as experiments.py)
import instance as _instance_mod
import heuristics as _heuristics_mod
import lower_bound as _lower_bound_mod
_my_version = __VERSION__
for _name, _mod in [("instance", _instance_mod), ("heuristics", _heuristics_mod),
                    ("lower_bound", _lower_bound_mod)]:
    _v = getattr(_mod, "__VERSION__", None)
    if _v != _my_version:
        print(f"VERSION MISMATCH: {_name}.py is at {_v!r}, "
              f"timing_experiment.py is at {_my_version!r}.", file=sys.stderr)
        print("Run `python verify_install.py` for a detailed report.", file=sys.stderr)
        sys.exit(2)

from instance import make_instance
from heuristics import ffdc, bfdc, mbwfd_pure, mbwfd_capped, verify
from lower_bound import combined_lower_bound

# n values: log-spaced enough to fit a power-law in log-log space.
N_LIST_UNIFORM = [60, 120, 250, 500, 1000, 2000]
N_LIST_TRIPLET = [60, 120, 249, 501, 999, 1998]   # multiples of 3

REPS_PER_N = 5
DENSITY = 0.0   # conflict-free: see module docstring


def make_seed(base_seed: int, family: str, n: int, k: int) -> int:
    """Deterministic seed for the timing experiment, separate namespace
    from experiments.py to avoid collisions."""
    family_id = {"uniform": 1, "triplet": 2}[family]
    return base_seed * 100_000_000 + family_id * 10_000_000 + n * 1000 + k


def run_one(inst, heuristic_fn, name):
    res = heuristic_fn(inst)
    if res.bins_used == -1:
        return res
    if not verify(inst, res.bins):
        raise RuntimeError(f"{name} produced INFEASIBLE solution on {inst.name}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-seed", type=int, default=0)
    ap.add_argument("--out", default="timing.csv")
    args = ap.parse_args()

    rows = []
    families = [("uniform", N_LIST_UNIFORM), ("triplet", N_LIST_TRIPLET)]
    total_runs = 0

    print(f"Timing experiment: density={DENSITY} (conflict-free), "
          f"reps={REPS_PER_N} per (family, n)")
    t0 = time.perf_counter()

    for family, n_list in families:
        for n in n_list:
            for k in range(REPS_PER_N):
                seed = make_seed(args.base_seed, family, n, k)
                inst = make_instance(family=family, n=n, density=DENSITY, seed=seed)
                lb = combined_lower_bound(inst)
                for hname, hfn in [
                    ("FFD-C",         ffdc),
                    ("BFD-C",         bfdc),
                    ("MB-WFD-pure",   mbwfd_pure),
                    ("MB-WFD-capped", mbwfd_capped),
                ]:
                    res = run_one(inst, hfn, hname)
                    if res.bins_used == -1:
                        gap = float("nan")
                    else:
                        gap = (res.bins_used - lb) / lb if lb > 0 else 0.0
                    rows.append({
                        "family":      family,
                        "n":           n,
                        "seed":        seed,
                        "heuristic":   hname,
                        "bins_used":   res.bins_used,
                        "lb":          lb,
                        "gap":         gap,
                        "runtime_ms":  res.runtime_ms,
                    })
                    total_runs += 1
            print(f"  done {family} n={n}  ({REPS_PER_N} reps)")

    t1 = time.perf_counter()

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nTotal runs: {total_runs}")
    print(f"Wall-clock time: {t1 - t0:.1f} s")
    print(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
