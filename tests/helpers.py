from dataclasses import replace

from eppace.config import Config
from eppace.sim import Simulation
from eppace.world import Task, World


def scenario(layout, tasks, variant="eppace", steps=60, **kw):
    """Hand-made map; tasks = [(goal_cell, class)] all created at t=0 with a long deadline."""
    cfg = Config(variant=variant, steps=steps, task_rate=0.0, n_moving_obstacles=0,
                 height=len(layout), width=len(layout[0]), **kw)
    w = World(cfg, layout)
    for i, spec in enumerate(tasks):
        goal, cls, *agent = spec
        tk = Task(i, goal, 0, 10**4, cls, 0.5, 0.5)
        w.tasks.append(tk)
        if agent:                      # pre-assign so a test can force a crossing
            a = w.agents[agent[0]]
            tk.state, tk.agent, tk.assigned_at, tk.start = "active", a.id, 0, a.pos
            tk.ref_len = int(w.dist_to(goal)[a.pos])
            a.status, a.task = "busy", i
    return Simulation(cfg, world=w)
