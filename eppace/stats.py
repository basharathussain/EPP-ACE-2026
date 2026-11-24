"""Paired comparisons between variants on identical (scenario, seed) pairs.

Per metric: mean paired difference with a bootstrap 95% CI, Wilcoxon signed-rank p,
Cliff's delta, and Holm correction across the whole family of tests.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

HIGHER_BETTER = {"tcr_on_time": True, "completion_rate": True, "throughput": True,
                 "path_efficiency": True, "mean_task_latency": False, "mean_density": False,
                 "conflicts": False, "mean_wait_per_task": False, "adaptation_time": False,
                 "peak_density": False, "makespan": False}


def cliffs_delta(x: np.ndarray, y: np.ndarray) -> float:
    gt = sum((xi > y).sum() for xi in x)
    lt = sum((xi < y).sum() for xi in x)
    return float((gt - lt) / (len(x) * len(y)))


def holm(p: list[float]) -> list[float]:
    order = np.argsort(p)
    m = len(p)
    out = [0.0] * m
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * p[i]))
        out[i] = run
    return out


def paired(df: pd.DataFrame, baseline: str, metrics: list[str], group: list[str] | None = None,
           n_boot: int = 5000, seed: int = 0) -> pd.DataFrame:
    """Rows: one per (group, variant != baseline, metric)."""
    group = group or [c for c in df.columns if c.startswith("cfg.") and c not in ("cfg.variant", "cfg.seed", "cfg.name")
                      and df[c].nunique() > 1]
    rng = np.random.default_rng(seed)
    rows = []
    for key, sub in (df.groupby(group) if group else [((), df)]):
        base = sub[sub.variant == baseline].set_index("seed")
        for variant in sorted(set(sub.variant) - {baseline}):
            other = sub[sub.variant == variant].set_index("seed")
            seeds = base.index.intersection(other.index)
            for m in metrics:
                a, b = other.loc[seeds, m].astype(float), base.loc[seeds, m].astype(float)
                ok = a.notna() & b.notna()
                a, b = a[ok].to_numpy(), b[ok].to_numpy()
                if len(a) < 2:
                    continue
                d = a - b
                boots = rng.choice(d, size=(n_boot, len(d))).mean(axis=1)
                try:
                    p = float(stats.wilcoxon(a, b).pvalue) if np.any(d != 0) else 1.0
                except ValueError:
                    p = 1.0
                rows.append({**(dict(zip(group, key if isinstance(key, tuple) else (key,))) if group else {}),
                             "variant": variant, "baseline": baseline, "metric": m, "n": len(a),
                             "mean_variant": a.mean(), "mean_baseline": b.mean(), "mean_diff": d.mean(),
                             "ci_lo": np.percentile(boots, 2.5), "ci_hi": np.percentile(boots, 97.5),
                             "p": p, "cliffs_delta": cliffs_delta(a, b)})
    out = pd.DataFrame(rows)
    if len(out):
        out["p_holm"] = holm(out["p"].tolist())
    return out


def congestion_reduction(df: pd.DataFrame, baseline: str, group: list[str] | None = None) -> pd.DataFrame:
    """CR = 1 - mean_density(variant) / mean_density(baseline), the evaluator's own density."""
    g = df.groupby((group or []) + ["variant"])["mean_density"].mean().reset_index()
    base = g[g.variant == baseline].drop(columns="variant").rename(columns={"mean_density": "base"})
    out = g.merge(base, on=group) if group else g.assign(base=float(base["base"].iloc[0]))
    out["congestion_reduction_pct"] = 100.0 * (1 - out["mean_density"] / out["base"])
    return out[out.variant != baseline]
