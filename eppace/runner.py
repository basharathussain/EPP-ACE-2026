"""Run one configuration, persist it, and sweep many in a process pool.

A run directory holds everything needed to audit or replay it:
  manifest.json   config + digest + software versions (what produced this)
  metrics.json    the evaluator's numbers
  events.jsonl    plans, assignments, arbitrations, adaptations, completions
  tasks.json      every task and its outcome
  trace.npz       positions/status per step, obstacles, congestion keyframes (for replay)
"""
from __future__ import annotations

import itertools
import json
import platform
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import scipy
import yaml

from . import __version__
from .config import Config
from .sim import run

SPEC_REVISION = "R2"


def manifest(cfg: Config) -> dict:
    return {"eppace": __version__, "spec": SPEC_REVISION, "config": cfg.to_dict(),
            "digest": cfg.digest(), "python": sys.version.split()[0], "numpy": np.__version__,
            "scipy": scipy.__version__, "platform": platform.platform()}


def save_run(res, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest(res.cfg), indent=2, default=list))
    (out / "metrics.json").write_text(json.dumps(res.metrics, indent=2, default=float))
    with open(out / "events.jsonl", "w") as f:
        for e in res.events:
            f.write(json.dumps(e, default=list) + "\n")
    (out / "tasks.json").write_text(json.dumps(res.tasks))
    if res.trace:
        tr = res.trace
        obs = np.full((len(tr["obstacles"]), max(1, max(len(o) for o in tr["obstacles"])), 2), -1, np.int16)
        for i, o in enumerate(tr["obstacles"]):
            obs[i, :len(o)] = o
        np.savez_compressed(out / "trace.npz", pos=tr["pos"], status=tr["status"], obstacles=obs,
                            cong=tr["cong"], cong_t=tr["cong_t"], walls=tr["walls"])


def flatten(metrics: dict) -> dict:
    out = {}
    for k, v in metrics.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                out[f"{k}.{kk}"] = vv
        else:
            out[k] = v
    return out


def _work(args):
    cfg_dict, out_dir, trace = args
    cfg = Config.from_dict(cfg_dict)
    res = run(cfg, record_trace=trace)
    if out_dir:
        save_run(res, Path(out_dir))
    row = {"variant": cfg.variant, "seed": cfg.seed, "digest": cfg.digest(), **flatten(res.metrics)}
    row.update({f"cfg.{k}": v for k, v in cfg.to_dict().items()
                if k not in ("flags_override", "class_mix", "deadline_factors")})
    return row


def expand(exp: dict) -> list[Config]:
    """exp: {base: {...}, variants: [...], seeds: N | [..], grid: {param: [values]}}"""
    base = dict(exp.get("base", {}))
    variants = exp.get("variants", [base.get("variant", "eppace")])
    seeds = exp.get("seeds", 1)
    seeds = list(range(seeds)) if isinstance(seeds, int) else list(seeds)
    grid = exp.get("grid", {})
    keys = list(grid)
    out = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        for variant in variants:
            for seed in seeds:
                d = {**base, **dict(zip(keys, combo)), "variant": variant, "seed": seed}
                d["name"] = exp.get("name", "exp")
                out.append(Config.from_dict(d))
    return out


def sweep(exp: dict, out_root: Path, workers: int = 8, save_runs: bool = False, progress=None):
    cfgs = expand(exp)
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "experiment.yaml").write_text(yaml.safe_dump(exp, sort_keys=False))
    jobs = [(c.to_dict(), str(out_root / "runs" / f"{c.variant}_{c.digest()}") if save_runs else None, False)
            for c in cfgs]
    rows = []
    if workers <= 1:
        for i, j in enumerate(jobs):
            rows.append(_work(j))
            if progress:
                progress(i + 1, len(jobs))
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for i, row in enumerate(ex.map(_work, jobs, chunksize=1)):
                rows.append(row)
                if progress:
                    progress(i + 1, len(jobs))
    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(out_root / "runs.csv", index=False)
    return df
