"""Paper figures from the held-out S3 runs (same data as Table I).
python experiments/make_figs_v2.py  ->  ../_article/images/{task_completion_chart,path_efficiency,congestion_density}.png"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

R = Path("results"); OUT = Path("../_article/images")
SIZES = [50, 100, 200]
METHODS = [("b1_alloc", "Traditional A*"), ("b2_alloc", "Replanning A* (D*-style)"), ("b3_alloc", "Coop A*"),
           ("b4_alloc", "WHCA*"), ("b5_alloc", "PIBT"), ("eppace2", "EPP-ACE")]
COL = ["#b9b9b9", "#8a8a8a", "#4c78a8", "#72b7b2", "#f2a65a", "#d1495b"]


def load(n):
    d = pd.concat([pd.read_csv(R / f"v2a_s3_{n}" / "runs.csv"), pd.read_csv(R / f"v2_s3_{n}" / "runs.csv")])
    return d.drop_duplicates(["variant", "seed"])


D = {n: load(n) for n in SIZES}


def bars(col, ylabel, fname, ylim=None, methods=METHODS, scale=1.0, ref=None):
    fig, ax = plt.subplots(figsize=(3.5, 2.5), dpi=300)
    w = 0.8 / len(methods)
    for i, (v, lab) in enumerate(methods):
        m = [D[n][D[n].variant == v][col].mean() * scale for n in SIZES]
        s = [D[n][D[n].variant == v][col].std() * scale for n in SIZES]
        ax.bar(np.arange(3) + (i - (len(methods) - 1) / 2) * w, m, w, yerr=s, color=COL[[x[0] for x in METHODS].index(v)],
               label=lab, capsize=1.2, error_kw={"lw": 0.5})
    ax.set_xticks(range(3)); ax.set_xticklabels([f"{n} agents" for n in SIZES], fontsize=7)
    ax.set_ylabel(ylabel, fontsize=7); ax.tick_params(axis="y", labelsize=6.5)
    if ylim: ax.set_ylim(*ylim)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.legend(fontsize=5.2, ncol=2, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(); fig.savefig(OUT / fname); plt.close(fig)


bars("tcr_on_time", "Task completion on time (%)", "task_completion_chart.png", (0, 105))
bars("path_efficiency", "Path efficiency", "path_efficiency.png", (0.85, 1.01))
bars("mean_density", "Mean congestion (density)", "congestion_density.png", (0, 0.42))
print("ok")
