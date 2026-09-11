"""
lower_bound.py
Lower bounds on the BPPC optimum.

We use the combined lower bound from Chapter 3 of the report:

    LB(I) = max{ ceil( sum of item sizes / C ) ,  omega_hat(G) }

where C is bin capacity. Instances are normalised to C = 1 before this module
is called, so the implemented capacity term is ceil(sum of normalised sizes).
omega_hat(G) is the size of a clique found by Johnson's (1974) greedy
procedure; it is not claimed to be the maximum clique.

Computing the true maximum clique is NP-hard. The greedy clique may be smaller,
but every clique found still supplies a valid lower bound on the chromatic
number and therefore on the BPPC optimum.
"""

__VERSION__ = "2026-05-07-fix1"

import math
from typing import List
from instance import Instance


def continuous_lb(inst: Instance) -> int:
    """Capacity bound after normalisation to C = 1: ceil(sum of sizes)."""
    return math.ceil(sum(inst.sizes) - 1e-9)  # tolerance to avoid 3.0 -> 3 vs 3.0000001 -> 4


def greedy_max_clique(inst: Instance) -> int:
    """Johnson (1974) greedy maximum clique size.

    Initialise the clique with a vertex of maximum degree. Then iteratively
    add the highest-degree vertex that is connected to every vertex already
    in the clique, until no such vertex remains.
    """
    n = inst.n
    if n == 0:
        return 0
    degree = {i: len(inst.neighbours[i]) for i in range(n)}
    # start with the highest-degree vertex
    start = max(range(n), key=lambda i: (degree[i], -i))
    clique = {start}
    candidates = set(inst.neighbours[start])
    while candidates:
        # pick the candidate with the highest degree (in the original graph)
        v = max(candidates, key=lambda i: (degree[i], -i))
        clique.add(v)
        # candidates must remain neighbours of every vertex in the clique
        candidates = candidates.intersection(inst.neighbours[v])
        candidates.discard(v)
    return len(clique)


def combined_lower_bound(inst: Instance) -> int:
    """Combined lower bound: max(continuous capacity bound, greedy clique bound)."""
    return max(continuous_lb(inst), greedy_max_clique(inst))
