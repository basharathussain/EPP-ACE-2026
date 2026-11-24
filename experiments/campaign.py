"""Official campaign for the manuscript results (spec R2, parameters frozen below).
   python experiments/campaign.py [stage ...]   stages: main100 main50x main200x main50 main200 main500 ablation robust control
Writes results/<stage>/runs.csv. 30 paired seeds, identical scenario per (seed, N) across variants."""
import sys
from pathlib import Path

from eppace.runner import sweep

SEEDS = 30
SEEDS_500 = 10  # one EPP-ACE run at 500 agents takes ~1h of CPU here; 30 seeds would take ~15 h
BASE = dict(height=60, width=60, map_style="rooms", room_size=9, door_width=2, n_moving_obstacles=5,
            steps=300, assignment="longest_idle")
MAIN = ["b1_astar", "b2_replan", "b3_prioritized", "eppace"]
NEW = ["b4_whca", "b5_pibt"]  # published comparison methods; the four above are already in main50/main200
rate = lambda n: n / 100


def stage(name):
    if name.startswith("main"):
        # "main100" runs every method; "main50x" / "main200x" add only the new methods to the
        # finished main50 / main200 runs (same seeds, so the results are paired and the old
        # runs are reproduced bit-for-bit rather than recomputed).
        n = int(name[4:].rstrip("x"))
        v = NEW if name.endswith("x") else MAIN + NEW
        return dict(base={**BASE, "n_agents": n, "task_rate": rate(n)}, variants=v)
    if name == "ablation":
        return dict(base={**BASE, "n_agents": 200, "task_rate": rate(200)},
                    variants=["b3_prioritized", "a2_congestion", "a3_priority", "a4_adaptation",
                              "a5_no_coordination", "eppace", "eppace_res", "eppace_manuscript_score"])
    if name == "robust":
        return dict(base={**BASE, "n_agents": 50, "task_rate": rate(50)}, variants=["b1_astar", "b3_prioritized", "eppace"],
                    grid={"agent_failure": [0.0, 0.1], "comm_loss": [0.0, 0.2]})
    if name == "control":  # same grid but scattered walls: is the gap about the map?
        return dict(base={**BASE, "map_style": "random", "obstacle_density": 0.15},
                    variants=MAIN, grid={"n_agents": [50, 200]}, )
    raise SystemExit(f"unknown stage {name}")


if __name__ == "__main__":
    # main500 is deferred (hours per EPP-ACE run); name it explicitly to run it.
    for s in sys.argv[1:] or ["main50x", "main100", "main200x"]:
        exp = {"name": s, "seeds": SEEDS_500 if s == "main500" else SEEDS, **stage(s)}
        if s == "control":
            exp["base"]["task_rate"] = 1.0
        sweep(exp, Path("results") / s, workers=8,
              progress=lambda i, n, s=s: print(f"{s} {i}/{n}", flush=True) if i % 10 == 0 or i == n else None)
        print("DONE", s, flush=True)
