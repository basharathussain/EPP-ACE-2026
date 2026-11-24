"""eppace run <config.yaml> | sweep <experiment.yaml> | report <results dir>"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .config import Config, VARIANTS
from .runner import save_run, sweep
from .sim import run


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="eppace")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="one run, saved with a replay trace")
    r.add_argument("config", nargs="?", help="YAML config (omit for defaults)")
    r.add_argument("--variant", choices=sorted(VARIANTS))
    r.add_argument("--seed", type=int)
    r.add_argument("--out", default="results/run")
    s = sub.add_parser("sweep", help="variants x seeds x grid in a process pool")
    s.add_argument("experiment")
    s.add_argument("--workers", type=int, default=8)
    s.add_argument("--out")
    s.add_argument("--save-runs", action="store_true")
    p = sub.add_parser("report", help="paired statistics for a finished sweep")
    p.add_argument("results")
    p.add_argument("--baseline", default="b1_astar")
    a = ap.parse_args(argv)

    if a.cmd == "run":
        d = yaml.safe_load(Path(a.config).read_text()) if a.config else {}
        if a.variant:
            d["variant"] = a.variant
        if a.seed is not None:
            d["seed"] = a.seed
        res = run(Config.from_dict(d), record_trace=True)
        save_run(res, Path(a.out))
        print(json.dumps({k: v for k, v in res.metrics.items() if not isinstance(v, dict)},
                         indent=2, default=float))
    elif a.cmd == "sweep":
        exp = yaml.safe_load(Path(a.experiment).read_text())
        out = Path(a.out or f"results/{exp.get('name', 'exp')}")
        df = sweep(exp, out, a.workers, a.save_runs,
                   progress=lambda i, n: print(f"\r{i}/{n}", end="", flush=True))
        print(f"\nwrote {out / 'runs.csv'} ({len(df)} runs)")
    elif a.cmd == "report":
        import pandas as pd
        from .stats import congestion_reduction, paired
        root = Path(a.results)
        df = pd.read_csv(root / "runs.csv")
        metrics = ["tcr_on_time", "completion_rate", "throughput", "path_efficiency",
                   "mean_task_latency", "mean_density", "conflicts", "mean_wait_per_task",
                   "adaptation_time"]
        tbl = paired(df, a.baseline, metrics)
        tbl.to_csv(root / "paired.csv", index=False)
        cr = congestion_reduction(df, a.baseline)
        cr.to_csv(root / "congestion_reduction.csv", index=False)
        pd.set_option("display.width", 200, "display.max_columns", 30)
        print(tbl.round(4).to_string(index=False))
        print(cr.round(3).to_string(index=False))
        print(f"\nviolations across all runs: {int(df['violations'].sum())}")
