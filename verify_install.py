"""
verify_install.py
A zero-dependency preflight check. Run this first, before sanity_check.py
or experiments.py. It tells you whether all 5 files are present, are at
the same version, and contain the symbols expected of the new code.

Usage:
    python verify_install.py

If you see "INSTALL OK", you can proceed to:
    python sanity_check.py
    python experiments.py --scale sanity --base-seed 0 --out sanity_results.csv

If you see "INSTALL FAILED", this script will tell you exactly which file
is wrong and what to do.
"""

import importlib
import os
import sys

EXPECTED_VERSION = "2026-05-07-fix1"

# (filename, list of module-level names that MUST exist after import)
EXPECTED_FILES = [
    ("instance.py",      "instance",      ["make_instance", "expected_realised_density",
                                            "gen_uniform_items", "gen_triplet_items",
                                            "gen_conflict_graph", "Instance", "Bin"]),
    ("heuristics.py",    "heuristics",    ["ffdc", "bfdc", "mbwfd_pure", "mbwfd_capped",
                                            "verify", "Result"]),
    ("lower_bound.py",   "lower_bound",   ["combined_lower_bound", "continuous_lb",
                                            "greedy_max_clique"]),
    ("experiments.py",   "experiments",   ["make_seed", "run_scale", "SCALES"]),
    ("sanity_check.py",  "sanity_check",  ["check_one_instance", "CELLS"]),
]


def fail(msg: str):
    print(f"  FAIL: {msg}")


def ok(msg: str):
    print(f"  ok:   {msg}")


def main():
    print("=" * 70)
    print(f"BPPC repo install check (expected __VERSION__ = {EXPECTED_VERSION!r})")
    print("=" * 70)

    failures = []
    here = os.path.dirname(os.path.abspath(__file__)) or "."

    # 1. Files exist
    print("\n[1/4] Checking that all 5 files are present in", here)
    for fname, _, _ in EXPECTED_FILES:
        path = os.path.join(here, fname)
        if not os.path.isfile(path):
            failures.append(f"missing file: {fname}")
            fail(f"{fname} not found in {here}")
        else:
            ok(f"{fname} present")

    if failures:
        print("\nINSTALL FAILED: missing file(s).")
        print("Make sure all 5 files (instance.py, heuristics.py, lower_bound.py,")
        print("experiments.py, sanity_check.py) are in the SAME directory.")
        sys.exit(1)

    # 2. Each file imports cleanly
    print("\n[2/4] Importing each module")
    # Make sure we're importing from the current directory, not somewhere else
    if here not in sys.path:
        sys.path.insert(0, here)
    # Drop cached imports so we definitely re-read from disk
    for _, modname, _ in EXPECTED_FILES:
        if modname in sys.modules:
            del sys.modules[modname]
    modules = {}
    for fname, modname, _ in EXPECTED_FILES:
        try:
            modules[modname] = importlib.import_module(modname)
            ok(f"{modname} imports cleanly")
        except Exception as e:
            failures.append(f"{fname}: {type(e).__name__}: {e}")
            fail(f"{fname}: {type(e).__name__}: {e}")

    if failures:
        print("\nINSTALL FAILED: import error(s).")
        print("Most likely cause: at least one file is the OLD version. Re-copy")
        print("ALL 5 files from the latest set, into the same directory.")
        sys.exit(1)

    # 3. Each file has the expected version stamp
    print(f"\n[3/4] Checking __VERSION__ == {EXPECTED_VERSION!r} on every file")
    bad_versions = []
    for fname, modname, _ in EXPECTED_FILES:
        v = getattr(modules[modname], "__VERSION__", None)
        if v == EXPECTED_VERSION:
            ok(f"{fname:20s} __VERSION__ = {v!r}")
        else:
            failures.append(f"{fname}: __VERSION__ is {v!r}, expected {EXPECTED_VERSION!r}")
            bad_versions.append(fname)
            fail(f"{fname:20s} __VERSION__ = {v!r}  <-- WRONG")

    if bad_versions:
        print("\nINSTALL FAILED: version mismatch.")
        print("These files are not at the latest version:")
        for f in bad_versions:
            print(f"  - {f}")
        print("Re-copy them from the latest patch.")
        sys.exit(1)

    # 4. Each file exports the expected names
    print("\n[4/4] Checking that the expected symbols exist in each module")
    for fname, modname, expected_names in EXPECTED_FILES:
        mod = modules[modname]
        for name in expected_names:
            if hasattr(mod, name):
                ok(f"{modname}.{name}")
            else:
                failures.append(f"{fname}: missing {name}")
                fail(f"{modname}.{name}  <-- MISSING")

    print()
    print("=" * 70)
    if failures:
        print(f"INSTALL FAILED ({len(failures)} problem(s) above).")
        print()
        print("Fix:")
        print("  1. Make sure ALL 5 files are present in the same directory.")
        print("  2. Make sure every file is the LATEST patch version.")
        print("  3. Re-run this script until it prints INSTALL OK.")
        sys.exit(1)
    else:
        print("INSTALL OK.")
        print()
        print("Next steps:")
        print("  python sanity_check.py")
        print("  python experiments.py --scale sanity --base-seed 0 --out sanity_results.csv")
        sys.exit(0)


if __name__ == "__main__":
    main()
