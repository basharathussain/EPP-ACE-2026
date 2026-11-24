"""EPP-ACE v2 held-out campaign (design: _reqm/4_theory_v2.md). Seeds 100-129, never used for tuning.
   python experiments/campaign_v2.py [stage ...]   stages: s0_50 s0_100 s0_200 s1_100 s1_200 s2_100
Writes results/v2_<stage>/runs.csv. No 500-agent stage by design."""
import sys
from pathlib import Path

from eppace.runner import sweep

SEEDS = list(range(100, 130))
BASE = dict(height=60, width=60, map_style="rooms", room_size=9, n_moving_obstacles=5, steps=300,
            assignment="longest_idle")
COMMON = ["b3_prioritized", "b4_whca", "b5_pibt", "b3_alloc", "b4_alloc", "b5_alloc",
          "eppace2", "eppace2_tb", "eppace2_adapt_tb"]
V1 = ["eppace", "eppace_alloc"]        # slow at 200 agents (~100 s a run): only where it is cheap
STAGES = {
    "s0_50": (dict(n_agents=50, task_rate=0.5, door_width=2), COMMON + V1),
    "s0_100": (dict(n_agents=100, task_rate=1.0, door_width=2), COMMON + V1),
    "s0_200": (dict(n_agents=200, task_rate=2.0, door_width=2), COMMON),
    "s1_100": (dict(n_agents=100, task_rate=3.0, door_width=1), COMMON),
    "s1_200": (dict(n_agents=200, task_rate=6.0, door_width=1), COMMON),
    "s2_100": (dict(n_agents=100, task_rate=3.0, door_width=1, n_moving_obstacles=40, agent_failure=0.1), COMMON),
    # S3 "working load": rate 3 tasks per 100 agents per step, doors 2. Chosen on dev seeds 1-5 by ONE rule
    # that does not involve EPP-ACE: Cooperative A* + the allocator completes 97-99.5% (S0 saturates at 100%).
    "s3_50": (dict(n_agents=50, task_rate=1.5, door_width=2), COMMON + V1 + ["b3_tb", "b1_astar", "b2_replan"]),
    "s3_100": (dict(n_agents=100, task_rate=3.0, door_width=2), COMMON + V1 + ["b3_tb", "b1_astar", "b2_replan"]),
    "s3_200": (dict(n_agents=200, task_rate=6.0, door_width=2), COMMON + ["b3_tb", "b1_astar", "b2_replan"]),
}
GRID = dict(door_width=[1, 2], task_rate=[3.0, 4.0], n_moving_obstacles=[5, 20, 40], agent_failure=[0.0, 0.1])
GRID_VARIANTS = ["b3_alloc", "b3_tb", "b4_alloc", "b5_alloc", "eppace2_tb"]

CONTROL = ["b3_tb"] if "--a_star" not in sys.argv else ["b1_alloc", "b2_alloc"]   # added after the first held-out run, same seeds: is transient blocking EPP-ACE-specific?

if __name__ == "__main__":
    if "grid" in sys.argv:        # python experiments/campaign_v2.py grid  -> results/v2_grid (100 agents, 24 conditions)
        exp = {"name": "grid", "seeds": SEEDS, "base": {**BASE, "n_agents": 100}, "variants": GRID_VARIANTS, "grid": GRID}
        sweep(exp, Path("results") / "v2_grid", workers=8,
              progress=lambda i, n: print(f"grid {i}/{n}", flush=True) if i % 100 == 0 or i == n else None)
        print("DONE grid", flush=True)
        raise SystemExit
    for s in [a for a in sys.argv[1:] if not a.startswith("--")] or list(STAGES):
        extra, variants = STAGES[s]
        if "--control" in sys.argv or "--a_star" in sys.argv:
            variants = CONTROL
        exp = {"name": s, "seeds": SEEDS, "base": {**BASE, **extra}, "variants": variants}
        sweep(exp, Path("results") / (f"v2c_{s}" if "--control" in sys.argv else f"v2_{s}") if "--a_star" not in sys.argv else Path("results") / f"v2a_{s}", workers=8,
              progress=lambda i, n, s=s: print(f"{s} {i}/{n}", flush=True) if i % 20 == 0 or i == n else None)
        print("DONE", s, flush=True)
