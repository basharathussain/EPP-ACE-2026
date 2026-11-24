"""The simulated world: static map, moving obstacles, agents, tasks.

The world owns state and applies state changes. It makes no planning decisions
(that is the point of EMM being separate from DPPE).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from .config import CLASSES, CLASS_CONTEXT, Config

DIRS = ((-1, 0), (0, 1), (1, 0), (0, -1))  # N E S W: fixed order => deterministic tie-breaks
Cell = tuple[int, int]


@dataclass
class Task:
    id: int
    goal: Cell
    created: int
    deadline: int
    cls: str
    reward: float
    difficulty: float
    state: str = "pending"        # pending | active | done | lost
    agent: int | None = None
    assigned_at: int | None = None
    start: Cell | None = None
    completed_at: int | None = None
    ref_len: int | None = None    # static shortest path length at assignment (for path efficiency)
    reassigned: int = 0
    moves: int = 0
    priority: float = 0.0


@dataclass
class Agent:
    id: int
    pos: Cell
    status: str = "idle"          # idle | busy | failed
    task: int | None = None
    plan: list = field(default_factory=list)   # plan[k] = cell at plan_t0 + k
    plan_i: int = 0
    plan_t0: int = 0
    plan_version: int = 0
    desync: bool = False
    stale_comm: bool = False
    fail_at: int | None = None
    wait_run: int = 0             # consecutive steps without moving while busy
    last_plan_t: int = -10**9
    last_moved: bool = False
    idle_since: int = 0
    moves: int = 0
    waits: int = 0
    priority: float = 0.5
    deadline: int = 10**9


class World:
    def __init__(self, cfg: Config, layout: list[str] | None = None):
        """`layout` (rows of '#' wall, '.' free, digits = agent id) builds a hand-made map for
        tests and fixed scenarios; the map RNG is then not used and no obstacles are placed."""
        self.cfg = cfg
        ss = np.random.SeedSequence(cfg.seed)
        s_map, s_task, s_event, s_agent = ss.spawn(4)
        self.rng_map = np.random.default_rng(s_map)
        self.rng_task = np.random.default_rng(s_task)
        self.rng_event = np.random.default_rng(s_event)
        self.rng_agent = np.random.default_rng(s_agent)
        self.t = 0
        self._dist_cache: dict[Cell, np.ndarray] = {}
        self.tasks: list[Task] = []
        self.agents: list[Agent] = []
        if layout is not None:
            self.H, self.W = len(layout), len(layout[0])
            walls = np.array([[ch == "#" for ch in row] for row in layout])
            self.walls, self.walkable = walls, ~walls
            self.walkable_cells = [tuple(map(int, rc)) for rc in np.argwhere(~walls)]
            placed = sorted((int(ch), (r, c)) for r, row in enumerate(layout)
                            for c, ch in enumerate(row) if ch.isdigit())
            self.agents = [Agent(i, pos) for i, pos in placed]
            self.obstacles = []
        else:
            self.H, self.W = cfg.height, cfg.width
            self._build_map()
            self._place_agents()
            self.obstacles = self._place_obstacles()
        self.safety = self._safety_map()

    # ---- static map -------------------------------------------------------------
    def _build_map(self) -> None:
        if self.cfg.map_style == "rooms":
            blocked = self._rooms()
        else:
            blocked = self.rng_map.random((self.H, self.W)) < self.cfg.obstacle_density
        lab, n = ndimage.label(~blocked)  # 4-connectivity by default
        if n == 0:
            raise ValueError("map has no free cells")
        sizes = ndimage.sum(~blocked, lab, index=range(1, n + 1))
        keep = lab == (1 + int(np.argmax(sizes)))
        self.walkable = keep  # free cells outside the largest component become walls
        self.walls = ~keep
        self.walkable_cells = [tuple(map(int, rc)) for rc in np.argwhere(keep)]

    def _rooms(self) -> np.ndarray:
        """Wall lines every room_size cells; each wall segment gets one door_width gap at a
        seeded position. Doors are the only way between rooms, so they are the bottlenecks."""
        n, d = self.cfg.room_size, self.cfg.door_width
        g = np.zeros((self.H, self.W), bool)
        g[n::n + 1, :] = True
        g[:, n::n + 1] = True
        rows, cols = list(range(n, self.H, n + 1)), list(range(n, self.W, n + 1))
        for r in rows:
            for c0 in range(0, self.W, n + 1):
                c = c0 + int(self.rng_map.integers(0, max(1, n - d + 1)))
                g[r, c:c + d] = False
        for c in cols:
            for r0 in range(0, self.H, n + 1):
                r = r0 + int(self.rng_map.integers(0, max(1, n - d + 1)))
                g[r:r + d, c] = False
        return g

    def _safety_map(self) -> np.ndarray:
        """1 on walkable cells that touch a static wall: the manuscript's S(pi) term."""
        pad = np.pad(self.walls, 1, constant_values=True)
        near = np.zeros_like(self.walls)
        for dr, dc in DIRS:
            near |= pad[1 + dr:1 + dr + self.H, 1 + dc:1 + dc + self.W]
        return (near & self.walkable).astype(np.float32)

    def dist_to(self, goal: Cell) -> np.ndarray:
        """BFS distance to `goal` over the static map (admissible heuristic basis)."""
        d = self._dist_cache.get(goal)
        if d is not None:
            return d
        d = np.full((self.H, self.W), 10**6, dtype=np.int32)
        d[goal] = 0
        q = deque([goal])
        while q:
            r, c = q.popleft()
            nd = d[r, c] + 1
            for dr, dc in DIRS:
                rr, cc = r + dr, c + dc
                if 0 <= rr < self.H and 0 <= cc < self.W and self.walkable[rr, cc] and d[rr, cc] > nd:
                    d[rr, cc] = nd
                    q.append((rr, cc))
        if len(self._dist_cache) > 1024:
            self._dist_cache.pop(next(iter(self._dist_cache)))
        self._dist_cache[goal] = d
        return d

    # ---- agents / obstacles ------------------------------------------------------
    def _place_agents(self) -> None:
        cells = self.walkable_cells
        n = min(self.cfg.n_agents, len(cells))
        idx = self.rng_agent.choice(len(cells), size=n, replace=False)
        self.agents = [Agent(i, cells[j]) for i, j in enumerate(idx)]
        nfail = int(round(self.cfg.agent_failure * n))
        if nfail:
            for i in self.rng_agent.choice(n, size=nfail, replace=False):
                self.agents[int(i)].fail_at = int(self.rng_agent.integers(self.cfg.steps // 10 + 1,
                                                                           max(self.cfg.steps // 10 + 2, self.cfg.steps * 3 // 4)))
        nstale = int(round(self.cfg.comm_loss * n))
        if nstale:
            for i in self.rng_agent.choice(n, size=nstale, replace=False):
                self.agents[int(i)].stale_comm = True

    def _place_obstacles(self) -> list[Cell]:
        taken = {a.pos for a in self.agents}
        free = [c for c in self.walkable_cells if c not in taken]
        k = min(self.cfg.n_moving_obstacles, len(free))
        idx = self.rng_event.choice(len(free), size=k, replace=False) if k else []
        return [free[j] for j in idx]

    def step_obstacles(self) -> None:
        """Seeded random walk. Obstacles never enter a cell holding an agent."""
        occupied = {a.pos for a in self.agents}
        taken = set(self.obstacles)
        out = []
        for pos in self.obstacles:
            taken.discard(pos)
            options = []
            for dr, dc in DIRS:
                rr, cc = pos[0] + dr, pos[1] + dc
                if 0 <= rr < self.H and 0 <= cc < self.W and self.walkable[rr, cc] \
                        and (rr, cc) not in occupied and (rr, cc) not in taken:
                    options.append((rr, cc))
            new = options[int(self.rng_event.integers(len(options)))] if options else pos
            taken.add(new)
            out.append(new)
        self.obstacles = out

    # ---- tasks -------------------------------------------------------------------
    def spawn_tasks(self, t: int) -> list[Task]:
        cfg = self.cfg
        out = []
        for _ in range(int(self.rng_task.poisson(cfg.task_rate))):
            cls = CLASSES[int(self.rng_task.choice(len(CLASSES), p=cfg.class_mix))]
            factor = cfg.deadline_factors[int(self.rng_task.integers(len(cfg.deadline_factors)))]
            goal = self.walkable_cells[int(self.rng_task.integers(len(self.walkable_cells)))]
            task = Task(
                id=len(self.tasks), goal=goal, created=t,
                deadline=t + int(np.ceil(factor * (self.H + self.W))), cls=cls,
                reward=float(self.rng_task.uniform(0.2, 1.0)),
                difficulty=float(self.rng_task.uniform(0.0, 1.0)),
            )
            self.tasks.append(task)
            out.append(task)
        return out

    @staticmethod
    def context(task: Task) -> float:
        return CLASS_CONTEXT[task.cls]
