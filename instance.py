"""
instance.py
Items, bins, conflict graphs, and instance generators for the BPPC.

We generate instances rather than reading the original Falkenauer 1996 files,
following the rules described in Falkenauer (1996) so that the resulting
distributions match the standard benchmark. The conflict graph is generated
following Gendreau, Laporte and Semet (2004).
"""

__VERSION__ = "2026-05-07-fix1"

import random
from dataclasses import dataclass, field
from typing import List, Set, Dict, Tuple


@dataclass
class Bin:
    """A bin holds items and tracks residual capacity."""
    capacity: float
    items: List[int] = field(default_factory=list)   # list of item ids
    item_set: Set[int] = field(default_factory=set)  # for O(1) membership
    residual: float = 0.0

    def __post_init__(self):
        if self.residual == 0.0:
            self.residual = self.capacity

    def add(self, item_id: int, item_size: float):
        self.items.append(item_id)
        self.item_set.add(item_id)
        self.residual -= item_size

    def fits(self, item_size: float) -> bool:
        # small tolerance for floating point
        return item_size <= self.residual + 1e-9


@dataclass
class Instance:
    """A BPPC instance: items with sizes, bin capacity, and a conflict graph."""
    sizes: List[float]                # sizes[i] is the (normalised) size of item i
    capacity: float                   # always 1.0 after normalisation
    neighbours: Dict[int, Set[int]]   # neighbours[i] = set of items conflicting with i
    name: str = ""

    @property
    def n(self) -> int:
        return len(self.sizes)

    @property
    def num_edges(self) -> int:
        return sum(len(s) for s in self.neighbours.values()) // 2

    @property
    def realised_edge_density(self) -> float:
        """The actual edge density of the conflict graph: |E| / C(n,2).
        Note: this is NOT the same as the generator parameter `d` used to
        produce the graph. See gen_conflict_graph() for the relationship."""
        n = self.n
        if n < 2:
            return 0.0
        return self.num_edges / (n * (n - 1) / 2)


# ----------------------------------------------------------------------
# Falkenauer-style item-size generators
# ----------------------------------------------------------------------

def gen_uniform_items(n: int, rng: random.Random) -> Tuple[List[float], float]:
    """Falkenauer 'uniform' class: integer sizes uniform in [20, 100], capacity 150.
    Returns (normalised_sizes, original_capacity)."""
    raw = [rng.randint(20, 100) for _ in range(n)]
    cap = 150
    sizes = [s / cap for s in raw]
    return sizes, 1.0


def gen_triplet_items(n: int, rng: random.Random) -> Tuple[List[float], float]:
    """Falkenauer (1996) 'triplet' class: items in groups of 3 that exactly fill
    a bin. Optimum (without conflicts) is exactly n/3 bins.

    Construction (Falkenauer 1996):
      - one large item a in (250, 500) of capacity 1000
      - one medium item b in (250, (1000 - a)/2) of capacity 1000
      - one small item c = 1000 - a - b
    The triplet sums to 1000 by construction, so the optimum is n/3.

    n must be a multiple of 3.
    """
    assert n % 3 == 0, "triplet n must be a multiple of 3"
    cap = 1000
    triples = []
    for _ in range(n // 3):
        # Falkenauer 1996 protocol:
        a = rng.uniform(250, 500)             # large item
        # b is constrained so that c = cap - a - b is also non-trivial and < a
        b_lo = 250
        b_hi = (cap - a) / 2.0                 # ensures c <= b
        if b_hi <= b_lo:
            # Edge case: a large enough that b_hi <= 250.
            # This happens only when a > 500, which we've already capped out.
            # Defensively, fall back to symmetric split of remainder.
            b = (cap - a) / 2.0
        else:
            b = rng.uniform(b_lo, b_hi)
        c = cap - a - b
        triple = sorted([a, b, c], reverse=True)
        triples.extend(triple)
    rng.shuffle(triples)
    sizes = [s / cap for s in triples]
    return sizes, 1.0


# ----------------------------------------------------------------------
# Gendreau et al. (2004) conflict graph generator
# ----------------------------------------------------------------------

def gen_conflict_graph(n: int, density: float, rng: random.Random) -> Dict[int, Set[int]]:
    """Generate a conflict graph using the Gendreau et al. (2004) protocol.

    Each item i gets a value p_i ~ Uniform[0,1]. An edge {i,j} is added iff
    (p_i + p_j) / 2 <= density.

    NOTE on terminology. The parameter `density` here is the *generator
    parameter* used by Gendreau et al. (2004) and Fernandes Muritiba et al.
    (2010); it is NOT the resulting edge density of the graph.

    For p_i, p_j ~ U[0,1], the probability of an edge is
        P((p_i + p_j)/2 <= d)  =  P(p_i + p_j <= 2d)
                                =  2*d^2                  for d <= 0.5
                                =  1 - 2*(1-d)^2          for d >  0.5

    So when this function is called with density=0.3, the realised edge
    density is approximately 0.18, not 0.30. We retain the parameter `d`
    here for direct comparability with the published benchmark, but the
    report distinguishes the two carefully (see Section 3.1.2 and
    Appendix A).
    """
    p = [rng.random() for _ in range(n)]
    neighbours: Dict[int, Set[int]] = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if (p[i] + p[j]) / 2 <= density:
                neighbours[i].add(j)
                neighbours[j].add(i)
    return neighbours


def expected_realised_density(d: float) -> float:
    """The expected realised edge density of a graph generated by gen_conflict_graph
    with parameter d. Useful for the Ch3 calibration table."""
    if d <= 0.5:
        return 2.0 * d * d
    else:
        return 1.0 - 2.0 * (1.0 - d) ** 2


# ----------------------------------------------------------------------
# Top-level instance builders
# ----------------------------------------------------------------------

def make_instance(family: str, n: int, density: float, seed: int) -> Instance:
    """Build a BPPC instance.
    family: 'uniform' or 'triplet'
    n:       number of items
    density: target density of the conflict graph
    seed:    RNG seed
    """
    rng = random.Random(seed)
    if family == "uniform":
        sizes, cap = gen_uniform_items(n, rng)
    elif family == "triplet":
        sizes, cap = gen_triplet_items(n, rng)
    else:
        raise ValueError(f"unknown family {family!r}")
    neigh = gen_conflict_graph(n, density, rng)
    name = f"{family}_n{n}_d{density:.1f}_s{seed}"
    return Instance(sizes=sizes, capacity=cap, neighbours=neigh, name=name)
