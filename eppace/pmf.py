"""PMF: Priority Management Framework.

P(T) = w_u U + w_d D + w_r R + w_c C, all terms in [0, 1], weights sum to 1.
U is the manuscript's time-decay urgency; ties broken deterministically.
"""
from __future__ import annotations

import math

import numpy as np

from .config import Config, Flags
from .world import World, Task


class PMF:
    def __init__(self, cfg: Config, flags: Flags):
        self.cfg, self.flags = cfg, flags

    def urgency(self, task: Task, t: int) -> float:
        span = max(1, task.deadline - task.created)
        frac = min(1.0, max(0.0, (task.deadline - t) / span))   # 1 at creation, 0 at deadline
        return math.exp(-self.cfg.urgency_lambda * frac)

    def priority(self, task: Task, t: int) -> float:
        c = self.cfg
        p = (c.w_u * self.urgency(task, t) + c.w_d * task.difficulty
             + c.w_r * task.reward + c.w_c * World.context(task))
        return min(1.0, max(0.0, p))

    def rank_key(self, task: Task, wait: int = 0):
        # higher priority first; then earlier deadline, longer wait, lower id
        return (-task.priority, task.deadline, -wait, task.id)

    def update(self, world: World, t: int) -> None:
        for task in world.tasks:
            if task.state in ("pending", "active"):
                task.priority = self.priority(task, t)
        for a in world.agents:
            if a.status == "busy" and a.task is not None:
                tk = world.tasks[a.task]
                a.priority, a.deadline = tk.priority, tk.deadline

    def assign(self, world: World, t: int, blocked: np.ndarray) -> list[tuple[int, int]]:
        """Greedy: tasks in rank order each take the nearest idle agent. Returns (task, agent)."""
        idle = [a for a in world.agents if a.status == "idle"]
        pending = [tk for tk in world.tasks if tk.state == "pending"]
        if not idle or not pending:
            return []
        if self.flags.priority_order or self.flags.priority_weight:
            pending.sort(key=lambda tk: self.rank_key(tk, t - tk.created))
        else:
            pending.sort(key=lambda tk: (tk.created, tk.id))     # FIFO when PMF is off
        pos = np.array([a.pos for a in idle])
        alive = np.ones(len(idle), dtype=bool)
        if self.flags.allocator in ("slack", "slack_near"):
            return self._assign_slack(world, t, blocked, idle, pending, pos, alive)
        out = []
        for tk in pending:
            if not alive.any():
                break
            if blocked[tk.goal]:
                continue
            if self.cfg.assignment == "longest_idle":
                d = np.array([a.idle_since for a in idle])      # earliest idle first
            else:
                d = np.abs(pos[:, 0] - tk.goal[0]) + np.abs(pos[:, 1] - tk.goal[1])
            d = np.where(alive, d, 10**9)
            j = int(np.argmin(d))            # argmin returns the first minimum: lowest index
            if d[j] >= 10**9:
                break
            self._give(world, t, tk, idle[j], out)
            alive[j] = False
        return out

    def _give(self, world, t, tk, a, out):
        tk.state, tk.agent, tk.assigned_at, tk.start = "active", a.id, t, a.pos
        tk.ref_len = int(world.dist_to(tk.goal)[a.pos])
        a.status, a.task = "busy", tk.id
        a.plan, a.plan_i, a.desync, a.wait_run = [], 0, False, 0
        a.priority, a.deadline = tk.priority, tk.deadline
        out.append((tk.id, a.id))

    def _assign_slack(self, world, t, blocked, idle, pending, pos, alive):
        """Deadline-feasible allocation (design doc v2, M1). Tasks in least-laxity order; each takes,
        among the idle agents that can reach it with margin (dist * kappa <= time left), the one the
        base rule would pick (longest idle, or nearest); if none can, the nearest agent. Tasks no
        idle agent can reach in time go last, so they do not take an agent a savable task needs."""
        kappa = self.flags.slack_kappa
        idle_since = np.array([a.idle_since for a in idle])
        rows = []
        for tk in pending:
            if blocked[tk.goal]:
                continue
            d = world.dist_to(tk.goal)[pos[:, 0], pos[:, 1]].astype(np.int64)
            left = tk.deadline - t
            lax = left - int(d.min())
            rows.append((1 if lax < 0 else 0, lax, -tk.priority, tk.id, tk, d, left))
        rows.sort(key=lambda r: r[:4])
        out = []
        for _, _, _, _, tk, d, left in rows:
            if not alive.any():
                break
            ok = alive & (d * kappa <= left) & (d < 10**6)
            if ok.any():
                key = idle_since if (self.cfg.assignment == "longest_idle" and self.flags.allocator == "slack") else d
                j = int(np.argmin(np.where(ok, key, 10**9)))
            else:
                j = int(np.argmin(np.where(alive, d, 10**9)))
                if d[j] >= 10**6:
                    continue
            self._give(world, t, tk, idle[j], out)
            alive[j] = False
        return out
