"""
experiments.py
Top-level experiment driver. Iterates over (family, n, density, k, heuristic)
and writes results to a CSV.

Usage:
    python experiments.py --scale sanity   # ~ 100 instances, a few minutes
    python experiments.py --scale medium   # ~ 600 instances, ~10-20 min
    python experiments.py --scale full     # 800 instances, full Gendreau benchmark
    python experiments.py --scale sanity --base-seed 42

Output CSV columns:
    family,n,density,realised_edge_density,seed,heuristic,bins_used,lb,gap,
    runtime_ms,retries,status,used_ffdc_fallback

Notes:
  * `density` here is the GENERATOR PARAMETER d in the Gendreau (2004)
    protocol; it is NOT the realised edge density of the conflict graph.
    See the Ch3 calibration table for the mapping.
  * `gap` is (bins_used - lb) / lb. For MB-WFD-pure, when the algorithm
    fails (no m in [LB, LB+max_retries] succeeds), bins_used is -1 and
    gap is reported as NaN; downstream analysis must filter these rows.
  * Seeds are deterministic functions of (family, n, density_index, k,
    base_seed). Two runs with the same base_seed produce identical
    instances and identical results.
"""

__VERSION__ = "2026-05-07-fix1"

import argparse
import csv
import math
import time

from instance import make_instance
from heuristics import ffdc, bfdc, mbwfd_pure, mbwfd_capped, verify
from lower_bound import combined_lower_bound

# Sanity check: every file in the repo must be from the same fix.
# If you see a mismatch, you have not finished copying all 5 files.
import instance, heuristics, lower_bound
_files = {"instance": instance, "heuristics": heuristics, "lower_bound": lower_bound}
_my_version = __VERSION__
for _name, _mod in _files.items():
    _v = getattr(_mod, "__VERSION__", None)
    if _v != _my_version:
        raise RuntimeError(
            f"VERSION MISMATCH: {_name}.py has __VERSION__={_v!r} but "
            f"experiments.py has __VERSION__={_my_version!r}. "
            f"You have not finished copying all 5 files into the same directory. "
            f"Run `python verify_install.py` for a detailed report."
        )


# Three "scales" so the user can start small and ramp up.
SCALES = {
    "sanity": {
        "uniform": [60, 120],
        "triplet": [60, 120],
        "densities": [0.0, 0.2, 0.4, 0.6, 0.8],
        "instances_per_cell": 3,
    },
    "medium": {
        "uniform": [120, 250, 500],
        "triplet": [60, 120, 249],
        "densities": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        "instances_per_cell": 5,
    },
    "full": {
        "uniform": [120, 250, 500, 1000],
        "triplet": [60, 120, 249, 501],
        "densities": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        "instances_per_cell": 10,
    },
}

# Stable numeric encoding of family and n so that the seed is reproducible
# across machines and Python versions. (Python's built-in hash() is
# randomised per process unless PYTHONHASHSEED is set, so we MUST NOT use
# hash() here.)
_FAMILY_ID = {"uniform": 1, "triplet": 2}


def make_seed(base_seed: int, family: str, n: int, density: float, k: int) -> int:
    """Deterministic seed for a single (family, n, density, k) cell.
    Independent of Python version and PYTHONHASHSEED.

    Layout (decimal, fits in 32-bit signed int for base_seed up to 999):
      base_seed * 10_000_000
      + family_id * 1_000_000          (1 = uniform, 2 = triplet)
      + n * 100                        (n is at most 1000 in our experiments)
      + density_index * 10             (0..9 for d in {0.0, 0.1, ..., 0.9})
      + k                              (0..9)
    """
    family_id = _FAMILY_ID[family]
    density_index = int(round(density * 10))
    return (base_seed * 10_000_000
            + family_id * 1_000_000
            + n * 100
            + density_index * 10
            + k)


def run_one(inst, heuristic_fn, name):
    """Run a single heuristic on a single instance. Verify feasibility unless
    the heuristic explicitly reported failure (bins_used == -1)."""
    res = heuristic_fn(inst)
    if res.bins_used == -1:
        # MB-WFD-pure can legitimately report failure. Don't try to verify.
        return res
    ok = verify(inst, res.bins)
    if not ok:
        raise RuntimeError(f"{name} produced an INFEASIBLE solution on {inst.name}")
    return res


def run_scale(scale: str, base_seed: int = 0, output_csv: str = "results.csv"):
    cfg = SCALES[scale]
    densities = cfg["densities"]
    inst_per_cell = cfg["instances_per_cell"]

    rows = []
    total_runs = 0
    for family in ("uniform", "triplet"):
        ns = cfg[family]
        for n in ns:
            if family == "triplet":
                # triplet n must be a multiple of 3; round down if needed
                n = (n // 3) * 3
            for density in densities:
                for k in range(inst_per_cell):
                    seed = make_seed(base_seed, family, n, density, k)
                    inst = make_instance(family=family, n=n, density=density, seed=seed)
                    lb = combined_lower_bound(inst)
                    realised_d = inst.realised_edge_density
                    for hname, hfn in [
                        ("FFD-C",         ffdc),
                        ("BFD-C",         bfdc),
                        ("MB-WFD-pure",   mbwfd_pure),
                        ("MB-WFD-capped", mbwfd_capped),
                    ]:
                        res = run_one(inst, hfn, hname)
                        if res.bins_used == -1:
                            gap = float("nan")
                        elif lb > 0:
                            gap = (res.bins_used - lb) / lb
                        else:
                            gap = 0.0
                        rows.append({
                            "family":               family,
                            "n":                    n,
                            "density":              density,
                            "realised_edge_density": realised_d,
                            "seed":                 seed,
                            "heuristic":            hname,
                            "bins_used":            res.bins_used,
                            "lb":                   lb,
                            "gap":                  gap,
                            "runtime_ms":           res.runtime_ms,
                            "retries":              res.extra.get("retries", ""),
                            "status":               res.extra.get("status", "success"),
                            "used_ffdc_fallback":   res.extra.get("used_ffdc_fallback", ""),
                        })
                        total_runs += 1
                    print(".", end="", flush=True)
            print(f"  done {family} n={n}")
    print()
    print(f"Total runs: {total_runs}")

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {output_csv}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", choices=list(SCALES.keys()), default="sanity")
    ap.add_argument("--base-seed", type=int, default=0,
                    help="Base seed for deterministic instance generation. "
                         "Same base-seed reproduces the same experiments exactly.")
    ap.add_argument("--out", default="results.csv")
    args = ap.parse_args()

    print(f"Running scale={args.scale}, base_seed={args.base_seed}")
    print(f"Configuration: {SCALES[args.scale]}")
    print()
    t0 = time.perf_counter()
    rows = run_scale(args.scale, base_seed=args.base_seed, output_csv=args.out)
    t1 = time.perf_counter()
    print(f"Total wall-clock time: {t1 - t0:.1f} s")


if __name__ == "__main__":
    main()
