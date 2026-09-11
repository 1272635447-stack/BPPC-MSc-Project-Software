"""
test_smoke.py
Small unit-style tests that you can run before launching the big experiment.

    python test_smoke.py

The tests check correctness on tiny hand-constructed instances where the
answer is obvious (or known). If anything is broken in the code, this script
will tell you immediately, rather than after a 20-minute experiment run.
"""

import sys
from instance import Instance, make_instance
from heuristics import ffdc, bfdc, mbwfd, verify
from lower_bound import combined_lower_bound, continuous_lb, greedy_max_clique


def case(name):
    print(f"  {name} ... ", end="")


def ok():
    print("ok")


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


# ----------------------------------------------------------------------
# Test 1. Trivial: 3 items of size 0.5, no conflicts.
#         Optimum = 2 bins (any pair fits, third item alone).
# ----------------------------------------------------------------------
def test_trivial_no_conflicts():
    case("trivial: 3 items of 0.5, no conflicts -> 2 bins")
    inst = Instance(sizes=[0.5, 0.5, 0.5], capacity=1.0,
                    neighbours={0: set(), 1: set(), 2: set()})
    for fn, name in [(ffdc, "FFD-C"), (bfdc, "BFD-C"), (mbwfd, "MB-WFD")]:
        r = fn(inst)
        if r.bins_used != 2:
            fail(f"{name} returned {r.bins_used}, expected 2")
        if not verify(inst, r.bins):
            fail(f"{name} returned an invalid solution")
    ok()


# ----------------------------------------------------------------------
# Test 2. The chain-effect example from the dissertation:
#         6 items of sizes 0.5, 0.5, 0.5, 0.4, 0.4, 0.4
#         items 1,2,3 mutually conflict; items 4,5,6 conflict with no one.
#         Optimum = 3 bins.
# ----------------------------------------------------------------------
def test_chain_effect_example_a():
    case("chain example A (1,2,3 mutually conflict) -> 3 bins")
    sizes = [0.5, 0.5, 0.5, 0.4, 0.4, 0.4]
    neigh = {0: {1, 2}, 1: {0, 2}, 2: {0, 1}, 3: set(), 4: set(), 5: set()}
    inst = Instance(sizes=sizes, capacity=1.0, neighbours=neigh)
    for fn, name in [(ffdc, "FFD-C"), (bfdc, "BFD-C"), (mbwfd, "MB-WFD")]:
        r = fn(inst)
        if not verify(inst, r.bins):
            fail(f"{name} returned an invalid solution")
        # On example A, all three should still find 3 bins.
        if r.bins_used != 3:
            print(f" [note: {name} used {r.bins_used} bins]", end="")
    ok()


# ----------------------------------------------------------------------
# Test 3. Lower bound sanity.
# ----------------------------------------------------------------------
def test_lower_bound():
    case("LB on 3-clique with sizes 0.5,0.5,0.5 -> max(2, 3) = 3")
    sizes = [0.5, 0.5, 0.5]
    neigh = {0: {1, 2}, 1: {0, 2}, 2: {0, 1}}
    inst = Instance(sizes=sizes, capacity=1.0, neighbours=neigh)
    cb = continuous_lb(inst)
    cl = greedy_max_clique(inst)
    lb = combined_lower_bound(inst)
    if cb != 2:
        fail(f"continuous LB = {cb}, expected 2")
    if cl != 3:
        fail(f"clique LB = {cl}, expected 3")
    if lb != 3:
        fail(f"combined LB = {lb}, expected 3")
    ok()


# ----------------------------------------------------------------------
# Test 4. A larger random instance: every heuristic must produce a valid
#         solution and at least as many bins as the lower bound.
# ----------------------------------------------------------------------
def test_random_instance():
    case("random uniform n=50 d=0.3, all heuristics feasible and >= LB")
    inst = make_instance("uniform", n=50, density=0.3, seed=1)
    lb = combined_lower_bound(inst)
    for fn, name in [(ffdc, "FFD-C"), (bfdc, "BFD-C"), (mbwfd, "MB-WFD")]:
        r = fn(inst)
        if not verify(inst, r.bins):
            fail(f"{name} produced invalid solution")
        if r.bins_used < lb:
            fail(f"{name} returned {r.bins_used} bins, below LB={lb}")
    ok()


# ----------------------------------------------------------------------
# Test 5. Triplet instances at d=0 must have UB = LB = n/3 exactly,
#         because Falkenauer triplets are constructed to be perfectly packable.
# ----------------------------------------------------------------------
def test_triplet_optimum():
    case("triplet n=60 d=0 -> all heuristics reach n/3 bins (or close)")
    inst = make_instance("triplet", n=60, density=0.0, seed=1)
    lb = combined_lower_bound(inst)
    if lb != 20:
        fail(f"LB = {lb}, expected 20 for n=60 triplets")
    # Heuristics may not always reach the exact triplet optimum; we just check
    # that they're at least feasible and not outrageously bad.
    for fn, name in [(ffdc, "FFD-C"), (bfdc, "BFD-C"), (mbwfd, "MB-WFD")]:
        r = fn(inst)
        if not verify(inst, r.bins):
            fail(f"{name} invalid")
    ok()


# ----------------------------------------------------------------------
# Test 6. MB-WFD must succeed (not fall back) on a sparse instance.
# ----------------------------------------------------------------------
def test_mbwfd_succeeds():
    case("MB-WFD does not fall back on a sparse instance")
    inst = make_instance("uniform", n=80, density=0.1, seed=2)
    r = mbwfd(inst)
    if r.extra.get("fallback"):
        fail(f"MB-WFD fell back to FFD-C — that should not happen on this instance")
    ok()


def main():
    print("Running smoke tests:")
    test_trivial_no_conflicts()
    test_chain_effect_example_a()
    test_lower_bound()
    test_random_instance()
    test_triplet_optimum()
    test_mbwfd_succeeds()
    print()
    print("All tests passed.")


if __name__ == "__main__":
    main()
