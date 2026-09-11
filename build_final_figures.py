from __future__ import annotations

import csv
import json
import math
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


COLORS = {
    "FFD-C": "#1F77B4",
    "BFD-C": "#FF7F0E",
    "MB-WFD-pure": "#D62728",
    "MB-WFD-capped": "#2CA02C",
}


def font(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    path = Path("C:/Windows/Fonts") / name
    return ImageFont.truetype(str(path), size=size)


F_TITLE = font(52, True)
F_LABEL = font(38)
F_TICK = font(31)
F_LEGEND = font(32)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["n"] = int(row["n"])
        if "density" in row:
            row["density"] = float(row["density"])
        row["gap"] = float(row["gap"])
        row["runtime_ms"] = float(row["runtime_ms"])
        row["bins_used"] = int(row["bins_used"])
    return rows


def grouped(rows: list[dict], fields: tuple[str, ...], value: str) -> dict:
    bucket: dict[tuple, list[float]] = defaultdict(list)
    for row in rows:
        v = row[value]
        if isinstance(v, float) and math.isnan(v):
            continue
        bucket[tuple(row[f] for f in fields)].append(v)
    return {
        k: {
            "mean": stats.mean(v),
            "sd": stats.stdev(v) if len(v) > 1 else 0.0,
            "n": len(v),
        }
        for k, v in bucket.items()
    }


def marker(draw: ImageDraw.ImageDraw, x: float, y: float, color: str, kind: str) -> None:
    r = 9
    if kind == "square":
        draw.rectangle((x - r, y - r, x + r, y + r), fill=color, outline="white", width=2)
    elif kind == "diamond":
        draw.polygon([(x, y - r - 2), (x + r + 2, y), (x, y + r + 2), (x - r - 2, y)],
                     fill=color, outline="white")
    elif kind == "triangle":
        draw.polygon([(x, y - r - 3), (x + r + 3, y + r), (x - r - 3, y + r)],
                     fill=color, outline="white")
    else:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline="white", width=2)


MARKERS = {
    "FFD-C": "circle",
    "BFD-C": "square",
    "MB-WFD-pure": "triangle",
    "MB-WFD-capped": "diamond",
}


def draw_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    series: list[dict],
    xlabel: str,
    ylabel: str | None,
    x_log: bool = False,
    y_log: bool = False,
    x_ticks: list[float] | None = None,
    y_min: float | None = None,
    y_max: float | None = None,
) -> None:
    left, top, right, bottom = box
    plot_l, plot_t, plot_r, plot_b = left + 145, top + 115, right - 35, bottom - 130
    all_x = [x for s in series for x in s["x"]]
    all_y = [y for s in series for y in s["y"] if not math.isnan(y)]
    tx = (lambda v: math.log10(v)) if x_log else (lambda v: v)
    ty = (lambda v: math.log10(v)) if y_log else (lambda v: v)
    x0, x1 = min(tx(v) for v in all_x), max(tx(v) for v in all_x)
    yy0 = min(ty(v) for v in all_y) if y_min is None else ty(y_min)
    yy1 = max(ty(v) for v in all_y) if y_max is None else ty(y_max)
    if yy1 == yy0:
        yy1 += 1
    pad = 0.06 * (yy1 - yy0)
    yy0 -= pad
    yy1 += pad

    def px(v: float) -> float:
        return plot_l + (tx(v) - x0) / (x1 - x0) * (plot_r - plot_l)

    def py(v: float) -> float:
        return plot_b - (ty(v) - yy0) / (yy1 - yy0) * (plot_b - plot_t)

    draw.text(((left + right) / 2, top + 18), title, font=F_TITLE, fill="#222222", anchor="ma")
    draw.line((plot_l, plot_b, plot_r, plot_b), fill="#222222", width=3)
    draw.line((plot_l, plot_t, plot_l, plot_b), fill="#222222", width=3)

    if x_ticks is None:
        x_ticks = sorted(set(all_x))
    for value in x_ticks:
        x = px(value)
        draw.line((x, plot_t, x, plot_b), fill="#E4E4E4", width=2)
        label = f"{int(value)}" if float(value).is_integer() else f"{value:.1f}"
        draw.text((x, plot_b + 18), label, font=F_TICK, fill="#333333", anchor="ma")

    if y_log:
        low_exp = math.floor(yy0)
        high_exp = math.ceil(yy1)
        y_ticks = [10.0 ** e for e in range(low_exp, high_exp + 1)]
    else:
        step = 5 if yy1 - yy0 <= 35 else 10
        low_tick = math.ceil(yy0 / step) * step
        y_ticks = []
        value = low_tick
        while value <= yy1 + 1e-9:
            y_ticks.append(value)
            value += step
    for value in y_ticks:
        if ty(value) < yy0 or ty(value) > yy1:
            continue
        y = py(value)
        draw.line((plot_l, y, plot_r, y), fill="#E4E4E4", width=2)
        label = f"{value:g}" if not y_log else f"{value:g}"
        draw.text((plot_l - 18, y), label, font=F_TICK, fill="#333333", anchor="rm")

    draw.text(((plot_l + plot_r) / 2, bottom - 35), xlabel, font=F_LABEL, fill="#222222", anchor="ma")
    if ylabel:
        temp = Image.new("RGBA", (bottom - top, 90), (255, 255, 255, 0))
        td = ImageDraw.Draw(temp)
        td.text((temp.width / 2, 45), ylabel, font=F_LABEL, fill="#222222", anchor="mm")
        rotated = temp.rotate(90, expand=True)
        draw._image.paste(rotated, (left + 8, int((top + bottom - rotated.height) / 2)), rotated)

    for s in series:
        points = [(px(x), py(y)) for x, y in zip(s["x"], s["y"]) if not math.isnan(y)]
        if len(points) > 1:
            draw.line(points, fill=s["color"], width=5, joint="curve")
        if s.get("yerr"):
            for x, y, err in zip(s["x"], s["y"], s["yerr"]):
                xx, ylo, yhi = px(x), py(max(y - err, 1e-12)), py(y + err)
                draw.line((xx, ylo, xx, yhi), fill=s["color"], width=3)
                draw.line((xx - 11, ylo, xx + 11, ylo), fill=s["color"], width=3)
                draw.line((xx - 11, yhi, xx + 11, yhi), fill=s["color"], width=3)
        for x, y in points:
            marker(draw, x, y, s["color"], MARKERS[s["name"]])


def legend(draw: ImageDraw.ImageDraw, y: int, names: list[str], width: int) -> None:
    item_w = width // len(names)
    for i, name in enumerate(names):
        cx = item_w * i + item_w // 2
        draw.line((cx - 135, y, cx - 80, y), fill=COLORS[name], width=6)
        marker(draw, cx - 108, y, COLORS[name], MARKERS[name])
        draw.text((cx - 60, y), name, font=F_LEGEND, fill="#222222", anchor="lm")


def canvas(width=2600, height=1500) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (width, height), "white")
    return img, ImageDraw.Draw(img)


def fig_triplet_d0(main: list[dict], out: Path) -> None:
    data = [r for r in main if r["family"] == "triplet" and r["density"] == 0.0]
    agg = grouped(data, ("n", "heuristic"), "gap")
    ns = [60, 120, 249]
    names = ["FFD-C", "BFD-C", "MB-WFD-capped"]
    series = []
    for h in names:
        series.append({
            "name": h,
            "color": COLORS[h],
            "x": ns,
            "y": [100 * agg[(n, h)]["mean"] for n in ns],
            "yerr": [100 * agg[(n, h)]["sd"] for n in ns],
        })
    img, draw = canvas()
    legend(draw, 70, names, img.width)
    draw_panel(draw, (80, 95, 2520, 1450), "Triplet instances at d = 0 (no conflicts)",
               series, "Number of items, n", "Mean gap from exact optimum (%)", x_ticks=ns,
               y_min=0, y_max=17)
    img.save(out, dpi=(300, 300))


def fig_density(main: list[dict], out: Path) -> None:
    names = ["FFD-C", "BFD-C", "MB-WFD-capped"]
    img, draw = canvas(3000, 1500)
    legend(draw, 65, names, img.width)
    cells = [("uniform", 250, "Uniform, n = 250"), ("triplet", 120, "Triplet, n = 120")]
    for idx, (family, n, title) in enumerate(cells):
        data = [r for r in main if r["family"] == family and r["n"] == n]
        agg = grouped(data, ("density", "heuristic"), "gap")
        ds = [i / 10 for i in range(10)]
        series = [{
            "name": h,
            "color": COLORS[h],
            "x": ds,
            "y": [100 * agg[(d, h)]["mean"] for d in ds],
        } for h in names]
        box = (50 + idx * 1475, 90, 1500 + idx * 1475, 1450)
        draw_panel(draw, box, title, series, "Generator parameter, d",
                   "Mean gap from lower bound (%)" if idx == 0 else None,
                   x_ticks=ds, y_min=0, y_max=30)
    img.save(out, dpi=(300, 300))


def fig_pure_vs_capped(main: list[dict], out: Path) -> None:
    names = ["MB-WFD-pure", "MB-WFD-capped"]
    img, draw = canvas(3000, 1500)
    legend(draw, 65, names, img.width)
    cells = [("uniform", 250, "Uniform, n = 250"), ("triplet", 120, "Triplet, n = 120")]
    for idx, (family, n, title) in enumerate(cells):
        data = [r for r in main if r["family"] == family and r["n"] == n]
        agg = grouped(data, ("density", "heuristic"), "gap")
        ds = [i / 10 for i in range(10)]
        series = [{
            "name": h,
            "color": COLORS[h],
            "x": ds,
            "y": [100 * agg[(d, h)]["mean"] if (d, h) in agg else math.nan for d in ds],
        } for h in names]
        box = (50 + idx * 1475, 90, 1500 + idx * 1475, 1450)
        draw_panel(draw, box, title, series, "Generator parameter, d",
                   "Mean gap from lower bound (%)" if idx == 0 else None,
                   x_ticks=ds, y_min=0, y_max=85)
    img.save(out, dpi=(300, 300))


def fig_timing(timing: list[dict], out: Path) -> dict:
    agg = grouped(timing, ("family", "n", "heuristic"), "runtime_ms")
    stats_out = {}
    for family in ("uniform", "triplet"):
        stats_out[family] = {}
        for h in ("FFD-C", "BFD-C", "MB-WFD-pure", "MB-WFD-capped"):
            keys = sorted(k for k in agg if k[0] == family and k[2] == h)
            x = np.array([k[1] for k in keys], dtype=float)
            y = np.array([agg[k]["mean"] for k in keys], dtype=float)
            slope, intercept = np.polyfit(np.log(x), np.log(y), 1)
            pred = intercept + slope * np.log(x)
            ss_res = float(np.sum((np.log(y) - pred) ** 2))
            ss_tot = float(np.sum((np.log(y) - np.mean(np.log(y))) ** 2))
            stats_out[family][h] = {
                "exponent": float(slope),
                "r2": float(1.0 - ss_res / ss_tot),
                "largest_n": int(x[-1]),
                "largest_n_mean_ms": float(y[-1]),
            }

    names = ["FFD-C", "BFD-C", "MB-WFD-pure", "MB-WFD-capped"]
    series = []
    for h in names:
        keys = sorted(k for k in agg if k[0] == "uniform" and k[2] == h)
        series.append({
            "name": h,
            "color": COLORS[h],
            "x": [k[1] for k in keys],
            "y": [agg[k]["mean"] for k in keys],
        })
    img, draw = canvas()
    legend(draw, 70, names, img.width)
    draw_panel(draw, (80, 95, 2520, 1450), "Running time on uniform instances, d = 0",
               series, "Number of items, n (log scale)", "Mean running time, ms (log scale)",
               x_log=True, y_log=True, x_ticks=[60, 120, 250, 500, 1000, 2000])
    img.save(out, dpi=(300, 300))
    return stats_out


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit("usage: build_final_figures.py MAIN_CSV TIMING_CSV OUT_DIR STATS_JSON")
    main_csv, timing_csv, out_dir, stats_json = map(Path, sys.argv[1:])
    out_dir.mkdir(parents=True, exist_ok=True)
    main_rows = read_csv(main_csv)
    timing_rows = read_csv(timing_csv)
    fig_triplet_d0(main_rows, out_dir / "figure_4_1_triplet_d0.png")
    fig_density(main_rows, out_dir / "figure_4_2_gap_density.png")
    fig_pure_vs_capped(main_rows, out_dir / "figure_4_3_cap_effect.png")
    timing_stats = fig_timing(timing_rows, out_dir / "figure_4_4_runtime.png")
    stats_json.write_text(json.dumps(timing_stats, indent=2), encoding="utf-8")
    print(json.dumps(timing_stats, indent=2))


if __name__ == "__main__":
    main()
