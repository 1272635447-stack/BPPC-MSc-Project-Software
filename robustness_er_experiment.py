"""Sensitivity experiment using arbitrary Erdos-Renyi conflict graphs.

The main dissertation experiment follows Gendreau et al. (2004), whose
threshold rule creates structured threshold graphs.  This script keeps the
Falkenauer-style item generators but replaces the conflict graph with G(n,q),
where every edge is sampled independently.  For comparability, q is set equal
to the expected realised density of the corresponding Gendreau parameter d.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

from build_final_figures import COLORS, canvas, draw_panel, legend
from heuristics import bfdc, ffdc, mbwfd_capped, mbwfd_pure, verify
from instance import (
    Instance,
    expected_realised_density,
    gen_triplet_items,
    gen_uniform_items,
)
from lower_bound import combined_lower_bound


D_VALUES = [i / 10 for i in range(10)]
CELLS = (("uniform", 250), ("triplet", 249))
REPS = 5


def er_graph(n: int, q: float, rng: random.Random) -> dict[int, set[int]]:
    neighbours = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < q:
                neighbours[i].add(j)
                neighbours[j].add(i)
    return neighbours


def make_er_instance(family: str, n: int, d: float, seed: int) -> Instance:
    rng = random.Random(seed)
    if family == "uniform":
        sizes, capacity = gen_uniform_items(n, rng)
    else:
        sizes, capacity = gen_triplet_items(n, rng)
    q = expected_realised_density(d)
    neighbours = er_graph(n, q, rng)
    return Instance(
        sizes=sizes,
        capacity=capacity,
        neighbours=neighbours,
        name=f"er_{family}_n{n}_d{d:.1f}_s{seed}",
    )


def run_one(instance: Instance, fn, name: str):
    result = fn(instance)
    if result.bins_used != -1 and not verify(instance, result.bins):
        raise RuntimeError(f"{name} produced an infeasible solution on {instance.name}")
    return result


def aggregate(rows: list[dict]) -> dict:
    groups: dict[tuple[str, float, str], list[float]] = defaultdict(list)
    wins: dict[tuple[str, float], int] = defaultdict(int)
    fallbacks: dict[tuple[str, float], list[int]] = defaultdict(list)
    instances: dict[tuple[str, float, int], dict[str, int]] = defaultdict(dict)
    realised: dict[tuple[str, float], list[float]] = defaultdict(list)

    for row in rows:
        key = (row["family"], row["d"], row["heuristic"])
        if not math.isnan(row["gap"]):
            groups[key].append(row["gap"])
        instance_key = (row["family"], row["d"], row["seed"])
        instances[instance_key][row["heuristic"]] = row["bins_used"]
        if row["heuristic"] == "FFD-C":
            realised[(row["family"], row["d"])].append(row["realised_edge_density"])
        if row["heuristic"] == "MB-WFD-capped":
            fallbacks[(row["family"], row["d"])].append(
                int(bool(row["used_ffdc_fallback"]))
            )

    for (family, d, _seed), values in instances.items():
        if values["MB-WFD-capped"] < values["FFD-C"]:
            wins[(family, d)] += 1

    summary = {"cells": {}, "validation": {}}
    for family, _n in CELLS:
        summary["cells"][family] = {}
        for d in D_VALUES:
            cell = {
                "target_edge_probability": expected_realised_density(d),
                "mean_realised_density": statistics.mean(realised[(family, d)]),
                "capped_wins_out_of_5": wins[(family, d)],
                "capped_fallback_rate": statistics.mean(fallbacks[(family, d)]),
            }
            for heuristic in ("FFD-C", "BFD-C", "MB-WFD-pure", "MB-WFD-capped"):
                values = groups[(family, d, heuristic)]
                cell[heuristic] = {
                    "mean_gap": statistics.mean(values) if values else None,
                    "sd_gap": statistics.stdev(values) if len(values) > 1 else 0.0,
                    "successful_runs": len(values),
                }
            summary["cells"][family][f"{d:.1f}"] = cell

    summary["validation"] = {
        "rows": len(rows),
        "instances": len(instances),
        "failed_pure_runs": sum(
            row["status"] == "failed" for row in rows if row["heuristic"] == "MB-WFD-pure"
        ),
        "bins_below_lb": sum(
            row["bins_used"] != -1 and row["bins_used"] < row["lb"] for row in rows
        ),
        "capped_above_ffdc": sum(
            values["MB-WFD-capped"] > values["FFD-C"] for values in instances.values()
        ),
    }
    return summary


def make_figure(summary: dict, path: Path) -> None:
    names = ["FFD-C", "BFD-C", "MB-WFD-capped"]
    image, draw = canvas(3000, 1500)
    legend(draw, 65, names, image.width)
    for index, (family, n) in enumerate(CELLS):
        series = []
        for heuristic in names:
            series.append(
                {
                    "name": heuristic,
                    "color": COLORS[heuristic],
                    "x": D_VALUES,
                    "y": [
                        100
                        * summary["cells"][family][f"{d:.1f}"][heuristic]["mean_gap"]
                        for d in D_VALUES
                    ],
                }
            )
        box = (50 + index * 1475, 90, 1500 + index * 1475, 1450)
        draw_panel(
            draw,
            box,
            f"{family.capitalize()}, n = {n}",
            series,
            "Matched Gendreau parameter, d",
            "Mean gap from lower bound (%)" if index == 0 else None,
            x_ticks=D_VALUES,
            y_min=0,
            y_max=30,
        )
    image.save(path, dpi=(300, 300))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--figure", required=True)
    args = parser.parse_args()

    rows: list[dict] = []
    start = time.perf_counter()
    for family_id, (family, n) in enumerate(CELLS, start=1):
        for d_index, d in enumerate(D_VALUES):
            for rep in range(REPS):
                seed = (
                    args.base_seed * 100_000_000
                    + 30_000_000
                    + family_id * 1_000_000
                    + n * 100
                    + d_index * 10
                    + rep
                )
                instance = make_er_instance(family, n, d, seed)
                lb = combined_lower_bound(instance)
                for name, fn in (
                    ("FFD-C", ffdc),
                    ("BFD-C", bfdc),
                    ("MB-WFD-pure", mbwfd_pure),
                    ("MB-WFD-capped", mbwfd_capped),
                ):
                    result = run_one(instance, fn, name)
                    gap = (
                        float("nan")
                        if result.bins_used == -1
                        else (result.bins_used - lb) / lb
                    )
                    rows.append(
                        {
                            "family": family,
                            "n": n,
                            "d": d,
                            "target_edge_probability": expected_realised_density(d),
                            "realised_edge_density": instance.realised_edge_density,
                            "seed": seed,
                            "heuristic": name,
                            "bins_used": result.bins_used,
                            "lb": lb,
                            "gap": gap,
                            "runtime_ms": result.runtime_ms,
                            "retries": result.extra.get("retries", ""),
                            "status": result.extra.get("status", "success"),
                            "used_ffdc_fallback": result.extra.get(
                                "used_ffdc_fallback", ""
                            ),
                        }
                    )
            print(f"done {family} d={d:.1f}", flush=True)

    output = Path(args.out)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = aggregate(rows)
    Path(args.summary).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    make_figure(summary, Path(args.figure))
    print(json.dumps(summary["validation"], indent=2))
    print(f"wall_clock_seconds={time.perf_counter() - start:.1f}")


if __name__ == "__main__":
    main()
