import numpy as np
import pytest

from eppace.cds import CDS
from eppace.config import Config, VARIANTS
from eppace.coordination import ReservationTable, arbitrate
from eppace.emm import EMM
from eppace.planner import plan_path
from eppace.pmf import PMF
from eppace.sim import run
from eppace.world import Task, World
from helpers import scenario

STABLE = ("tasks_done", "tcr_on_time", "conflicts", "violations", "mean_density",
          "path_efficiency", "adaptation_time", "replans", "reassigned")


def free_world(rows):
    return World(Config(height=len(rows), width=len(rows[0])), rows)


# ---- reproducibility ------------------------------------------------------------------
@pytest.mark.parametrize("variant", ["b1_astar", "eppace", "b4_whca", "b5_pibt"])
def test_same_seed_same_result(variant):
    cfg = Config(variant=variant, seed=7, steps=120, n_agents=25, n_moving_obstacles=4)
    a, b = run(cfg).metrics, run(cfg).metrics
    for k in STABLE:
        assert a[k] == b[k] or (a[k] != a[k] and b[k] != b[k]), k


def test_different_seed_differs():
    a = run(Config(seed=1, steps=80)).metrics
    b = run(Config(seed=2, steps=80)).metrics
    assert a["tasks_created"] != b["tasks_created"] or a["mean_density"] != b["mean_density"]


# ---- DPPE -----------------------------------------------------------------------------
def test_astar_is_shortest_without_costs():
    w = free_world(["........", "..####..", "........", "........"])
    pr = plan_path(w, w.walls, (0, 0), (3, 7), 0, alpha=1.0, beta=0.0, eps=0.0, agent=0)
    assert pr.status == "ok" and pr.steps == w.dist_to((3, 7))[0, 0]
    assert pr.path[0] == (0, 0) and pr.path[-1] == (3, 7)
    assert all(not w.walls[p] for p in pr.path)
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(pr.path, pr.path[1:]))


def test_no_path_is_reported_not_faked():
    w = free_world(["..#..", "..#..", "..#.."])
    assert plan_path(w, w.walls, (0, 0), (0, 4), 0, alpha=1, beta=0, eps=0, agent=0).status == "no_path"


def test_cost_matches_independent_calculation():
    w = free_world(["....", "...."])
    C = np.zeros((2, 4)); C[0, 1] = 1.0
    pr = plan_path(w, w.walls, (0, 0), (0, 3), 0, alpha=0.4, beta=2.0, eps=0.1, agent=0,
                   cong=lambda r, c, t: C[r, c])
    expect = sum(0.4 + 2.0 * C[p] + 0.1 * float(w.safety[p]) for p in pr.path[1:])
    assert pr.cost == pytest.approx(expect)
    # the cheaper route goes round the congested cell
    assert (0, 1) not in pr.path


def test_priority_scaled_weight_changes_the_route():
    """Finding A: priority matters only through how congestion is weighed."""
    w = free_world(["......", "......"])
    C = np.zeros((2, 6)); C[0, 1:5] = 0.9      # the direct row is congested
    cong = lambda r, c, t: C[r, c]
    hi = plan_path(w, w.walls, (0, 0), (0, 5), 0, alpha=0.4, beta=0.5 * (1 - 0.95), eps=0.0,
                   agent=0, cong=cong)
    lo = plan_path(w, w.walls, (0, 0), (0, 5), 0, alpha=0.4, beta=0.5 * (1 - 0.05), eps=0.0,
                   agent=0, cong=cong)
    assert hi.steps < lo.steps and lo.congestion < hi.congestion


def test_reservation_forces_a_wait():
    w = free_world(["....."])
    res = ReservationTable()
    res.reserve(9, [(0, 2)] * 3, 1)          # someone sits on (0,2) during t=1..3
    pr = plan_path(w, w.walls, (0, 0), (0, 4), 0, alpha=1, beta=0, eps=0, agent=0, res=res)
    assert pr.status == "no_path" or pr.steps > 4  # corridor: must wait it out, never pass through
    for k, p in enumerate(pr.path):
        assert res.vertex_free(p, k, 0)


# ---- arbiter --------------------------------------------------------------------------
def arb(layout, intents, idle=(), priority=None):
    w = free_world(layout)
    for a in w.agents:
        a.status = "idle" if a.id in idle else "busy"
    rank = {a.id: ((2, 0) if a.status == "idle" else (1, a.id)) for a in w.agents}
    return w, *arbitrate(w, intents, frozenset(), rank)


def test_vertex_conflict_one_loses():
    w, final, ev, _ = arb(["0.1"], {0: (0, 1), 1: (0, 1)})
    assert sorted(final.values()) == [(0, 1), (0, 2)] and len(set(final.values())) == 2
    assert [e["kind"] for e in ev] == ["vertex"]


def test_swap_forbidden():
    w, final, ev, _ = arb(["01"], {0: (0, 1), 1: (0, 0)})
    assert final == {0: (0, 0), 1: (0, 1)} or final == {0: (0, 1), 1: (0, 1)} is False
    assert len(set(final.values())) == 2 and any(e["kind"] == "swap" for e in ev)


def test_following_allowed():
    w, final, ev, _ = arb(["01."], {0: (0, 1), 1: (0, 2)})
    assert final == {0: (0, 1), 1: (0, 2)} and not ev


def test_rotation_allowed():
    w, final, ev, _ = arb(["01", "32"], {0: (0, 1), 1: (1, 1), 2: (1, 0), 3: (0, 0)})
    assert not ev and len(set(final.values())) == 4


def test_blocked_follower_cascades():
    w, final, ev, _ = arb(["012."], {0: (0, 1), 1: (0, 2), 2: (0, 3)}, idle=())
    assert final == {0: (0, 1), 1: (0, 2), 2: (0, 3)}


def test_idle_agent_yields():
    w, final, ev, _ = arb(["01.", "..."], {0: (0, 1)}, idle=(1,))
    assert final[0] == (0, 1) and final[1] != (0, 1) and any(e["kind"] == "yield" for e in ev)


# ---- coordination end-to-end -----------------------------------------------------------
def test_crossing_in_open_space_is_planned_conflict_free():
    layout = ["...1...", ".......", ".......", "0......", ".......", "......."]
    # agent 0 goes east along row 3, agent 1 goes south along column 3: paths cross at (3,3)
    tasks = [((3, 6), "high", 0), ((5, 3), "high", 1)]
    on = scenario(layout, tasks, variant="eppace", steps=30).run().metrics
    off = scenario(layout, tasks, variant="b1_astar", steps=30).run().metrics
    assert on["tasks_done"] == off["tasks_done"] == 2
    assert on["violations"] == off["violations"] == 0
    assert on["conflicts"] == 0 and off["conflicts"] > 0


def test_head_on_corridor_with_pocket_is_safe_and_completes():
    """Prioritized planning cannot always avoid the conflict here (known incompleteness);
    the claim is only that execution stays collision-free and both tasks finish."""
    layout = ["##.##", "0...1", "##.##"]
    sim = scenario(layout, [((1, 4), "high", 0), ((1, 0), "high", 1)], variant="eppace")
    r = sim.run()
    assert r.metrics["tasks_done"] == 2 and r.metrics["violations"] == 0


def test_head_on_without_coordination_needs_the_arbiter_and_may_stall():
    layout = ["##.##", "0...1", "##.##"]
    sim = scenario(layout, [((1, 4), "high", 0), ((1, 0), "high", 1)], variant="b1_astar", steps=60)
    r = sim.run()
    assert r.metrics["violations"] == 0                     # the arbiter still keeps it safe
    assert r.metrics["conflicts"] > 0                       # but the planner left conflicts to it


# ---- invariants across all variants ---------------------------------------------------
@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_no_violations_under_stress(variant):
    cfg = Config(variant=variant, seed=3, steps=150, n_agents=60, height=20, width=20,
                 obstacle_density=0.2, n_moving_obstacles=8, task_rate=1.5, agent_failure=0.1,
                 comm_loss=0.2)
    m = run(cfg).metrics
    assert m["violations"] == 0, m["violations_by_kind"]


def test_failed_agent_task_reassigned_only_with_adaptation():
    base = dict(seed=5, steps=200, n_agents=15, agent_failure=0.3, task_rate=0.5)
    on = run(Config(variant="a4_adaptation", **base)).metrics
    off = run(Config(variant="b1_astar", **base)).metrics
    assert on["reassigned"] > 0 and off["reassigned"] == 0


# ---- CDS / PMF / EMM ------------------------------------------------------------------
def test_cds_bounds_empty_and_monotone():
    cfg = Config(height=9, width=9)
    w = World(cfg, ["........."] * 9)
    emm = EMM(w)
    cds = CDS(cfg)
    m = cds.update(emm.snapshot(0))
    assert float(m.now.max()) == 0.0
    from eppace.world import Agent
    scores = []
    for n in (1, 2, 4, 6):
        w.agents = [Agent(i, (3 + i // 3, 3 + i % 3)) for i in range(n)]
        for a in w.agents:
            a.last_moved = False
        scores.append(float(CDS(cfg).update(emm.snapshot(0)).now[4, 4]))
    assert scores == sorted(scores) and 0.0 <= scores[-1] <= 1.0


def test_pmf_priority_ranges_and_urgency():
    cfg = Config()
    pmf = PMF(cfg, cfg.flags())
    tk = Task(0, (0, 0), 0, 100, "critical", 1.0, 1.0)
    low = Task(1, (0, 0), 0, 100, "low", 0.2, 0.0)
    assert 0 <= pmf.priority(low, 0) <= pmf.priority(tk, 0) <= 1
    assert pmf.urgency(tk, 90) > pmf.urgency(tk, 10)
    a, b = Task(2, (0, 0), 0, 50, "high", .5, .5), Task(3, (0, 0), 0, 50, "high", .5, .5)
    a.priority = b.priority = 0.5
    assert pmf.rank_key(a) < pmf.rank_key(b)                 # deterministic tie-break by id


def test_weights_stay_on_simplex_and_bounded():
    r = run(Config(variant="eppace", seed=2, steps=200, n_agents=80, height=15, width=15,
                   task_rate=2.0))
    for e in r.events:
        if e.get("event") == "weights":
            assert e["alpha"] + e["beta"] + e["eps"] == pytest.approx(1.0)
            assert e["alpha"] > 0 and 0.25 - 1e-9 <= e["beta"] <= 0.75 + 1e-9


def test_config_rejects_bad_input():
    with pytest.raises(ValueError):
        Config(alpha=0.5, beta=0.5, eps=0.5).validate()
    with pytest.raises(ValueError):
        Config.from_dict({"nonsense": 1})


# ---- published comparison methods -------------------------------------------------------
def test_whca_plans_only_a_window_and_still_arrives():
    layout = ["0.............", "..............", ".............."]
    sim = scenario(layout, [((2, 13), "high", 0)], variant="b4_whca", steps=60)
    sim.step(0)
    a = sim.world.agents[0]
    assert len(a.plan) - 1 == sim.flags.window_len < 15        # cut at the window, goal is 15 away
    r = sim.run()
    assert r.metrics["tasks_done"] == 1 and r.metrics["violations"] == 0


def test_pibt_head_on_in_a_corridor_stays_safe_but_may_not_finish():
    """PIBT is only guaranteed to finish on maps where every cell lies on a cycle
    (Okumura et al. 2022). A single corridor with a side pocket is not such a map: the agent
    pushed back ends in the dead end. The claim here is safety, not completion."""
    layout = ["##.##", "0...1", "##.##"]
    r = scenario(layout, [((1, 4), "high", 0), ((1, 0), "high", 1)], variant="b5_pibt", steps=60).run()
    assert r.metrics["violations"] == 0


def test_pibt_crossing_needs_no_arbiter_override():
    layout = ["...1...", ".......", ".......", "0......", ".......", "......."]
    r = scenario(layout, [((3, 6), "high", 0), ((5, 3), "high", 1)], variant="b5_pibt", steps=30).run()
    assert r.metrics["tasks_done"] == 2 and r.metrics["violations"] == 0
    assert not [e for e in r.events if e.get("event") == "arb" and e["kind"] in ("vertex", "swap", "occupied")]


def test_pibt_inheritance_pushes_a_lower_priority_agent_aside():
    # agent 1 (idle) stands in the corridor agent 0 needs; the pockets at (0,3) and (2,3) let it step aside
    layout = ["###.#", "0.1..", "###.#"]
    r = scenario(layout, [((1, 4), "high", 0)], variant="b5_pibt", steps=30).run()
    assert r.metrics["tasks_done"] == 1 and r.metrics["violations"] == 0


# ---- v2: slack allocator and laxity order --------------------------------------------
def _alloc_world(variant):
    cfg = Config(variant=variant, height=1, width=40, n_agents=2, n_moving_obstacles=0, steps=1,
                 task_rate=0.0, assignment="longest_idle")
    w = World(cfg, layout=["0" + "." * 38 + "1"])
    return cfg, w


def test_slack_allocator_sends_the_reachable_agent_not_the_longest_idle():
    from eppace.pmf import PMF
    cfg, w = _alloc_world("b3_alloc")
    w.agents[0].idle_since, w.agents[1].idle_since = 0, 5     # agent 0 has idled longer
    from eppace.world import Task
    w.tasks.append(Task(id=0, goal=(0, 2), created=10, deadline=20, cls="high", reward=.5, difficulty=.5))
    pm = PMF(cfg, cfg.flags()); pm.update(w, 10)
    out = pm.assign(w, 10, np.zeros((1, 40), bool))
    assert out == [(0, 0)]    # agent 0 is 2 away; agent 1 is 37 away and cannot make the deadline
    cfg2, w2 = _alloc_world("b3_alloc")
    w2.agents[0].idle_since, w2.agents[1].idle_since = 5, 0   # now agent 1 idled longest but is infeasible
    w2.tasks.append(Task(id=0, goal=(0, 2), created=10, deadline=20, cls="high", reward=.5, difficulty=.5))
    pm2 = PMF(cfg2, cfg2.flags()); pm2.update(w2, 10)
    assert pm2.assign(w2, 10, np.zeros((1, 40), bool)) == [(0, 0)]


def test_default_allocator_unchanged_by_v2():
    from eppace.pmf import PMF
    from eppace.world import Task
    cfg, w = _alloc_world("b3_prioritized")
    w.agents[0].idle_since, w.agents[1].idle_since = 5, 0
    w.tasks.append(Task(id=0, goal=(0, 2), created=10, deadline=20, cls="high", reward=.5, difficulty=.5))
    pm = PMF(cfg, cfg.flags()); pm.update(w, 10)
    assert pm.assign(w, 10, np.zeros((1, 40), bool)) == [(0, 1)]   # longest idle, as before


def test_v2_variants_run_safely_and_deterministically():
    base = dict(height=24, width=24, map_style="rooms", room_size=7, door_width=2, n_agents=20,
                n_moving_obstacles=2, steps=80, task_rate=0.3, assignment="longest_idle", seed=3)
    for v in ("eppace2", "b3_alloc", "b4_alloc", "b5_alloc", "eppace_alloc"):
        a = run(Config(variant=v, **base)).metrics
        b = run(Config(variant=v, **base)).metrics
        assert a["violations"] == 0, v
        assert a["tcr_on_time"] == b["tcr_on_time"] and a["travel_time_efficiency"] == b["travel_time_efficiency"], v
        assert a["miss_alloc"] + a["miss_delay"] + a["miss_unassigned"] == \
            a["tasks_counted"] - round(a["tcr_on_time"] * a["tasks_counted"] / 100), v
