"""Evaluator: read-only observer. It never touches simulation state.

It receives per-step observations (positions, events, remaining-plan cells, timings) and
computes every metric itself, including its own density measure, so no number depends on
the CDS output that the planner optimises. It also re-checks the safety invariants from
raw positions: any violation is reported, never hidden.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from .config import CLASSES, Config


class Evaluator:
    def __init__(self, cfg: Config, walls: np.ndarray):
        self.cfg, self.walls = cfg, walls
        self.prev_pos: np.ndarray | None = None
        self.prev_status: np.ndarray | None = None
        self.prev_dyn: set = set()
        self.violations = {"vertex": 0, "swap": 0, "teleport": 0, "into_obstacle": 0}
        self.density_mean: list[float] = []
        self.density_peak = 0.0
        self.conflicts = {"vertex": 0, "swap": 0, "occupied": 0}
        self.obstacle_blocks = 0
        self.yields = 0
        self.moves = 0
        self.plan_times: list[float] = []
        self.replans = 0
        self.open_events: dict[int, dict] = {}
        self.closed_durations: list[int] = []
        self.invalidations = 0

    def observe(self, t, pos, status, events, plan_cells, moved_ids, plan_times, dyn_cells, busy_wait):
        """pos: (N,2) int array; status: (N,) 0 idle/1 busy/2 failed; plan_cells: {agent: set}."""
        alive = status != 2
        count = np.zeros(self.walls.shape, dtype=np.float32)
        for (r, c), ok in zip(pos, alive):
            if ok:
                count[r, c] += 1
        rho = ndimage.uniform_filter(count, size=3, mode="constant")
        occ = count > 0
        if occ.any():
            self.density_mean.append(float(rho[occ].mean()))
            self.density_peak = max(self.density_peak, float(rho.max()))
        else:
            self.density_mean.append(0.0)

        # invariants, from raw positions only
        cells = [tuple(p) for p, ok in zip(pos, alive) if ok]
        if len(set(cells)) != len(cells):
            self.violations["vertex"] += len(cells) - len(set(cells))
        self.violations["into_obstacle"] += sum(
            1 for cell in cells if self.walls[cell] or cell in dyn_cells)
        if self.prev_pos is not None:
            both = np.nonzero(alive & (self.prev_status != 2))[0]
            edges = set()
            for i in both:
                a, b = tuple(self.prev_pos[i]), tuple(pos[i])
                if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1:
                    self.violations["teleport"] += 1
                elif a != b:
                    edges.add((a, b))
            self.violations["swap"] += sum(1 for (a, b) in edges if (b, a) in edges) // 2
        for ev in events:
            k = ev["kind"]
            if k in self.conflicts:
                self.conflicts[k] += 1
            elif k == "obstacle":
                self.obstacle_blocks += 1
            elif k == "yield":
                self.yields += 1
        self.moves += len(moved_ids)
        self.plan_times.extend(plan_times)
        self.replans += len(plan_times)

        # invalidation -> recovery (adaptation time): independent of how the system reacts
        new_dyn = dyn_cells - self.prev_dyn
        for i, cells_ahead in plan_cells.items():
            ev = self.open_events.get(i)
            hit = bool(cells_ahead & dyn_cells)
            if ev is None:
                if new_dyn and (cells_ahead & new_dyn):
                    self.open_events[i] = {"t0": t, "moves": 0}
                    self.invalidations += 1
            else:
                if i in moved_ids:
                    ev["moves"] += 1
                if not hit and ev["moves"] >= 3:
                    self.closed_durations.append(t - ev["t0"])
                    del self.open_events[i]
        for i in [i for i in self.open_events if i not in plan_cells]:   # task ended / agent failed
            self.closed_durations.append(t - self.open_events.pop(i)["t0"])
        self.prev_dyn = set(dyn_cells)
        self.prev_pos, self.prev_status = pos.copy(), status.copy()

    def finalize(self, world, steps: int, wall_time: float) -> dict:
        tasks = world.tasks
        counted = [k for k in tasks if k.deadline <= steps or k.state == "done"]
        done = [k for k in counted if k.state == "done"]
        on_time = [k for k in done if k.completed_at <= k.deadline]
        n = max(1, len(counted))
        # reference shortest static path / distance actually travelled (moves, not waits)
        eff = [min(1.0, k.ref_len / k.moves) for k in done if k.ref_len and k.moves]
        lat = [k.completed_at - k.created for k in done]
        # travel-time efficiency: shortest time / actual time from assignment (counts waiting)
        tt = [min(1.0, k.ref_len / max(1, k.completed_at - k.assigned_at)) for k in done
              if k.ref_len and k.assigned_at is not None]
        wts = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        wsum = sum(wts[k.cls] for k in counted)
        wdone = sum(wts[k.cls] for k in on_time)
        # miss decomposition (theory note 1): lost at assignment vs lost in transit
        missed = [k for k in counted if k not in on_time]
        m_unassigned = sum(1 for k in missed if k.assigned_at is None)
        m_alloc = sum(1 for k in missed if k.assigned_at is not None and k.ref_len is not None
                      and k.assigned_at + k.ref_len > k.deadline)
        m_delay = len(missed) - m_unassigned - m_alloc
        per_class = {}
        for cls in CLASSES:
            cc = [k for k in counted if k.cls == cls]
            oc = [k for k in cc if k.state == "done" and k.completed_at <= k.deadline]
            per_class[cls] = 100.0 * len(oc) / len(cc) if cc else float("nan")
        censored = len(open_ := self.open_events)
        dur = self.closed_durations + [steps - e["t0"] for e in open_.values()]
        pt = np.array(self.plan_times) * 1000 if self.plan_times else np.array([0.0])
        busy_waits = sum(a.waits for a in world.agents)
        return {
            "tasks_created": len(tasks), "tasks_counted": len(counted),
            "tasks_censored": len(tasks) - len(counted),
            "tasks_done": len(done), "tasks_late": len(done) - len(on_time),
            "tcr_on_time": 100.0 * len(on_time) / n,
            "completion_rate": 100.0 * len(done) / n,
            "tcr_by_class": per_class,
            "throughput": len(done) / steps,
            "path_efficiency": float(np.mean(eff)) if eff else float("nan"),
            "travel_time_efficiency": float(np.mean(tt)) if tt else float("nan"),
            "tcr_weighted": 100.0 * wdone / max(1, wsum),
            "miss_alloc": m_alloc, "miss_delay": m_delay, "miss_unassigned": m_unassigned,
            "mean_task_latency": float(np.mean(lat)) if lat else float("nan"),
            "makespan": max((k.completed_at for k in done), default=0),
            "mean_wait_per_task": busy_waits / max(1, len(done)),
            "conflicts": sum(self.conflicts.values()), "conflicts_by_kind": dict(self.conflicts),
            "conflict_rate": sum(self.conflicts.values()) / max(1, self.moves),
            "obstacle_blocks": self.obstacle_blocks, "yields": self.yields,
            "violations": sum(self.violations.values()), "violations_by_kind": dict(self.violations),
            "mean_density": float(np.mean(self.density_mean)),
            "peak_density": self.density_peak,
            "invalidations": self.invalidations,
            "adaptation_time": float(np.mean(dur)) if dur else float("nan"),
            "adaptation_censored": censored,
            "replans": self.replans,
            "plan_ms_mean": float(pt.mean()), "plan_ms_p95": float(np.percentile(pt, 95)),
            "reassigned": sum(k.reassigned for k in tasks),
            "wall_time_s": wall_time,
        }
