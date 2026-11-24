"""EMM: Environment Monitoring Module.

Maintains the authoritative picture of the environment and hands out an immutable
snapshot. It makes no decisions.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .world import World, Cell


@dataclass(frozen=True)
class Snapshot:
    t: int
    blocked: np.ndarray            # static walls | moving obstacles | failed agents
    obstacle_cells: frozenset      # moving obstacles + failed agents (the dynamic part)
    count: np.ndarray              # agents per cell (all non-failed agents)
    speed_sum: np.ndarray          # sum of last-step speed magnitudes per cell
    positions: dict                # agent id -> cell (all agents, incl. failed)


class EMM:
    def __init__(self, world: World):
        self.world = world
        self.events: list[dict] = []

    def snapshot(self, t: int) -> Snapshot:
        w = self.world
        blocked = w.walls.copy()
        dyn = set(w.obstacles)
        for a in w.agents:
            if a.status == "failed":
                dyn.add(a.pos)
        for r, c in dyn:
            blocked[r, c] = True
        count = np.zeros((w.H, w.W), dtype=np.float32)
        speed = np.zeros((w.H, w.W), dtype=np.float32)
        for a in w.agents:
            if a.status == "failed":
                continue
            count[a.pos] += 1
            speed[a.pos] += 1.0 if a.last_moved else 0.0
        return Snapshot(t, blocked, frozenset(dyn), count, speed, {a.id: a.pos for a in w.agents})
