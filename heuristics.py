"""
heuristics.py
The three heuristics under study:
  - FFD-C  (First Fit Decreasing with Conflicts)
  - BFD-C  (Best Fit Decreasing with Conflicts)
  - MB-WFD (Multi-Bin Worst Fit Decreasing), in two variants:
      * mbwfd_pure   — no FFD-C safety net; fails honestly on exhaustion
      * mbwfd_capped — capped above by FFD-C; falls back to FFD-C on failure

Each heuristic takes an Instance and returns a Result with the bin assignment
and a timing record.
"""

__VERSION__ = "2026-05-07-fix1"

import time
from dataclasses import dataclass
from typing import List, Optional
from instance import Instance, Bin
from lower_bound import combined_lower_bound


@dataclass
class Result:
    name: str           # heuristic name
    bins_used: int      # number of bins in the solution
    bins: List[Bin]     # the bins themselves
    runtime_ms: float   # wall-clock time in milliseconds
    extra: dict         # algorithm-specific extra info (e.g. retries)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _conflicts(bin_obj: Bin, item: int, neighbours) -> bool:
    """True iff `item` conflicts with any item already in bin_obj.
    Iterate over the smaller of (bin items, item's neighbours) for speed."""
    nbrs = neighbours[item]
    if len(bin_obj.item_set) <= len(nbrs):
        for j in bin_obj.item_set:
            if j in nbrs:
                return True
        return False
    else:
        for j in nbrs:
            if j in bin_obj.item_set:
                return True
        return False


def _sorted_indices_by_size_desc(sizes):
    """Return item ids sorted by non-increasing size, with id as tie-break."""
    return sorted(range(len(sizes)), key=lambda i: (-sizes[i], i))


# ----------------------------------------------------------------------
# FFD-C
# ----------------------------------------------------------------------

def ffdc(inst: Instance) -> Result:
    """First Fit Decreasing with Conflicts."""
    t0 = time.perf_counter()
    order = _sorted_indices_by_size_desc(inst.sizes)
    bins: List[Bin] = []
    for i in order:
        s = inst.sizes[i]
        placed = False
        for b in bins:                                     # bins in opening order
            if b.fits(s) and not _conflicts(b, i, inst.neighbours):
                b.add(i, s)
                placed = True
                break
        if not placed:
            new_b = Bin(capacity=inst.capacity)
            new_b.add(i, s)
            bins.append(new_b)
    t1 = time.perf_counter()
    return Result(name="FFD-C", bins_used=len(bins), bins=bins,
                  runtime_ms=(t1 - t0) * 1000.0, extra={})


# ----------------------------------------------------------------------
# BFD-C
# ----------------------------------------------------------------------

def bfdc(inst: Instance) -> Result:
    """Best Fit Decreasing with Conflicts."""
    t0 = time.perf_counter()
    order = _sorted_indices_by_size_desc(inst.sizes)
    bins: List[Bin] = []
    for i in order:
        s = inst.sizes[i]
        # find feasible bin with smallest residual
        best: Optional[Bin] = None
        best_residual = float("inf")
        for b in bins:
            if b.fits(s) and b.residual < best_residual and not _conflicts(b, i, inst.neighbours):
                best = b
                best_residual = b.residual
        if best is not None:
            best.add(i, s)
        else:
            new_b = Bin(capacity=inst.capacity)
            new_b.add(i, s)
            bins.append(new_b)
    t1 = time.perf_counter()
    return Result(name="BFD-C", bins_used=len(bins), bins=bins,
                  runtime_ms=(t1 - t0) * 1000.0, extra={})


# ----------------------------------------------------------------------
# MB-WFD
# ----------------------------------------------------------------------

def _try_mbwfd_pass(inst: Instance, m: int, order) -> Optional[List[Bin]]:
    """One inner pass of MB-WFD with m preactivated bins.
    Returns the bins on success, or None on failure (some item could not be placed)."""
    bins = [Bin(capacity=inst.capacity) for _ in range(m)]
    for i in order:
        s = inst.sizes[i]
        # find feasible bin with LARGEST residual ("worst fit")
        best: Optional[Bin] = None
        best_residual = -1.0
        for b in bins:
            if b.fits(s) and b.residual > best_residual and not _conflicts(b, i, inst.neighbours):
                best = b
                best_residual = b.residual
        if best is None:
            return None
        best.add(i, s)
    return bins


# ----------------------------------------------------------------------
# MB-WFD-pure: no FFD-C safety net.
#
# This is the "isolated" version for studying the multi-bin idea on its own.
# It is allowed to fail: if no m in [LB, LB + max_extra_retries] yields a
# successful pass, the function returns Result with bins_used = -1 and
# extra["status"] = "failed". The caller MUST check for this and decide
# what to do; nothing falls back silently.
# ----------------------------------------------------------------------

def mbwfd_pure(inst: Instance, max_extra_retries: int = 200) -> Result:
    """Pure MB-WFD: try m = LB, LB+1, ..., LB+max_extra_retries.
    Return on first success. If all retries fail, return Result with
    bins_used = -1 and extra["status"] = "failed". DOES NOT fall back to
    FFD-C; that is the whole point of this version.

    Use this version to study MB-WFD's intrinsic behaviour, including the
    non-monotonicity proved by Mommessin et al. (2025): for some instances
    a pass with m bins can succeed while a pass with m+k bins fails.
    """
    t0 = time.perf_counter()
    order = _sorted_indices_by_size_desc(inst.sizes)
    m_start = combined_lower_bound(inst)

    final_bins: Optional[List[Bin]] = None
    retries_used = 0
    for k in range(max_extra_retries + 1):
        m = m_start + k
        retries_used = k
        bins = _try_mbwfd_pass(inst, m, order)
        if bins is not None:
            final_bins = [b for b in bins if b.items]
            break
    t1 = time.perf_counter()

    if final_bins is None:
        # Honest failure. Caller must handle.
        return Result(name="MB-WFD-pure", bins_used=-1, bins=[],
                      runtime_ms=(t1 - t0) * 1000.0,
                      extra={"status": "failed",
                             "retries": retries_used,
                             "m_start": m_start,
                             "max_extra_retries": max_extra_retries})

    return Result(name="MB-WFD-pure", bins_used=len(final_bins), bins=final_bins,
                  runtime_ms=(t1 - t0) * 1000.0,
                  extra={"status": "success",
                         "retries": retries_used,
                         "m_start": m_start})


# ----------------------------------------------------------------------
# MB-WFD-capped: MB-WFD with FFD-C used as both an upper bound on m and
# as a fallback when the multi-bin pass fails. This is the "deployed"
# hybrid; it is what a practitioner would actually run.
#
# Reported separately from MB-WFD-pure so the report can clearly say:
#   * MB-WFD-pure isolates the multi-bin idea.
#   * MB-WFD-capped is the hybrid one would use in practice.
# Conflating the two would be misleading.
# ----------------------------------------------------------------------

def mbwfd_capped(inst: Instance) -> Result:
    """MB-WFD bounded above by FFD-C.

    Step 1: run FFD-C to obtain an upper bound U on the optimum.
    Step 2: try m = LB, LB+1, ..., U inclusive. (BUG-FIX vs earlier draft:
            the upper end of the range used to be `m < U`, which meant that
            on instances with LB == U the multi-bin pass was never attempted
            and the result was silently FFD-C wearing an MB-WFD label.
            We now allow m == U so that MB-WFD is genuinely tried at least
            once on every instance.)
    Step 3: return the first successful pass. If none succeeds, return
            FFD-C's solution and flag used_ffdc_fallback = True.
    """
    t0 = time.perf_counter()
    order = _sorted_indices_by_size_desc(inst.sizes)
    m_start = combined_lower_bound(inst)

    ffdc_result = ffdc(inst)
    m_cap = ffdc_result.bins_used  # upper bound U on optimum

    final_bins: Optional[List[Bin]] = None
    retries_used = 0
    used_ffdc_fallback = False

    # NOTE: we iterate m in [m_start, m_cap] INCLUSIVE.
    # range stop is m_cap + 1 so that m == m_cap is tried.
    for m in range(m_start, m_cap + 1):
        retries_used = m - m_start
        bins = _try_mbwfd_pass(inst, m, order)
        if bins is not None:
            final_bins = [b for b in bins if b.items]
            break

    if final_bins is None:
        # Every m in [LB, U] failed: fall back to the FFD-C solution we
        # already computed. This is honest because U is by definition
        # achievable by FFD-C.
        final_bins = ffdc_result.bins
        used_ffdc_fallback = True
        retries_used = m_cap - m_start + 1   # number of failed MB-WFD passes

    t1 = time.perf_counter()

    return Result(name="MB-WFD-capped", bins_used=len(final_bins), bins=final_bins,
                  runtime_ms=(t1 - t0) * 1000.0,
                  extra={"status": "success",
                         "retries": retries_used,
                         "m_start": m_start,
                         "m_cap": m_cap,
                         "used_ffdc_fallback": used_ffdc_fallback})


# Backwards-compat alias for any older code that imported `mbwfd`.
# Marked deprecated in the docstring; experiments.py now uses the explicit
# names mbwfd_pure / mbwfd_capped directly.
def mbwfd(inst: Instance, max_extra_retries: int = 50,
          ffdc_upper_bound: bool = True) -> Result:
    """DEPRECATED. Use mbwfd_pure() or mbwfd_capped() instead.

    This shim preserves the old call site:
      mbwfd(inst, ffdc_upper_bound=True)  -> mbwfd_capped(inst)
      mbwfd(inst, ffdc_upper_bound=False) -> mbwfd_pure(inst, max_extra_retries)
    """
    if ffdc_upper_bound:
        return mbwfd_capped(inst)
    return mbwfd_pure(inst, max_extra_retries=max_extra_retries)


# ----------------------------------------------------------------------
# Sanity check: a solution must satisfy capacity and conflict constraints.
# ----------------------------------------------------------------------

def verify(inst: Instance, bins: List[Bin]) -> bool:
    """Check that a bin assignment is feasible: capacity respected, no conflicts,
    every item placed exactly once."""
    seen = set()
    for b in bins:
        # capacity
        total = sum(inst.sizes[i] for i in b.items)
        if total > inst.capacity + 1e-9:
            return False
        # no duplicates and no conflicts
        for i in b.items:
            if i in seen:
                return False
            seen.add(i)
            for j in b.items:
                if j != i and j in inst.neighbours[i]:
                    return False
    # every item present exactly once
    return seen == set(range(inst.n))
