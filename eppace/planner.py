"""DPPE search: space-time A*.

State is (row, col, t). Step cost
    alpha + beta_i * C(next, t+1) + eps * safety(next)
with C >= 0 counted once. h = alpha * static BFS distance to the goal, which never
overestimates (every step costs >= alpha), so the returned path is optimal for this cost.
Waiting is a move like any other and costs the same step cost.

With `window` set (WHCA*) the search stops at the first node `window` steps deep and returns
the path to it, so only that much is planned and reserved; the heuristic is still the true
distance to the goal.

With `transient` (moving-obstacle cells) and `t_block`, those cells are blocked only for the first
`t_block` steps: an obstacle that moves on is not treated as a wall for the rest of the plan.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np

from .coordination import ReservationTable
from .world import DIRS, Cell, World


@dataclass
class PlanResult:
    status: str                       # ok | no_path | capped
    path: list = field(default_factory=list)   # path[0] is the start cell at t0
    cost: float = 0.0
    steps: int = 0
    congestion: float = 0.0           # sum of C along the path (G(pi))
    safety: float = 0.0               # sum of safety terms (S(pi))
    expanded: int = 0


def plan_path(world: World, blocked: np.ndarray, start: Cell, goal: Cell, t0: int, *,
              alpha: float, beta: float, eps: float, agent: int,
              cong=None, res: ReservationTable | None = None,
              max_expansions: int = 30000, horizon: int | None = None,
              window: int | None = None, transient: set | None = None, t_block: int = 0) -> PlanResult:
    if start == goal:
        return PlanResult("ok", [start], 0.0, 0)
    if blocked[goal]:
        return PlanResult("no_path")
    dist = world.dist_to(goal)
    if dist[start] >= 10**6:
        return PlanResult("no_path")
    H, W = world.H, world.W
    safety = world.safety
    if horizon is None:
        horizon = min(3 * int(dist[start]) + 40, 600)

    h0 = alpha * dist[start]
    open_: list = [(h0, h0, 0, start[0], start[1], t0)]
    best = {(start[0], start[1], t0): 0.0}
    parent: dict = {}
    counter = 0
    expanded = 0
    while open_:
        f, _, _, r, c, t = heapq.heappop(open_)
        g = best.get((r, c, t))
        if g is None:
            continue
        if (r, c) == goal or (window is not None and t - t0 >= window):
            path = [(r, c)]
            key = (r, c, t)
            while key in parent:
                key = parent[key]
                path.append((key[0], key[1]))
            path.reverse()
            cg = sum(float(cong(p[0], p[1], t0 + k)) for k, p in enumerate(path) if k and cong)
            sf = sum(float(safety[p]) for p in path[1:])
            return PlanResult("ok", path, g, len(path) - 1, cg, sf, expanded)
        expanded += 1
        if expanded > max_expansions:
            return PlanResult("capped", expanded=expanded)
        if t - t0 >= horizon:
            continue
        nt = t + 1
        for dr, dc in ((0, 0),) + DIRS:
            rr, cc = r + dr, c + dc
            if not (0 <= rr < H and 0 <= cc < W):
                continue
            if blocked[rr, cc] and not (transient and (rr, cc) in transient and nt - t0 > t_block):
                continue
            if res is not None:
                if not res.vertex_free((rr, cc), nt, agent):
                    continue
                if (dr or dc) and not res.edge_free((r, c), (rr, cc), t, agent):
                    continue
            step = alpha + eps * float(safety[rr, cc])
            if cong is not None:
                step += beta * float(cong(rr, cc, nt))
            ng = g + step
            key = (rr, cc, nt)
            if ng < best.get(key, 1e30) - 1e-12:
                best[key] = ng
                parent[key] = (r, c, t)
                counter += 1
                hh = alpha * float(dist[rr, cc])
                heapq.heappush(open_, (ng + hh, hh, counter, rr, cc, nt))
    return PlanResult("no_path", expanded=expanded)
