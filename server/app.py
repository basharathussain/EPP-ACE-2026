"""Local web API over the headless engine.

Storage is plain files under DATA_DIR so a run can be audited without this server:
  runs/<id>/{manifest,metrics,status}.json, events.jsonl, tasks.json, trace.npz
  sweeps/<id>/{experiment.yaml,runs.csv,status.json}
Jobs run in a process pool; status lives in memory and in status.json (a run left
"running" by a restart is reported as "interrupted", never as finished).
"""
from __future__ import annotations

import base64
import io
import json
import os
import threading
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from eppace.config import VARIANTS, Config
from eppace.runner import expand, save_run, sweep
from eppace.sim import run as run_sim
from eppace.stats import congestion_reduction, paired

DATA = Path(os.environ.get("DATA_DIR", "data"))
WORKERS = int(os.environ.get("EPPACE_WORKERS", max(1, (os.cpu_count() or 2) - 1)))
(DATA / "runs").mkdir(parents=True, exist_ok=True)
(DATA / "sweeps").mkdir(parents=True, exist_ok=True)

app = FastAPI(title="EPP-ACE")
pool = ProcessPoolExecutor(max_workers=WORKERS)
lock = threading.Lock()
status: dict[str, dict] = {}


def clean(o):
    """JSON has no NaN: undefined metrics (e.g. no completed tasks) travel as null."""
    if isinstance(o, float) and o != o:
        return None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    return o


def _write_status(kind: str, id_: str, **kw) -> None:
    with lock:
        s = status.setdefault(id_, {"id": id_, "kind": kind, "created": time.time()})
        s.update(kw)
        d = DATA / ("runs" if kind == "run" else "sweeps") / id_
        d.mkdir(parents=True, exist_ok=True)
        (d / "status.json").write_text(json.dumps(s))


def _load_status(kind: str, id_: str) -> dict:
    if id_ in status:
        return status[id_]
    f = DATA / ("runs" if kind == "run" else "sweeps") / id_ / "status.json"
    if not f.exists():
        raise HTTPException(404, f"{kind} {id_} not found")
    s = json.loads(f.read_text())
    if s.get("state") in ("queued", "running"):
        s["state"] = "interrupted"          # the process that owned it is gone
    return s


# ---- worker functions (top-level so the pool can pickle them) --------------------------
def _do_run(cfg_dict: dict, out: str) -> dict:
    res = run_sim(Config.from_dict(cfg_dict), record_trace=True)
    save_run(res, Path(out))
    return {k: v for k, v in res.metrics.items() if not isinstance(v, dict)}


def _do_sweep(exp: dict, out: str, workers: int, id_: str) -> int:
    def progress(i, n):
        _write_status("sweep", id_, done=i, total=n)
    df = sweep(exp, Path(out), workers=workers, progress=progress)
    return len(df)


# ---- meta ---------------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "workers": WORKERS}


@app.get("/api/meta")
def meta():
    d = Config().to_dict()
    return {"defaults": d, "variants": {k: asdict(v) for k, v in VARIANTS.items()}}


# ---- single runs --------------------------------------------------------------------------
class RunReq(BaseModel):
    config: dict


@app.post("/api/runs")
def create_run(req: RunReq):
    try:
        cfg = Config.from_dict(req.config)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))
    if cfg.n_agents + cfg.n_moving_obstacles > cfg.height * cfg.width * (1 - cfg.obstacle_density) * 0.8:
        raise HTTPException(422, "too many agents for the free area of the grid")
    if cfg.n_agents * cfg.steps > 400_000:
        raise HTTPException(422, "agents x steps above 400k for an interactive run; use a sweep")
    id_ = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    _write_status("run", id_, state="queued", variant=cfg.variant, seed=cfg.seed, name=cfg.name,
                  n_agents=cfg.n_agents, steps=cfg.steps)
    fut = pool.submit(_do_run, cfg.to_dict(), str(DATA / "runs" / id_))

    def done(f):
        try:
            m = f.result()
            _write_status("run", id_, state="done", headline={k: m.get(k) for k in (
                "tcr_on_time", "tasks_done", "conflicts", "violations", "mean_density")})
        except Exception as e:                       # surfaced, not swallowed
            _write_status("run", id_, state="failed", error=repr(e))
    fut.add_done_callback(done)
    _write_status("run", id_, state="running")
    return {"id": id_}


def _run_dir(id_: str) -> Path:
    d = DATA / "runs" / id_
    if not d.is_dir():
        raise HTTPException(404, "run not found")
    return d


@app.get("/api/runs")
def list_runs():
    out = []
    for d in sorted((DATA / "runs").iterdir(), reverse=True):
        if (d / "status.json").exists():
            out.append(_load_status("run", d.name))
    return out


@app.get("/api/runs/{id_}")
def get_run(id_: str):
    d = _run_dir(id_)
    out = {"status": _load_status("run", id_)}
    for name in ("manifest", "metrics"):
        f = d / f"{name}.json"
        out[name] = clean(json.loads(f.read_text())) if f.exists() else None
    return out


def _b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


@app.get("/api/runs/{id_}/trace")
def get_trace(id_: str):
    d = _run_dir(id_)
    f = d / "trace.npz"
    if not f.exists():
        raise HTTPException(409, "run has no trace yet")
    z = np.load(f)
    pos, st = z["pos"].astype("<i2"), z["status"].astype("i1")
    T, N, _ = pos.shape
    H, W = z["walls"].shape
    cong = (np.clip(z["cong"].astype("f4"), 0, 1) * 255).astype("u1")
    obs = z["obstacles"]
    tasks = json.loads((d / "tasks.json").read_text())
    assigns, dones = [], []
    for line in (d / "events.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e.get("event") == "assign":
            assigns.append([e["t"], e["task"], e["agent"]])
        elif e.get("event") == "done":
            dones.append([e["t"], e["task"]])
    return {"T": T, "N": N, "H": H, "W": W, "pos": _b64(pos), "status": _b64(st),
            "walls": _b64(z["walls"].astype("u1")), "cong": _b64(cong),
            "cong_t": z["cong_t"].tolist(), "obstacles": obs.tolist(),
            "tasks": [{k: t[k] for k in ("id", "goal", "cls", "created", "deadline", "priority", "state")}
                      for t in tasks],
            "assigns": assigns, "dones": dones}


@app.get("/api/runs/{id_}/events")
def get_events(id_: str, t: int | None = None, kind: str | None = None,
               agent: int | None = None, limit: int = Query(500, le=5000)):
    d = _run_dir(id_)
    out = []
    for line in (d / "events.jsonl").read_text().splitlines():
        e = json.loads(line)
        if t is not None and e.get("t") != t:
            continue
        if kind and e.get("event") != kind:
            continue
        if agent is not None and e.get("agent") != agent:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


# ---- sweeps ---------------------------------------------------------------------------------
class SweepReq(BaseModel):
    experiment: dict
    workers: int | None = None


@app.post("/api/sweeps")
def create_sweep(req: SweepReq):
    try:
        cfgs = expand(req.experiment)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))
    if not cfgs:
        raise HTTPException(422, "experiment expands to zero runs")
    id_ = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    name = req.experiment.get("name", "exp")
    _write_status("sweep", id_, state="running", name=name, done=0, total=len(cfgs),
                  variants=sorted({c.variant for c in cfgs}))
    exp = {**req.experiment, "name": name}
    # a sweep brings its own pool, so it is a thread here and never starves single runs
    def go():
        try:
            _do_sweep(exp, str(DATA / "sweeps" / id_), req.workers or WORKERS, id_)
            _write_status("sweep", id_, state="done")
        except Exception as e:
            _write_status("sweep", id_, state="failed", error=repr(e))
    threading.Thread(target=go, daemon=True).start()
    return {"id": id_, "runs": len(cfgs)}


def _sweep_dir(id_: str) -> Path:
    d = DATA / "sweeps" / id_
    if not d.is_dir():
        raise HTTPException(404, "sweep not found")
    return d


@app.get("/api/sweeps")
def list_sweeps():
    return [_load_status("sweep", d.name) for d in sorted((DATA / "sweeps").iterdir(), reverse=True)
            if (d / "status.json").exists()]


@app.get("/api/sweeps/{id_}")
def get_sweep(id_: str):
    d = _sweep_dir(id_)
    s = _load_status("sweep", id_)
    exp = yaml.safe_load((d / "experiment.yaml").read_text()) if (d / "experiment.yaml").exists() else None
    return {"status": s, "experiment": exp}


def _df(id_: str) -> pd.DataFrame:
    f = _sweep_dir(id_) / "runs.csv"
    if not f.exists():
        raise HTTPException(409, "sweep has no results yet")
    return pd.read_csv(f)


METRICS = ["tcr_on_time", "completion_rate", "throughput", "path_efficiency", "mean_task_latency",
           "mean_density", "conflicts", "mean_wait_per_task", "adaptation_time"]


@app.get("/api/sweeps/{id_}/summary")
def sweep_summary(id_: str, baseline: str | None = None):
    df = _df(id_)
    variants = sorted(df.variant.unique())
    baseline = baseline or ("b1_astar" if "b1_astar" in variants else variants[0])
    g = df.groupby("variant")
    rows = []
    for v, sub in g:
        row = {"variant": v, "n": len(sub)}
        for m in METRICS:
            x = sub[m].dropna().astype(float)
            n = len(x)
            row[m] = {"mean": float(x.mean()) if n else None,
                      "sd": float(x.std(ddof=1)) if n > 1 else None,
                      "ci": (1.96 * float(x.std(ddof=1)) / n ** 0.5) if n > 1 else None}
        rows.append(row)
    pr = paired(df, baseline, METRICS)
    cr = congestion_reduction(df, baseline) if baseline in variants else pd.DataFrame()
    return clean({"baseline": baseline, "variants": variants, "summary": rows,
            "paired": json.loads(pr.to_json(orient="records")),
            "congestion_reduction": json.loads(cr.to_json(orient="records")),
            "violations": int(df["violations"].sum()),
            "censored_tasks": int(df["tasks_censored"].sum()),
            "runs": len(df),
            "seeds": int(df["seed"].nunique()),
            "by_class": {v: {c: float(sub[f"tcr_by_class.{c}"].mean())
                             for c in ("critical", "high", "medium", "low")}
                         for v, sub in g}})


@app.get("/api/sweeps/{id_}/export", response_class=PlainTextResponse)
def sweep_export(id_: str, fmt: str = "csv", baseline: str | None = None):
    df = _df(id_)
    if fmt == "csv":
        return df.to_csv(index=False)
    if fmt == "latex":
        g = df.groupby("variant")[["tcr_on_time", "path_efficiency", "mean_density",
                                   "conflicts", "adaptation_time"]].agg(["mean", "std"])
        buf = io.StringIO()
        buf.write("\\begin{tabular}{lccccc}\n\\hline\nVariant & TCR (\\%) & Path eff. & Density & Conflicts & Adapt. (steps) \\\\\n\\hline\n")
        for v, r in g.iterrows():
            def cell(m, p=2):
                return f"{r[(m, 'mean')]:.{p}f} $\\pm$ {0 if pd.isna(r[(m, 'std')]) else r[(m, 'std')]:.{p}f}"
            buf.write(f"{v.replace('_', '\\_')} & {cell('tcr_on_time', 1)} & {cell('path_efficiency')} & "
                      f"{cell('mean_density', 3)} & {cell('conflicts', 0)} & {cell('adaptation_time', 1)} \\\\\n")
        buf.write("\\hline\n\\end{tabular}\n")
        return buf.getvalue()
    raise HTTPException(422, "fmt must be csv or latex")


# ---- static UI (built by the Dockerfile; absent in dev) --------------------------------------
# Client-side routes (/runs/<id>, /sweeps/<id>) must serve index.html on a direct load or refresh,
# which StaticFiles(html=True) does not do. /api/* routes above take precedence.
UI = Path(os.environ.get("UI_DIR", "ui/dist")).resolve()
if UI.is_dir():
    from fastapi.responses import FileResponse

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        f = (UI / path).resolve()
        if path and f.is_file() and UI in f.parents:
            return FileResponse(f)
        return FileResponse(UI / "index.html")
