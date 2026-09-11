"""
sanity_check.py
Pre-flight tests for the BPPC heuristics. Run this BEFORE the full experiment
to catch bugs cheaply.

Usage:
    python sanity_check.py

The script is invariant-based, not data-comparison-based. It does not look up
"correct" bin counts; instead it asserts properties that any correct
implementation must satisfy. If any assertion fails, the script prints which
invariant broke and on which instance, and exits with a non-zero status.

Cells tested (chosen to span the interesting regimes):
    (uniform, n=60,  d=0.0)   conflict-free regime
    (uniform, n=60,  d=0.3)   medium density
    (uniform, n=60,  d=0.6)   high density
    (uniform, n=120, d=0.3)   scale-up sanity
    (triplet, n=60,  d=0.0)   triplet at d=0 (FFD known to be slightly suboptimal)
    (triplet, n=60,  d=0.3)   triplet with conflicts
"""

__VERSION__ = "2026-05-07-fix1"

import math
import sys
from typing import List, Tuple

# IMPORTANT: cross-file version check happens BEFORE we try to import any
# names that only exist in the new versions. If you see ImportError below,
# it means at least one of {instance, heuristics, lower_bound}.py is the OLD
# version. Run `python verify_install.py` for a detailed report.
import instance as _instance_mod
import heuristics as _heuristics_mod
import lower_bound as _lower_bound_mod
_my_version = __VERSION__
for _name, _mod in [("instance", _instance_mod), ("heuristics", _heuristics_mod),
                    ("lower_bound", _lower_bound_mod)]:
    _v = getattr(_mod, "__VERSION__", None)
    if _v != _my_version:
        print(f"\n*** VERSION MISMATCH ***", file=sys.stderr)
        print(f"sanity_check.py is at __VERSION__={_my_version!r}", file=sys.stderr)
        print(f"but {_name}.py is at __VERSION__={_v!r}", file=sys.stderr)
        print(f"You have not finished copying all 5 files into the same directory.", file=sys.stderr)
        print(f"Run `python verify_install.py` for a detailed report.\n", file=sys.stderr)
        sys.exit(2)

from instance import make_instance, expected_realised_density
from heuristics import ffdc, bfdc, mbwfd_pure, mbwfd_capped, verify
from lower_bound import combined_lower_bound, continuous_lb, greedy_max_clique


CELLS: List[Tuple[str, int, float]] = [
    ("uniform", 60,  0.0),
    ("uniform", 60,  0.3),
    ("uniform", 60,  0.6),
    ("uniform", 120, 0.3),
    ("triplet", 60,  0.0),
    ("triplet", 60,  0.3),
]

SEEDS_PER_CELL = 5  # five seeds per cell; enough to catch flukes


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

failures: List[str] = []

def check(cond: bool, msg: str):
    """Record a failure but keep going so we collect all errors."""
    if not cond:
        failures.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  ok:   {msg}")


def check_close(actual: float, expected: float, tol: float, msg: str):
    """Same as check() but for approximate-equality on floats."""
    ok = abs(actual - expected) <= tol
    if not ok:
        failures.append(f"{msg} (actual={actual:.4f}, expected={expected:.4f}, tol={tol})")
        print(f"  FAIL: {msg} (actual={actual:.4f}, expected={expected:.4f}, tol={tol})")
    else:
        print(f"  ok:   {msg} (actual={actual:.4f})")


# ---------------------------------------------------------------------------
# Per-instance invariants
# ---------------------------------------------------------------------------

def check_one_instance(family: str, n: int, d: float, seed: int):
    """All checks that must hold on a single instance."""
    inst = make_instance(family=family, n=n, density=d, seed=seed)
    label = f"{family} n={n} d={d:.1f} seed={seed}"
    print(f"\n--- {label} ---")

    # --- Lower bound ---------------------------------------------------------
    lb = combined_lower_bound(inst)
    cont_lb = continuous_lb(inst)
    clique_lb = greedy_max_clique(inst)
    check(lb >= 1, f"{label}: LB >= 1")
    check(lb == max(cont_lb, clique_lb),
          f"{label}: combined LB = max(continuous, clique)")
    check(lb <= n, f"{label}: LB <= n (cannot need more bins than items)")

    # --- Run all four heuristics --------------------------------------------
    r_ff  = ffdc(inst)
    r_bf  = bfdc(inst)
    r_mbp = mbwfd_pure(inst)
    r_mbc = mbwfd_capped(inst)

    # --- Feasibility --------------------------------------------------------
    check(verify(inst, r_ff.bins),  f"{label}: FFD-C produces a feasible solution")
    check(verify(inst, r_bf.bins),  f"{label}: BFD-C produces a feasible solution")
    if r_mbp.bins_used == -1:
        # mbwfd_pure is allowed to fail; just record it
        print(f"  note: mbwfd_pure FAILED on {label} (no m in retry budget worked)")
        check(r_mbp.extra["status"] == "failed",
              f"{label}: mbwfd_pure status flagged as 'failed' when it fails")
    else:
        check(verify(inst, r_mbp.bins),
              f"{label}: mbwfd_pure produces a feasible solution when it succeeds")
    check(verify(inst, r_mbc.bins), f"{label}: mbwfd_capped produces a feasible solution")

    # --- Bin count >= LB ----------------------------------------------------
    check(r_ff.bins_used >= lb,  f"{label}: FFD-C bins_used >= LB")
    check(r_bf.bins_used >= lb,  f"{label}: BFD-C bins_used >= LB")
    if r_mbp.bins_used != -1:
        check(r_mbp.bins_used >= lb, f"{label}: mbwfd_pure bins_used >= LB")
    check(r_mbc.bins_used >= lb, f"{label}: mbwfd_capped bins_used >= LB")

    # --- Capped variant cannot be worse than FFD-C --------------------------
    # (FFD-C is the upper bound; capped version falls back to it on failure.)
    check(r_mbc.bins_used <= r_ff.bins_used,
          f"{label}: mbwfd_capped <= FFD-C (FFD-C is the cap)")

    # --- d == 0: no conflicts ----------------------------------------------
    if d == 0.0:
        check(inst.num_edges == 0, f"{label}: d=0 produces zero conflict edges")
        # FFD-C and BFD-C should produce identical bin counts on conflict-free
        # one-dim BPPC (this is a textbook fact for FFD vs BFD without conflicts).
        # Actually they CAN diverge on adversarial inputs but on uniform/triplet
        # they match in practice; we relax the check to "within 1".
        check(abs(r_ff.bins_used - r_bf.bins_used) <= 1,
              f"{label}: d=0 -> |FFD - BFD| <= 1")

    # --- Capped variant: if it succeeded WITHOUT fallback, verify the retries
    if not r_mbc.extra.get("used_ffdc_fallback", False):
        # retries is the number of FAILED MB-WFD passes before the successful one
        # so retries should be in [0, m_cap - m_start]
        retries = r_mbc.extra["retries"]
        m_start = r_mbc.extra["m_start"]
        m_cap = r_mbc.extra["m_cap"]
        check(0 <= retries <= m_cap - m_start,
              f"{label}: mbwfd_capped retries in [0, m_cap-m_start]")
        # the resulting bin count is m_start + retries
        check(r_mbc.bins_used == m_start + retries,
              f"{label}: mbwfd_capped bins_used == m_start + retries when no fallback")


# ---------------------------------------------------------------------------
# Cross-instance / aggregate invariants
# ---------------------------------------------------------------------------

def check_density_calibration():
    """The realised edge density should match the analytical 2*d^2 / 1-2(1-d)^2
    formula to within ~3% on n=1000 instances."""
    print("\n--- density calibration (Bug #1 sanity check) ---")
    for d in [0.1, 0.3, 0.5, 0.7, 0.9]:
        # Use an n=1000 instance for a low-variance estimate
        inst = make_instance("uniform", 1000, d, seed=12345)
        actual = inst.realised_edge_density
        expected = expected_realised_density(d)
        # Tolerance: 0.02 absolute is generous; std error is much smaller at n=1000
        check_close(actual, expected, 0.02,
                    f"density param d={d:.1f}: realised density matches 2d^2/(1-2(1-d)^2)")


def check_seed_determinism():
    """Same seed must produce the same instance."""
    print("\n--- seed determinism ---")
    a = make_instance("uniform", 100, 0.3, seed=7)
    b = make_instance("uniform", 100, 0.3, seed=7)
    check(a.sizes == b.sizes, "same seed -> identical sizes")
    check(a.neighbours == b.neighbours, "same seed -> identical conflict graph")


def check_triplet_optimum():
    """Falkenauer triplet at d=0: optimum is exactly n/3 by construction;
    LB should equal n/3."""
    print("\n--- triplet d=0 has LB = n/3 ---")
    for n in [60, 120]:
        inst = make_instance("triplet", n, 0.0, seed=1)
        lb = combined_lower_bound(inst)
        check(lb == n // 3, f"triplet n={n} d=0: LB == n/3 = {n//3}")
        # FFD on Falkenauer triplets is known to be slightly suboptimal
        # (~5% gap typical). We don't assert exact behaviour but do assert
        # the gap is not absurd.
        r_ff = ffdc(inst)
        gap = (r_ff.bins_used - lb) / lb
        check(0 <= gap <= 0.20,
              f"triplet n={n} d=0: FFD-C gap in [0, 20%] (actual: {gap*100:.1f}%)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("BPPC heuristics sanity check")
    print("=" * 70)

    # Aggregate-level invariants
    check_seed_determinism()
    check_density_calibration()
    check_triplet_optimum()

    # Per-instance invariants on the chosen cells
    print("\n" + "=" * 70)
    print("Per-instance invariants")
    print("=" * 70)
    for family, n, d in CELLS:
        for k in range(SEEDS_PER_CELL):
            seed = 100000 + k                # arbitrary but deterministic
            check_one_instance(family, n, d, seed)

    # Summary
    print("\n" + "=" * 70)
    if failures:
        print(f"SANITY CHECK FAILED. {len(failures)} invariant(s) violated:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("SANITY CHECK PASSED. All invariants held.")
        sys.exit(0)


if __name__ == "__main__":
    main()
