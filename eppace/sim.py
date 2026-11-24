"""Simulation controller: the synchronous step cycle from the design doc (R3, Timing).

  1 events        obstacles move, tasks arrive, scheduled agent failures
  2 EMM           snapshot
  3 CDS           congestion map (current + predicted)
  4 PMF           priorities, task assignment
  5 Adaptation    failures -> reassign; flag agents whose plan is invalidated
  6 DPPE          plan only agents that need it (space-time A*); Coordination reserves
  7 arbitration   conflict-free synchronous move (all variants)
  8 Evaluator     observe

Adaptation's check (5) sits before planning in the same step rather than after movement:
an event is applied in (1), so detecting it here lets it change this step's routes and
keeps the "immediate safety events interrupt before the action executes" rule.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .adaptation import Adaptation
from .cds import CDS
from .config import Config
from .coordination import ReservationTable, arbitrate
from .emm import EMM
from .evaluator import Evaluator
from .pmf import PMF
from . import pibt
from .planner import plan_path
from .world import World

STATUS = {"idle": 0, "busy": 1, "failed": 2}


@dataclass
class RunResult:
    cfg: Config
    metrics: dict
    trace: dict
    events: list
    tasks: list


class Simulation:
    def __init__(self, cfg: Config, record_trace: bool = False, world: World | None = None):
        cfg.validate()
        self.cfg, self.flags = cfg, cfg.flags()
        self.world = world if world is not None else World(cfg)
        self.emm = EMM(self.world)
        self.cds = CDS(cfg, self.flags.congestion_score, self.world.walkable)
        self.pmf = PMF(cfg, self.flags)
        self.adapt = Adaptation(cfg, self.flags)
        self.res = ReservationTable() if self.flags.coordination else None
        self.evaluator = Evaluator(cfg, self.world.walls)
        self.events: list[dict] = []
        self.record_trace = record_trace
        self._tr = {"pos": [], "status": [], "obs": [], "cong": [], "cong_t": []}
        self.prev_pred: np.ndarray | None = None

    # ------------------------------------------------------------------------------
    def _weights(self):
        if self.flags.weights is not None:
            return self.flags.weights
        return self.adapt.weights if (self.flags.adaptation and self.flags.adapt_weights) \
            else (self.cfg.alpha, self.cfg.beta, self.cfg.eps)

    def _cong_fn(self, agent, cmap):
        if not self.flags.congestion:
            return None
        if self.flags.predictor == "reservation" and self.res is not None:
            H, W, rm, res = self.world.H, self.world.W, self.cfg.rho_max, self.res
            return lambda r, c, t: min(1.0, res.density((r, c), t, agent.id, H, W) / rm)
        m = self.prev_pred if (agent.stale_comm and self.prev_pred is not None) else cmap.predicted
        return lambda r, c, t: m[r, c]

    def _rank(self, a):
        """Arbiter / planning order. Idle agents always lose."""
        if a.status == "idle":
            return (2, 0, 0, 0, a.id)
        if self.flags.laxity and a.task is not None:
            lax = a.deadline - self.world.t - int(self.world.dist_to(self.world.tasks[a.task].goal)[a.pos])
            return (0, 1 if lax < 0 else 0, lax, -a.priority, a.id)
        if self.flags.priority_order:
            return (0, -a.priority, a.deadline, -a.wait_run, a.id)
        return (1, a.id, 0, 0, 0)


    def _plan_pass(self, need, snap, cmap, t, plan_times, pass_no):
        w, cfg, fl = self.world, self.cfg, self.flags
        alpha, beta, eps = self._weights()
        failed = []
        for a, reason in need:
            tk = w.tasks[a.task]
            b_i = beta * (1.0 - a.priority) if (fl.priority_weight and fl.congestion) else beta
            if self.res is not None:
                self.res.release(a.id)
            t0 = time.perf_counter()
            pr = plan_path(w, snap.blocked, a.pos, tk.goal, t, alpha=alpha, beta=b_i, eps=eps,
                           agent=a.id, cong=self._cong_fn(a, cmap), res=self.res,
                           max_expansions=cfg.max_expansions,
                           window=fl.window_len if fl.planner == "whca" else None,
                           transient=set(w.obstacles) if fl.transient_block is not None else None,
                           t_block=fl.transient_block or 0)
            plan_times.append(time.perf_counter() - t0)
            a.last_plan_t = t
            if pr.status == "ok":
                a.plan, a.plan_i, a.plan_t0, a.desync = pr.path, 0, t, False
                a.plan_version += 1
                a.wait_run = 0 if reason != "stuck" else a.wait_run
                if self.res is not None:
                    self.res.reserve(a.id, pr.path, t)
            else:
                a.plan = []
                failed.append((a, reason))
            self.events.append({"t": t, "event": "plan", "agent": a.id, "reason": reason,
                                "pass": pass_no, "status": pr.status, "cost": round(pr.cost, 4),
                                "steps": pr.steps, "congestion": round(pr.congestion, 4),
                                "expanded": pr.expanded, "version": a.plan_version,
                                "weights_v": self.adapt.weight_version,
                                **({"path": pr.path} if self.record_trace and pr.status == "ok" else {})})
        return failed

    # ------------------------------------------------------------------------------
    def step(self, t: int) -> None:
        w, cfg, fl = self.world, self.cfg, self.flags
        w.t = t
        # 1 events
        w.step_obstacles()
        for tk in w.spawn_tasks(t):
            pass
        for a in w.agents:
            if a.fail_at == t and a.status != "failed":
                a.status = "failed"
                self.events.append({"t": t, "event": "failure", "agent": a.id})
        # 2-3
        snap = self.emm.snapshot(t)
        cmap = self.cds.update(snap)
        # 4
        self.pmf.update(w, t)
        # 5
        flagged: dict[int, str] = {}
        if fl.adaptation:
            self.adapt.handle_failures(w, t, self.res)
            flagged = self.adapt.detect(w, snap, cmap, t)
            self.adapt.update_weights(w, cmap, t)
        for tid, aid in self.pmf.assign(w, t, snap.blocked):
            self.events.append({"t": t, "event": "assign", "task": tid, "agent": aid})
        # 6 plan
        need: list = []
        for a in w.agents:
            if a.status != "busy":
                continue
            tk = w.tasks[a.task]
            if not a.plan or (a.plan_i >= len(a.plan) - 1 and a.pos != tk.goal):
                reason = "noplan"
            elif fl.coordination and a.desync:
                reason = "desync"
            elif a.wait_run >= cfg.stuck_replan and t - a.last_plan_t >= cfg.stuck_replan:
                reason = "stuck"
            elif a.id in flagged:
                reason = flagged[a.id]
            elif fl.planner == "whca" and t - a.last_plan_t >= max(1, fl.window_len // 2):
                reason = "window"       # WHCA*: replan every half window
            else:
                continue
            need.append((a, reason))
        if fl.planner == "pibt":
            need = []                   # PIBT keeps no plans: it decides each step below
        need.sort(key=lambda x: self._rank(x[0]))
        plan_times: list[float] = []
        # Prioritized planning is incomplete (an early plan can wall in a later agent, e.g. head-on
        # in a corridor); a failed agent simply retries next step. CBS/PBS is a v1.1 item.
        self._plan_pass(need, snap, cmap, t, plan_times, 1)
        # 7 move
        intents = {}
        if fl.planner == "pibt":
            # One timing entry per busy agent (the fleet's decision time shared out), so the
            # plan-time metric stays "cost of one agent's decision" as for the other variants.
            t0 = time.perf_counter()
            intents = pibt.decide(w, snap.blocked, t)
            busy = sum(1 for a in w.agents if a.status == "busy")
            if busy:
                plan_times.extend([(time.perf_counter() - t0) / busy] * busy)
        for a in w.agents:
            if fl.planner != "pibt" and a.status == "busy" and a.plan and a.plan_i + 1 < len(a.plan):
                intents[a.id] = a.plan[a.plan_i + 1]
        rank = {a.id: self._rank(a) for a in w.agents if a.status != "failed"}
        final, events, forced = arbitrate(w, intents, snap.obstacle_cells, rank)
        for ev in events:
            ev.update({"t": t, "event": "arb"})
        self.events.extend(events)
        moved_ids = set()
        for a in w.agents:
            if a.status == "failed":
                a.last_moved = False
                continue
            new = final[a.id]
            moved = new != a.pos
            if moved:
                moved_ids.add(a.id)
                a.moves += 1
            a.last_moved = moved
            a.pos = new
            if a.status == "busy":
                tk = w.tasks[a.task]
                if moved:
                    tk.moves += 1
                else:
                    a.waits += 1
                a.wait_run = 0 if moved else a.wait_run + 1
                want = intents.get(a.id)
                if want is not None:
                    if new == want:
                        a.plan_i += 1
                    else:
                        a.desync = True
                if a.pos == tk.goal:
                    tk.state, tk.completed_at = "done", t + 1
                    self.events.append({"t": t + 1, "event": "done", "task": tk.id, "agent": a.id,
                                        "on_time": t + 1 <= tk.deadline})
                    a.status, a.task, a.plan, a.plan_i = "idle", None, [], 0
                    a.idle_since = t + 1
                    if self.res is not None:
                        self.res.release(a.id)
        self.prev_pred = cmap.predicted
        # 8 observe
        pos = np.array([a.pos for a in w.agents], dtype=np.int16)
        status = np.array([STATUS[a.status] for a in w.agents], dtype=np.int8)
        L = cfg.lookahead
        plan_cells = {a.id: set(a.plan[a.plan_i + 1:a.plan_i + 1 + L]) for a in w.agents
                      if a.status == "busy" and a.plan}
        dyn = set(w.obstacles) | {a.pos for a in w.agents if a.status == "failed"}
        self.evaluator.observe(t, pos, status, events, plan_cells, moved_ids, plan_times, dyn, None)
        if self.record_trace:
            self._tr["pos"].append(pos)
            self._tr["status"].append(status)
            self._tr["obs"].append(np.array(w.obstacles, dtype=np.int16).reshape(-1, 2))
            if t % cfg.trace_stride == 0:
                self._tr["cong"].append(cmap.now.astype(np.float16))
                self._tr["cong_t"].append(t)

    def run(self) -> RunResult:
        t0 = time.perf_counter()
        for t in range(self.cfg.steps):
            self.step(t)
        wall = time.perf_counter() - t0
        m = self.evaluator.finalize(self.world, self.cfg.steps, wall)
        m["weight_versions"] = self.adapt.weight_version
        trace = {}
        if self.record_trace:
            trace = {"pos": np.stack(self._tr["pos"]), "status": np.stack(self._tr["status"]),
                     "obstacles": self._tr["obs"], "cong": np.stack(self._tr["cong"]),
                     "cong_t": np.array(self._tr["cong_t"]), "walls": self.world.walls}
        tasks = [{"id": k.id, "goal": list(k.goal), "created": k.created, "deadline": k.deadline,
                  "cls": k.cls, "state": k.state, "agent": k.agent, "completed_at": k.completed_at,
                  "priority": round(k.priority, 4), "ref_len": k.ref_len, "moves": k.moves,
                  "assigned_at": k.assigned_at}
                 for k in self.world.tasks]
        return RunResult(self.cfg, m, trace, self.events + self.adapt.log, tasks)


def run(cfg: Config, record_trace: bool = False) -> RunResult:
    return Simulation(cfg, record_trace).run()
