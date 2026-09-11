# BPPC experiments: final reproducibility package

This package contains the Python 3.11 code and final data used in the MSc
dissertation. It implements FFD-C, BFD-C, MB-WFD-pure and MB-WFD-capped.
H2--H6 and surrogate-weight methods are discussed as literature in the
dissertation but are not implemented here.

## Requirements and quick start

- Python 3.11
- Install the two packages required for the figure-generation scripts:

```text
python -m pip install -r requirements.txt
```

The core algorithms and validation scripts otherwise use the Python standard
library. Run the commands in the "Reproduction commands" section from the
repository root.

## Final experimental evidence

- `results_medium_final_20260731.csv`: 300 Gendreau-style benchmark instances
  and 1,200 heuristic runs.
- `timing_final_20260731.csv`: 240 timing runs.
- `robustness_er_final_20260731.csv`: 100 independent-edge
  Erdős--Rényi sensitivity instances and 400 heuristic runs.
- `analysis_final_20260830.json`, `timing_stats_final_20260731.json`, and
  `robustness_er_summary_20260731.json`: derived summaries.
- `figures_final_20260731/`: the five final figures used in Chapter 4.

The final rerun reproduced every non-timing field in the archived main CSV.
All successful packings passed capacity and conflict checks, no successful
bin count was below the combined lower bound, and MB-WFD-capped never used
more bins than FFD-C. Three MB-WFD-pure attempts exhausted the retry budget;
they remain explicitly marked as failures and are excluded from mean-gap
calculations.

## Main findings

The strongest result is on conflict-free Falkenauer triplet instances.
MB-WFD-capped wins all 15 instances and reduces the mean gap from roughly
14--15% for FFD-C/BFD-C to roughly 6--9%. The exact paired sign-test
p-value is 6.1035e-05. This effect is driven by item-size matching, not by
dense conflicts.

MB-WFD-capped offers no solution-quality benefit in the dense-conflict
regime because its FFD-C safety cap falls back on every tested main instance
from d = 0.6 onward. The uncapped variant is unreliable in the medium-density
region, so the cap is essential.

The independent-edge Erdős--Rényi sensitivity experiment confirms that the
low- and medium-density triplet advantage is not solely an artefact of the
Gendreau threshold-graph generator. It also shows that the detailed
high-density gap curve depends on the conflict-graph family.

Absolute timing figures were regenerated on the final machine. At n = 2000,
the observed uniform-instance means were approximately 76.5 ms for FFD-C,
100.1 ms for BFD-C, 18.19 s for MB-WFD-pure, and 1.37 s for MB-WFD-capped.
These Python timings should not be compared directly with optimized C/C++
implementations.

## Files

| File | Purpose |
|---|---|
| `instance.py` | Item, bin and conflict-graph structures; benchmark generators |
| `heuristics.py` | Four reported heuristic labels and feasibility verifier |
| `lower_bound.py` | Capacity plus greedy-clique lower bound |
| `experiments.py` | Main benchmark driver |
| `timing_experiment.py` | Separate scaling experiment |
| `robustness_er_experiment.py` | Independent-edge random-graph sensitivity |
| `verify_install.py` | Installation and module check |
| `test_smoke.py` | Small deterministic smoke tests |
| `sanity_check.py` | Invariant and protocol checks |
| `analyze_results.py` | Main-result analysis |
| `build_final_figures.py` | Final tables, summaries and figures |

## Reproduction commands

Run from this directory:

```text
python verify_install.py
python test_smoke.py
python sanity_check.py
python experiments.py --scale medium --base-seed 0 --out results_medium_final.csv
python analyze_results.py results_medium_final_20260731.csv results_medium_final.csv analysis_rerun.json
python timing_experiment.py --base-seed 0 --out timing_final.csv
python build_final_figures.py results_medium_final.csv timing_final.csv figures_rerun timing_stats_rerun.json
python robustness_er_experiment.py --base-seed 0 --out robustness_er_final.csv --summary robustness_er_summary.json --figure figure_4_5_er_sensitivity.png
```

`analysis_rerun.json` contains the means and sample standard deviations used
in Tables 4.1--4.3, the fallback and paired-test summaries, and the expected
and empirical edge-density values used in Table 5.1.  This keeps the derived
table entries traceable to the archived CSV rather than to an undocumented
manual calculation.

All instance generation is deterministic for a fixed base seed. Runtime is
intentionally excluded from byte-for-byte reproducibility claims because it
depends on the machine and system load.

## Scope and scholarly limitation

The package does not claim a numerical per-instance reproduction of the
published Gendreau et al. or Fernandes Muritiba et al. results. Their exact
instance files/seeds were not matched in this project. The dissertation
therefore compares qualitative curve features and reports exact optimum
gaps only for the conflict-free triplet construction, where the optimum is
known as n/3.
