# EPP-ACE reference implementation (deterministic, non-LLM)

Reference implementation and experiment code for the EPP-ACE path-planning article (deterministic, non-LLM simulator).

```
python3 -m venv .venv && .venv/bin/python -m pip install numpy scipy pandas pyyaml pytest fastapi "uvicorn[standard]" pydantic
.venv/bin/python -m pytest -q tests                                   # 38 tests
.venv/bin/python -m eppace run --variant eppace --seed 1 --out results/run1   # saves a replay trace
.venv/bin/python -m eppace sweep experiments/loaded.yaml --workers 10
.venv/bin/python -m eppace report results/loaded --baseline b1_astar
```

Layout: `eppace/` config, world, emm, cds, pmf, planner (space-time A*), coordination
(reservations + arbiter), adaptation, evaluator, sim, runner, stats, cli.
Variants: b1_astar, b2_replan, b3_prioritized, a2..a5, eppace, eppace_res, eppace_manuscript_score.

## Web app (local Docker, no VPS)
```
docker compose up -d --build     # http://localhost:8450  (bound to 127.0.0.1, no auth)
docker compose down              # data stays in ./data (runs/, sweeps/)
```
Pages: Scenarios (build a run or a variants x seeds sweep), Runs, Replay (canvas + scrubber +
per-module Inspector), Results (paired statistics, CSV / LaTeX export). Dev without Docker:
`DATA_DIR=data UI_DIR=ui/dist .venv/bin/python -m uvicorn server.app:app --port 8451` (build the UI first
with `cd ui && npm install && npm run build`).

Not yet built: CBS/PBS and true D* Lite baselines, Q-learning variant, cross-platform determinism check.

## Article experiments (v2)
Compared methods: Traditional A* (`b1_*`), Replanning A* (D*-style, `b2_*`), Cooperative A* (`b3_*`), WHCA* (`b4_*`),
PIBT (`b5_*`) and EPP-ACE (`eppace2`). `*_alloc` variants use the common deadline-aware allocator.
```
.venv/bin/python experiments/campaign_v2.py --help      # stages s0/s1/s2/s3 and the stress grid
.venv/bin/python experiments/report_v2.py               # tables + prediction scorecard
.venv/bin/python experiments/make_figs_v2.py            # paper figures
```
Held-out seeds 100-129, tuning seeds 1-5. Per-run CSVs for the reported results are in `results/`.
