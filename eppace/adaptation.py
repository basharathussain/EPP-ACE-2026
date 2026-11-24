"""Adaptation: event detection, selective replanning flags, deterministic weight rule.

Reference rule (design doc R2.4): no learning. Weights (alpha, beta, eps) stay on the
simplex and inside [beta0/2, 1.5*beta0]; every change is logged with a version number.
"""
from __future__ import annotations

import numpy as np

from .cds import CongestionMap
from .config import Config, Flags
from .coordination import ReservationTable
from .emm import Snapshot
from .world import World


class Adaptation:
    def __init__(self, cfg: Config, flags: Flags):
        self.cfg, self.flags = cfg, flags
        self.weights = (cfg.alpha, cfg.beta, cfg.eps)
        self.weight_version = 0
        self.prev_C: np.ndarray | None = None
        self.delta = 0.0
        self.log: list[dict] = []

    # -- failures: give the task back, free the reservations -----------------------
    def handle_failures(self, world: World, t: int, res: ReservationTable | None) -> list[int]:
        out = []
        for a in world.agents:
            if a.status == "failed" and a.task is not None:
                tk = world.tasks[a.task]
                tk.state, tk.agent, tk.reassigned = "pending", None, tk.reassigned + 1
                a.task, a.plan = None, []
                if res is not None:
                    res.release(a.id)
                out.append(a.id)
                self.log.append({"t": t, "event": "agent_failure", "agent": a.id, "task": tk.id})
        return out

    # -- which agents must replan ---------------------------------------------------
    def detect(self, world: World, snap: Snapshot, cmap: CongestionMap, t: int) -> dict[int, str]:
        cfg = self.cfg
        C = cmap.now
        self.delta = 0.0 if self.prev_C is None else float(
            np.linalg.norm(C - self.prev_C) / np.sqrt(C.size))
        self.prev_C = C
        flagged: dict[int, str] = {}
        L = self.flags.adapt_look or cfg.lookahead
        for a in world.agents:
            if a.status != "busy" or not a.plan:
                continue
            ahead = a.plan[a.plan_i + 1:a.plan_i + 1 + L]
            if any(c in snap.obstacle_cells for c in ahead):
                flagged[a.id] = "blocked"
                continue
            if (self.flags.congestion and (self.delta > cfg.replan_threshold or cmap.hotspots)
                    and t - a.last_plan_t >= cfg.replan_cooldown
                    and ahead and max(float(cmap.predicted[c]) for c in ahead) > cfg.hotspot_threshold):
                flagged[a.id] = "congestion"
        return flagged

    def update_weights(self, world: World, cmap: CongestionMap, t: int) -> None:
        if not (self.flags.adapt_weights and self.flags.congestion):
            return
        cfg = self.cfg
        a, b, e = self.weights
        frac_hot = len(cmap.hotspots) / max(1, len(world.walkable_cells))
        nb = b
        if frac_hot > 0.05:
            nb = b + cfg.weight_eta
        elif frac_hot < 0.01:
            nb = b - cfg.weight_eta * (1 if b > cfg.beta else -1) if b != cfg.beta else b
        nb = min(1.5 * cfg.beta, max(cfg.beta / 2, nb))   # keeps alpha > 0 so h stays informative
        if abs(nb - b) < 1e-12:
            return
        rest = 1.0 - nb
        base = cfg.alpha + cfg.eps
        self.weights = (rest * cfg.alpha / base, nb, rest * cfg.eps / base)   # keeps alpha:eps ratio
        self.weight_version += 1
        self.log.append({"t": t, "event": "weights", "version": self.weight_version,
                         "alpha": self.weights[0], "beta": nb, "eps": self.weights[2],
                         "frac_hot": frac_hot})
