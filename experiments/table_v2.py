"""Final comparison table in the manuscript layout (S3 working load, held-out seeds 100-129).
   python experiments/table_v2.py  -> prints and appends to ../_reqm/5_results_v2.md"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import wilcoxon

R = Path("results")
SIZES = [(50, "Low (50 agents)"), (100, "Medium-low (100 agents)"), (200, "Medium (200 agents)")]
SETS = {
    "same allocator for every method": ["b1_alloc", "b2_alloc", "b3_alloc", "b4_alloc", "b5_alloc", "eppace2"],
    "baselines as they were (longest-idle assignment); EPP-ACE v2 with its allocator": ["b1_astar", "b2_replan", "b3_prioritized", "b4_whca", "b5_pibt", "eppace2"],
}
HEAD = ["Traditional A*", "Replanning A* (D*-style)", "Coop A*", "WHCA*", "PIBT", "EPP-ACE v2"]
M = [("tcr_on_time", "Task completion on time (%)", 1), ("path_efficiency", "Path efficiency", 3),
     ("travel_time_efficiency", "Travel-time efficiency", 3), ("adaptation_time", "Adaptation time (steps)", 1),
     ("throughput", "Throughput (tasks/step)", 3), ("mean_density", "Mean congestion (evaluator density)", 3),
     ("conflicts", "Planner conflicts left to the arbiter", 0), ("plan_ms_mean", "Plan ms per decision", 2)]


def load(n):
    st = f"s3_{n}"
    parts = [pd.read_csv(R / f"v2_{st}" / "runs.csv"), pd.read_csv(R / f"v2a_{st}" / "runs.csv")]
    return pd.concat(parts)


def cell(df, v, m, d):
    x = df[df.variant == v][m].dropna()
    if not len(x):
        return "n/a"
    return f"{x.mean():.{d}f} ± {x.std():.{d}f}"


def main():
    out = ["", "# Final comparison, S3 working load (30 paired held-out seeds 100-129)", "",
           "Rooms 60x60, doors 2, 5 moving obstacles, 3 tasks per 100 agents per step. Mean ± SD."]
    data = {n: load(n) for n, _ in SIZES}
    viol = int(sum(d.violations.sum() for d in data.values()))
    out.append(f"Safety violations in these runs: **{viol}**.")
    for title, vs in SETS.items():
        out += ["", f"## Table: {title}", "", "| Scenario | Metric | " + " | ".join(HEAD) + " | v2 minus Coop A* (p) | v2 minus PIBT (p) |",
                "|---|---|" + "---|" * (len(HEAD) + 2)]
        for n, lab in SIZES:
            df = data[n]
            for i, (m, name, d) in enumerate(M):
                cells = [cell(df, v, m, d) for v in vs]
                dd = []
                for ref in (vs[2], vs[4]):
                    a = df[df.variant == "eppace2"].set_index("seed")[m]
                    b = df[df.variant == ref].set_index("seed")[m]
                    x = (a - b).dropna()
                    p = wilcoxon(x).pvalue if len(x) and (x != 0).any() else 1.0
                    dd.append(f"{x.mean():+.{max(d,2)}f} (p={p:.3f})" if len(x) else "n/a")
                out.append(f"| {lab if i == 0 else ''} | {name} | " + " | ".join(cells) + f" | {dd[0]} | {dd[1]} |")
    # predictions P13-P15
    sa = SETS["same allocator for every method"]
    r = {n: {v: data[n][data[n].variant == v].tcr_on_time.mean() for v in sa} for n, _ in SIZES}
    p13 = all(94 <= r[n][v] <= 99.9 for n, _ in SIZES for v in ("b3_alloc", "b4_alloc", "b5_alloc", "eppace2"))
    dens = {n: (data[n][data[n].variant == "eppace2"].mean_density.mean() / data[n][data[n].variant == "b3_alloc"].mean_density.mean() - 1) for n, _ in SIZES}
    p14 = all(abs(r[n]["eppace2"] - r[n]["b3_alloc"]) <= 0.5 and dens[n] <= -0.08 for n, _ in SIZES)
    p15 = all(r[n]["b3_alloc"] - r[n]["b5_alloc"] >= 2 for n in (100, 200))
    out += ["", "## S3 predictions (frozen in 4_theory_v2.md section 8)", "", "| # | Result | Evidence |", "|---|---|---|",
            f"| P13 coordinated + alloc within 94-99.9% | {'CONFIRMED' if p13 else 'REFUTED'} | " + "; ".join(f"{n}: " + ", ".join(f"{v.split('_')[0]} {r[n][v]:.1f}" for v in ('b3_alloc','b4_alloc','b5_alloc','eppace2')) for n, _ in SIZES) + " |",
            f"| P14 v2 within 0.5 of Coop A*, density >= 8% lower | {'CONFIRMED' if p14 else 'REFUTED'} | " + "; ".join(f"{n}: {r[n]['eppace2']-r[n]['b3_alloc']:+.2f} pts, density {dens[n]:+.1%}" for n, _ in SIZES) + " |",
            f"| P15 PIBT >= 2 points below Coop A* at 100/200 | {'CONFIRMED' if p15 else 'REFUTED'} | " + "; ".join(f"{n}: {r[n]['b3_alloc']-r[n]['b5_alloc']:+.2f}" for n in (100, 200)) + " |"]
    txt = "\n".join(out) + "\n"
    open("../_reqm/5_results_v2.md", "a").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
