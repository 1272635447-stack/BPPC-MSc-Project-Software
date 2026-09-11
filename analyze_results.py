from __future__ import annotations

import csv
import json
import math
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path


NON_TIMING_FIELDS = [
    "family",
    "n",
    "density",
    "realised_edge_density",
    "seed",
    "heuristic",
    "bins_used",
    "lb",
    "gap",
    "retries",
    "status",
    "used_ffdc_fallback",
]


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["n"] = int(row["n"])
        row["density"] = float(row["density"])
        row["realised_edge_density"] = float(row["realised_edge_density"])
        row["seed"] = int(row["seed"])
        row["bins_used"] = int(row["bins_used"])
        row["lb"] = int(row["lb"])
        row["gap"] = float(row["gap"])
        row["runtime_ms"] = float(row["runtime_ms"])
        row["retries"] = int(row["retries"]) if row["retries"] else None
        if row["used_ffdc_fallback"] == "True":
            row["used_ffdc_fallback"] = True
        elif row["used_ffdc_fallback"] == "False":
            row["used_ffdc_fallback"] = False
        else:
            row["used_ffdc_fallback"] = None
    return rows


def key(row: dict) -> tuple:
    return row["family"], row["n"], row["density"], row["seed"], row["heuristic"]


def canonical(row: dict) -> tuple:
    values = []
    for field in NON_TIMING_FIELDS:
        value = row[field]
        if isinstance(value, float) and math.isnan(value):
            values.append("NaN")
        elif isinstance(value, float):
            values.append(round(value, 14))
        else:
            values.append(value)
    return tuple(values)


def mean_sd(values: list[float]) -> tuple[float, float]:
    return stats.mean(values), stats.stdev(values) if len(values) > 1 else 0.0


def main() -> None:
    if len(sys.argv) < 4:
        raise SystemExit("usage: analyze_results.py ORIGINAL RERUN OUT_JSON")
    original_path, rerun_path, out_path = map(Path, sys.argv[1:4])
    original = read_rows(original_path)
    rerun = read_rows(rerun_path)
    old_map = {key(row): canonical(row) for row in original}
    new_map = {key(row): canonical(row) for row in rerun}
    mismatches = []
    for k in sorted(set(old_map) | set(new_map)):
        if old_map.get(k) != new_map.get(k):
            mismatches.append({"key": k, "original": old_map.get(k), "rerun": new_map.get(k)})

    by_instance: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for row in rerun:
        ikey = row["family"], row["n"], row["density"], row["seed"]
        by_instance[ikey][row["heuristic"]] = row

    validation = {
        "row_count": len(rerun),
        "instance_count": len(by_instance),
        "all_four_heuristics": all(len(v) == 4 for v in by_instance.values()),
        "failed_rows": sum(row["status"] != "success" for row in rerun),
        "bins_below_lb": sum(row["bins_used"] >= 0 and row["bins_used"] < row["lb"] for row in rerun),
        "capped_above_ffdc": 0,
    }
    for heuristics in by_instance.values():
        if heuristics["MB-WFD-capped"]["bins_used"] > heuristics["FFD-C"]["bins_used"]:
            validation["capped_above_ffdc"] += 1

    triplet_d0: dict[int, dict] = {}
    paired_differences = []
    for n in (60, 120, 249):
        instances = [
            v for k, v in by_instance.items()
            if k[0] == "triplet" and k[1] == n and k[2] == 0.0
        ]
        row = {}
        for heuristic in ("FFD-C", "BFD-C", "MB-WFD-capped"):
            gaps = [item[heuristic]["gap"] for item in instances]
            row[heuristic] = {
                "mean_gap": stats.mean(gaps),
                "sd_gap": stats.stdev(gaps),
                "mean_bins": stats.mean(item[heuristic]["bins_used"] for item in instances),
            }
        row["wins_over_both"] = sum(
            item["MB-WFD-capped"]["bins_used"]
            < min(item["FFD-C"]["bins_used"], item["BFD-C"]["bins_used"])
            for item in instances
        )
        triplet_d0[n] = row
        paired_differences.extend(
            item["FFD-C"]["bins_used"] - item["MB-WFD-capped"]["bins_used"]
            for item in instances
        )
    nonzero_diffs = [d for d in paired_differences if d != 0]
    positive_diffs = sum(d > 0 for d in nonzero_diffs)
    two_sided_sign_p = min(1.0, 2.0 / (2 ** len(nonzero_diffs))) if positive_diffs == len(nonzero_diffs) else None

    family_density: dict[str, dict[str, dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))
    for family in ("uniform", "triplet"):
        for density in [i / 10 for i in range(10)]:
            for heuristic in ("FFD-C", "BFD-C", "MB-WFD-pure", "MB-WFD-capped"):
                values = [
                    row["gap"] for row in rerun
                    if row["family"] == family
                    and row["density"] == density
                    and row["heuristic"] == heuristic
                    and not math.isnan(row["gap"])
                ]
                mean, sd = mean_sd(values)
                family_density[family][f"{density:.1f}"][heuristic] = {
                    "mean_gap": mean,
                    "sd_gap": sd,
                    "n": len(values),
                }
            capped = [
                row for row in rerun
                if row["family"] == family
                and row["density"] == density
                and row["heuristic"] == "MB-WFD-capped"
            ]
            family_density[family][f"{density:.1f}"]["fallback_rate"] = stats.mean(
                float(row["used_ffdc_fallback"]) for row in capped
            )

    pooled_density = {}
    for density in [i / 10 for i in range(10)]:
        ffd = [
            row for row in rerun
            if row["density"] == density and row["heuristic"] == "FFD-C"
        ]
        capped = [
            row for row in rerun
            if row["density"] == density and row["heuristic"] == "MB-WFD-capped"
        ]
        pooled_density[f"{density:.1f}"] = {
            "ffdc_mean_gap": stats.mean(row["gap"] for row in ffd),
            "ffdc_sd_gap": stats.stdev(row["gap"] for row in ffd),
            "capped_mean_gap": stats.mean(row["gap"] for row in capped),
            "capped_sd_gap": stats.stdev(row["gap"] for row in capped),
            "capped_wins": sum(c["bins_used"] < f["bins_used"] for c, f in zip(capped, ffd)),
            "capped_ties": sum(c["bins_used"] == f["bins_used"] for c, f in zip(capped, ffd)),
            "fallback_rate": stats.mean(float(row["used_ffdc_fallback"]) for row in capped),
        }

    # Table 5.1 uses one realised edge-density value per generated graph.  Each
    # graph appears four times in the result CSV (once per heuristic), so read
    # the value from the instance-level dictionary rather than averaging all
    # algorithm rows.  The expected density is the analytical value of the
    # Gendreau--Laporte--Semet threshold rule used by instance.py.
    edge_density_validation = {}
    for density in [i / 10 for i in range(10)]:
        realised = [
            next(iter(heuristics.values()))["realised_edge_density"]
            for instance_key, heuristics in by_instance.items()
            if instance_key[2] == density
        ]
        expected = 2.0 * density * density if density <= 0.5 else 1.0 - 2.0 * (1.0 - density) ** 2
        empirical_mean = stats.mean(realised)
        edge_density_validation[f"{density:.1f}"] = {
            "expected": expected,
            "empirical_mean": empirical_mean,
            "empirical_sd": stats.stdev(realised),
            "absolute_error": abs(empirical_mean - expected),
            "n_graphs": len(realised),
        }

    payload = {
        "comparison": {
            "original_rows": len(original),
            "rerun_rows": len(rerun),
            "non_timing_mismatch_count": len(mismatches),
            "first_mismatches": mismatches[:10],
        },
        "validation": validation,
        "triplet_d0": triplet_d0,
        "paired_test": {
            "differences_ffdc_minus_capped": paired_differences,
            "nonzero_count": len(nonzero_diffs),
            "positive_count": positive_diffs,
            "median_bin_reduction": stats.median(paired_differences),
            "mean_gap_reduction_percentage_points": 100
            * stats.mean(
                item["FFD-C"]["gap"] - item["MB-WFD-capped"]["gap"]
                for k, item in by_instance.items()
                if k[0] == "triplet" and k[2] == 0.0
            ),
            "exact_two_sided_sign_test_p": two_sided_sign_p,
        },
        "family_density": family_density,
        "pooled_density": pooled_density,
        "edge_density_validation": edge_density_validation,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload["comparison"], indent=2))
    print(json.dumps(payload["validation"], indent=2))
    print(json.dumps(payload["paired_test"], indent=2))


if __name__ == "__main__":
    main()
