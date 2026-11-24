"""Turn results/<stage>/runs.csv into _reqm/3_results.md, _reqm/results_tables.tex and figures.
   python experiments/make_report.py"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from eppace.stats import paired

R = Path("results")
OUT = Path("../_reqm")
OLD = ["b1_astar", "b2_replan", "b3_prioritized", "eppace"]       # control/robust/ablation stages hold only these
VARS = ["b1_astar", "b2_replan", "b3_prioritized", "b4_whca", "b5_pibt", "eppace"]
NAME = {"b1_astar": "Traditional A*", "b2_replan": "Replanning A* (D*-style)", "b3_prioritized": "Multi-agent A* (prioritized, Cooperative A*)",
        "b4_whca": "WHCA* (Silver 2005)", "b5_pibt": "PIBT (Okumura 2022)",
        "eppace": "EPP-ACE", "eppace_res": "EPP-ACE + reservation predictor",
        "eppace_manuscript_score": "EPP-ACE (manuscript CDS score)", "a2_congestion": "A2 congestion only",
        "a3_priority": "A3 + priority", "a4_adaptation": "A4 + adaptation", "a5_no_coordination": "A5 full, no coordination"}
COL = {"b1_astar": "#8c8c8c", "b2_replan": "#e69f00", "b3_prioritized": "#0072b2", "b4_whca": "#009e73", "b5_pibt": "#cc79a7", "eppace": "#d55e00"}
DEN = {50: "Low (50 agents)", 100: "Medium-low (100 agents)", 200: "Medium (200 agents)", 500: "High (500 agents)"}
CLS = ["critical", "high", "medium", "low"]


def load(name):
    p = R / name / "runs.csv"
    return pd.read_csv(p) if p.exists() else None


def ms(x, d=1):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return "n/a" if len(x) == 0 else f"{x.mean():.{d}f} ± {x.std(ddof=1) if len(x) > 1 else 0:.{d}f}"


def mean(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return float(x.mean()) if len(x) else float("nan")


def sig(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def pv(p):
    return "p" + (sig(p) if p < 0.001 else "=" + sig(p))


def md_table(head, rows):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(map(str, r)) + " |" for r in rows])


def tex_table(caption, label, head, rows, star=False):
    env = "table*" if star else "table"
    spec = "|l|" + "c|" * (len(head) - 1)
    body = " \\\\ \\hline\n".join(" & ".join(str(c).replace("%", "\\%").replace("±", "$\\pm$").replace("<", "$<$") for c in r) for r in rows)
    return (f"\\begin{{{env}}}[t]\n\\caption{{{caption}}}\n\\label{{{label}}}\n\\centering\n\\small\n\\resizebox{{{'\\textwidth' if star else '\\columnwidth'}}}{{!}}{{%\n\\begin{{tabular}}{{{spec}}}\n\\hline\n"
            + " & ".join(f"\\textbf{{{h}}}" for h in head) + " \\\\ \\hline\n" + body + " \\\\ \\hline\n\\end{tabular}}\n\\end{" + env + "}\n")


def ci(d):
    return f"[{d.ci_lo:+.1f}, {d.ci_hi:+.1f}]"


def bars(df, metric, ylabel, fname, scale=1.0, title=None):
    fig, ax = plt.subplots(figsize=(6.4, 3.9))
    ns = sorted(df["cfg.n_agents"].unique()); w = 0.8 / len(VARS)
    for i, v in enumerate(VARS):
        mu, err = [], []
        for n in ns:
            x = df[(df.variant == v) & (df["cfg.n_agents"] == n)][metric].dropna().to_numpy() * scale
            mu.append(x.mean() if len(x) else np.nan)
            err.append(1.96 * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0)
        ax.bar(np.arange(len(ns)) + (i - (len(VARS) - 1) / 2) * w, mu, w, yerr=err, label=NAME[v], color=COL[v], capsize=2, error_kw={"lw": .8})
    ax.set_xticks(range(len(ns)), [DEN[n] for n in ns]); ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False); ax.legend(fontsize=7, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3)
    if title: ax.set_title(title, fontsize=9)
    fig.tight_layout(); fig.savefig(OUT / fname, dpi=200); plt.close(fig)


def main():
    # main500 is deferred and left out; the "x" stages hold the new methods for the same seeds.
    main_df = pd.concat([d for d in (load("main50"), load("main50x"), load("main100"),
                                     load("main200"), load("main200x")) if d is not None], ignore_index=True)
    ns = sorted(main_df["cfg.n_agents"].unique())
    nseeds = main_df.groupby("cfg.n_agents").seed.nunique().to_dict()
    seeds = ", ".join(f"{nseeds[n]} at {n} agents" for n in ns)
    viol = int(main_df.violations.sum())
    md, tex = [], []

    # ---------------- Table 1 -----------------
    metrics = [("tcr_on_time", "Task completion on time (%)", 1), ("path_efficiency", "Path efficiency", 3),
               ("adaptation_time", "Adaptation time (steps)", 1), ("throughput", "Throughput (tasks/step)", 3),
               ("mean_density", "Mean congestion (evaluator density)", 3), ("conflicts", "Planner conflicts left to the arbiter", 0)]
    # Holm family = all tests of one baseline within one scenario (variants x metrics)
    per_n = lambda base: pd.concat([paired(main_df[main_df["cfg.n_agents"] == n].assign(**{"cfg.n_agents": n}), base,
                                           [m for m, _, _ in metrics], group=["cfg.n_agents"]) for n in ns], ignore_index=True)
    vs_best, vs_a, vs_pibt = per_n("b3_prioritized"), per_n("b1_astar"), per_n("b5_pibt")
    rows1 = []
    for n in ns:
        for m, lab, d in metrics:
            cells = [ms(main_df[(main_df.variant == v) & (main_df["cfg.n_agents"] == n)][m], d) for v in VARS]
            r = vs_best[(vs_best["cfg.n_agents"] == n) & (vs_best.metric == m) & (vs_best.variant == "eppace")]
            diff = "n/a" if r.empty else f"{r.mean_diff.iloc[0]:+.{d}f} ({pv(r.p_holm.iloc[0])})"
            r2 = vs_pibt[(vs_pibt["cfg.n_agents"] == n) & (vs_pibt.metric == m) & (vs_pibt.variant == "eppace")]
            diff2 = "n/a" if r2.empty else f"{r2.mean_diff.iloc[0]:+.{d}f} ({pv(r2.p_holm.iloc[0])})"
            rows1.append([DEN[n] if m == metrics[0][0] else "", lab, *cells, diff, diff2])
    head1 = ["Scenario", "Metric", *[NAME[v] for v in VARS], "EPP-ACE minus Multi-agent A* (Holm p)", "EPP-ACE minus PIBT (Holm p)"]
    md += ["## 1. Comprehensive comparison", f"Paired seeds: {seeds}. Mean ± SD. Same maps, tasks and failures for every algorithm within a seed. "
           f"Safety violations across all {len(main_df)} runs: **{viol}**.", "", md_table(head1, rows1), ""]
    tex.append(tex_table("Comprehensive performance comparison on the rooms-and-doors map (mean $\\pm$ SD over paired seeds: " + seeds + "). Last column: EPP-ACE minus Multi-agent A* with Holm-corrected Wilcoxon p.",
                         "table:comprehensive_comparison", ["Scenario", "Metric", "Trad. A*", "Replan A*", "Coop. A*", "WHCA*", "PIBT", "EPP-ACE", "EPP-ACE $-$ Coop. A*", "EPP-ACE $-$ PIBT"],
                         rows1, star=True))

    # ---------------- Paired detail -----------------
    pr = []
    for n in ns:
        for base, tab in (("b1_astar", vs_a), ("b3_prioritized", vs_best), ("b5_pibt", vs_pibt)):
            for m in ("tcr_on_time", "mean_density"):
                r = tab[(tab["cfg.n_agents"] == n) & (tab.metric == m) & (tab.variant == "eppace")]
                if len(r):
                    r = r.iloc[0]
                    pr.append([DEN[n], f"EPP-ACE vs {NAME[base]}", m, f"{r.mean_diff:+.3f}", f"[{r.ci_lo:+.3f}, {r.ci_hi:+.3f}]", sig(r.p_holm), f"{r.cliffs_delta:+.2f}"])
    md += ["### Paired effect sizes (EPP-ACE)", md_table(["Scenario", "Comparison", "Metric", "Mean paired diff", "95% bootstrap CI", "Holm p", "Cliff's δ"], pr), ""]

    # ---------------- Congestion reduction -----------------
    cr = []
    for n in ns:
        dens = main_df[main_df["cfg.n_agents"] == n].groupby("variant").mean_density.mean()
        for v in VARS[1:]:
            cr.append([DEN[n], NAME[v], f"{dens['b1_astar']:.3f}", f"{dens[v]:.3f}", f"{100 * (1 - dens[v] / dens['b1_astar']):+.1f}%"])
    md += ["## 2. Congestion reduction  (1 − density / density of Traditional A*)",
           "Caution: gridlocked agents stand still, so a failed baseline can show *lower* or higher density depending on where it jams. Read with Table 1.", "",
           md_table(["Scenario", "Algorithm", "A* density", "Density", "Reduction vs A*"], cr), ""]
    tex.append(tex_table("Congestion reduction relative to Traditional A* (evaluator density).", "table:congestion",
                         ["Scenario", "Algorithm", "A* density", "Density", "Reduction"], cr))

    # ---------------- Priority -----------------
    pr_rows, n0 = [], 200 if 200 in ns else ns[len(ns) // 2]
    sub = main_df[main_df["cfg.n_agents"] == n0]
    for c in CLS:
        col = f"tcr_by_class.{c}"
        cells = [ms(sub[sub.variant == v][col]) for v in VARS]
        r = paired(sub, "b3_prioritized", [col], group=None)
        r = r[(r.variant == "eppace")]
        pr_rows.append([c.capitalize(), *cells, "n/a" if r.empty else f"{r.mean_diff.iloc[0]:+.1f} ({pv(r.p.iloc[0])})"])
    md += [f"## 3. Priority-based task completion ({DEN[n0]})", md_table(["Priority", *[NAME[v] for v in VARS], "EPP-ACE − MA-A* (raw p)"], pr_rows), ""]
    tex.append(tex_table(f"Priority-based task completion on time (\\%), {DEN[n0].lower()}.", "table:priority_analysis",
                         ["Priority", "Trad. A*", "Replan A*", "Coop. A*", "WHCA*", "PIBT", "EPP-ACE", "EPP-ACE $-$ Coop. A*"], pr_rows, star=False))

    # ---------------- Robustness -----------------
    rb = load("robust")
    if rb is not None:
        rows = []
        for (f, c), g in rb.groupby(["cfg.agent_failure", "cfg.comm_loss"]):
            lab = "none" if f == 0 and c == 0 else ", ".join(x for x in ([f"{int(f*100)}% agent failure"] if f else []) + ([f"{int(c*100)}% communication loss"] if c else []))
            rows.append([lab, *[ms(g[g.variant == v].tcr_on_time) for v in ("b1_astar", "b3_prioritized", "eppace")]])
        md += ["## 4. Robustness (50 agents)", md_table(["Disturbance", "Traditional A*", "Multi-agent A*", "EPP-ACE"], rows), ""]
        tex.append(tex_table("Task completion on time (\\%) under disturbances, 50 agents.", "table:robustness", ["Disturbance", "Trad. A*", "Multi-agent A*", "EPP-ACE"], rows))

    # ---------------- Ablation -----------------
    ab = load("ablation")
    if ab is not None:
        t = paired(ab, "b3_prioritized", ["tcr_on_time", "mean_density"])
        rows = []
        for v in ab.variant.unique():
            g = ab[ab.variant == v]
            r = t[(t.variant == v) & (t.metric == "tcr_on_time")]
            rows.append([NAME.get(v, v), ms(g.tcr_on_time), ms(g.mean_density, 3), ms(g.plan_ms_mean, 2),
                         "baseline" if v == "b3_prioritized" else f"{r.mean_diff.iloc[0]:+.2f} ({pv(r.p_holm.iloc[0])})"])
        md += [f"## 5. Ablation ({DEN[200]}, {len(ab[ab.variant == 'eppace'])} seeds)", md_table(["Variant", "On-time %", "Density", "Plan ms", "On-time vs Multi-agent A* (Holm p)"], rows), ""]
        tex.append(tex_table("Ablation at 200 agents: contribution of each EPP-ACE component over prioritized planning.", "table:ablation",
                             ["Variant", "On-time \\%", "Density", "Plan ms", "vs MA-A*"], rows))

    # ---------------- Control -----------------
    ct = load("control")
    if ct is not None:
        rows = []
        for n in sorted(ct["cfg.n_agents"].unique()):
            g = ct[ct["cfg.n_agents"] == n]
            rows.append([DEN.get(n, n), *[ms(g[g.variant == v].tcr_on_time) for v in OLD]])
        md += ["## 6. Control: same grid, scattered 15% walls instead of rooms", md_table(["Scenario", *[NAME[v] for v in OLD]], rows), ""]
        tex.append(tex_table("Control on the same grid with 15\\% scattered walls instead of rooms: task completion on time (\\%). The task rate is fixed at 1.0 for both agent counts.", "table:control",
                             ["Scenario", "Trad. A*", "Replan A*", "Multi-agent A*", "EPP-ACE"], rows))

    # ---------------- Cost -----------------
    rows = [[DEN[n], *[f"{mean(main_df[(main_df.variant == v) & (main_df['cfg.n_agents'] == n)].plan_ms_mean):.2f}" for v in VARS],
             *[f"{mean(main_df[(main_df.variant == v) & (main_df['cfg.n_agents'] == n)].wall_time_s):.1f}" for v in ("b3_prioritized", "eppace")]] for n in ns]
    md += ["## 7. Computational cost", md_table(["Scenario", *[f"{NAME[v]} plan ms" for v in VARS], "MA-A* run s", "EPP-ACE run s"], rows), ""]

    # figures
    bars(main_df, "tcr_on_time", "Tasks completed on time (%)", "fig_task_completion.png")
    bars(main_df, "path_efficiency", "Path efficiency", "fig_path_efficiency.png")
    bars(main_df, "adaptation_time", "Adaptation time (steps)", "fig_adaptation_time.png")
    (OUT / "results_tables.tex").write_text("% generated by experiments/make_report.py; do not edit\n" + "\n".join(tex))
    (R / "report_body.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
