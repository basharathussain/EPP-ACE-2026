"""Run configuration and the named variants (baselines and ablations).

A variant is a bundle of feature flags. Everything the experiments sweep lives here,
so a run is fully described by (Config, seed) and the manifest can hash it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields, replace

CLASSES = ("critical", "high", "medium", "low")
CLASS_CONTEXT = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}


@dataclass(frozen=True)
class Flags:
    """Which mechanisms are switched on. One field per ablation axis."""
    congestion: bool = False              # CDS feeds the planner's cost
    congestion_score: str = "refined"     # "refined" | "manuscript"
    predictor: str = "window"             # "window" | "reservation"
    priority_mode: str = "none"           # "none" | "order" | "weight" | "both"
    adaptation: bool = False              # event-driven replanning + weight rule
    coordination: bool = False            # reservation-table planning (space-time)
    adapt_weights: bool = True            # deterministic weight rule (needs adaptation)
    planner: str = "astar_st"             # "astar_st" | "whca" (windowed reservations) | "pibt"
    window_len: int = 8                   # WHCA*: steps planned and reserved ahead
    allocator: str = "default"            # "default" (FIFO / PMF rank) | "slack" (deadline-feasible, base pick) | "slack_near" (deadline-feasible, nearest)
    weights: tuple | None = None          # fixed (alpha, beta, eps) for this variant; None = Config values
    adapt_look: int | None = None         # adaptation: cells of the plan scanned for blockage (None = cfg.lookahead)
    transient_block: int | None = None    # moving obstacles block only the next N steps of a plan (None = for ever)
    laxity: bool = False                  # planning/arbitration order by least laxity (needs priority_order off)
    slack_kappa: float = 1.5              # slack allocator: an agent qualifies if dist * kappa <= time left

    @property
    def priority_order(self) -> bool:
        return self.priority_mode in ("order", "both")

    @property
    def priority_weight(self) -> bool:
        return self.priority_mode in ("weight", "both")


# B1..B3 are the baselines, A1..A6 the ablation ladder from the design doc (5.2, 5.3).
# B2 is an *event-replanning A\** stand-in: a true D* Lite is a v1.1 item.
VARIANTS: dict[str, Flags] = {
    "b1_astar": Flags(),
    "b2_replan": Flags(adaptation=True, adapt_weights=False),
    "b3_prioritized": Flags(coordination=True),
    # Published comparison methods. B3 is Cooperative A* / HCA* (Silver 2005) as it stands.
    "b4_whca": Flags(coordination=True, planner="whca"),
    "b5_pibt": Flags(planner="pibt"),
    # v2 (see _reqm/4_theory_v2.md): slack-aware allocation, laxity ordering, reservation-table congestion.
    # b*_alloc give the published/baseline methods the same allocator so allocation and planning can be separated.
    "b1_alloc": Flags(allocator="slack"),
    "b2_alloc": Flags(adaptation=True, adapt_weights=False, allocator="slack"),
    "b3_alloc": Flags(coordination=True, allocator="slack"),
    "b4_alloc": Flags(coordination=True, planner="whca", allocator="slack"),
    "b5_alloc": Flags(planner="pibt", allocator="slack"),
    "eppace_alloc": Flags(congestion=True, priority_mode="both", adaptation=True, coordination=True,
                          allocator="slack"),
    # v2 ablation rungs: each adds one mechanism to b3_alloc
    "v2_lax": Flags(coordination=True, allocator="slack", laxity=True),
    "v2_cong": Flags(coordination=True, congestion=True, predictor="reservation", allocator="slack"),
    "v2_adapt": Flags(coordination=True, adaptation=True, adapt_weights=False, allocator="slack"),
    "v2_cong_w": Flags(coordination=True, congestion=True, predictor="reservation", allocator="slack",
                       weights=(0.8, 0.1, 0.1)),
    "v2_near": Flags(coordination=True, allocator="slack_near"),
    # EPP-ACE v2: reservation-table congestion at a small weight, priority-scaled, deadline-feasible
    # allocation. Adaptation is a separate rung (eppace2_adapt): on dev seeds it did not pay at overload.
    "eppace2": Flags(congestion=True, predictor="reservation", priority_mode="weight", coordination=True,
                     allocator="slack", weights=(0.8, 0.1, 0.1)),
    "eppace2_adapt": Flags(congestion=True, predictor="reservation", priority_mode="weight", adaptation=True,
                           adapt_weights=False, coordination=True, allocator="slack", weights=(0.8, 0.1, 0.1)),
    # control for the transient-block gain: the same planner change on plain Cooperative A*
    "b3_tb": Flags(coordination=True, allocator="slack", transient_block=4),
    "eppace2_tb": Flags(congestion=True, predictor="reservation", priority_mode="weight", coordination=True,
                        allocator="slack", weights=(0.8, 0.1, 0.1), transient_block=4),
    "eppace2_adapt_tb": Flags(congestion=True, predictor="reservation", priority_mode="weight", adaptation=True,
                              adapt_weights=False, coordination=True, allocator="slack",
                              weights=(0.8, 0.1, 0.1), adapt_look=3, transient_block=4),
    "eppace2_adapt3": Flags(congestion=True, predictor="reservation", priority_mode="weight", adaptation=True,
                            adapt_weights=False, coordination=True, allocator="slack",
                            weights=(0.8, 0.1, 0.1), adapt_look=3),
    "a2_congestion": Flags(congestion=True),
    "a3_priority": Flags(priority_mode="both"),
    "a4_adaptation": Flags(adaptation=True),
    "a5_no_coordination": Flags(congestion=True, priority_mode="both", adaptation=True),
    "eppace": Flags(congestion=True, priority_mode="both", adaptation=True, coordination=True),
    "eppace_res": Flags(congestion=True, predictor="reservation", priority_mode="both",
                        adaptation=True, coordination=True),
    "eppace_manuscript_score": Flags(congestion=True, congestion_score="manuscript",
                                     priority_mode="both", adaptation=True, coordination=True),
}
VARIANTS["a1_astar"] = VARIANTS["b1_astar"]
VARIANTS["a6_full"] = VARIANTS["eppace"]


@dataclass(frozen=True)
class Config:
    name: str = "run"
    seed: int = 0
    variant: str = "eppace"
    # environment
    height: int = 30
    width: int = 30
    obstacle_density: float = 0.15
    map_style: str = "random"   # "random" scattered walls | "rooms" walled rooms joined by doors
    room_size: int = 10
    door_width: int = 3
    n_agents: int = 20
    n_moving_obstacles: int = 3
    steps: int = 300
    # tasks (lifelong Poisson stream)
    task_rate: float = 0.4                       # expected new tasks per step
    assignment: str = "nearest"                  # "nearest" idle agent | "longest_idle" (long trips)
    class_mix: tuple = (0.25, 0.35, 0.30, 0.10)  # critical, high, medium, low
    deadline_factors: tuple = (0.5, 1.0, 2.0)    # x (height + width) steps: tight, medium, relaxed
    # disturbances
    comm_loss: float = 0.0       # fraction of agents that plan with a one-step-stale map
    agent_failure: float = 0.0   # fraction of agents that fail at a seeded time
    # CDS
    rho_max: float = 0.25
    v_max: float = 1.0
    w_spatial: float = 0.6
    w_velocity: float = 0.4
    window: int = 5
    hotspot_threshold: float = 0.6
    # PMF
    w_u: float = 0.3
    w_d: float = 0.1
    w_r: float = 0.2
    w_c: float = 0.4
    urgency_lambda: float = 2.0
    # DPPE (normalised: alpha + beta + eps = 1)
    alpha: float = 0.4
    beta: float = 0.5
    eps: float = 0.1
    max_expansions: int = 30000
    stuck_replan: int = 10
    # adaptation
    replan_threshold: float = 0.05
    lookahead: int = 15
    replan_cooldown: int = 10
    weight_eta: float = 0.05
    # trace
    trace_stride: int = 5
    flags_override: dict = field(default_factory=dict)

    def flags(self) -> Flags:
        if self.variant not in VARIANTS:
            raise ValueError(f"unknown variant {self.variant!r}; have {sorted(VARIANTS)}")
        return replace(VARIANTS[self.variant], **self.flags_override)

    def validate(self) -> None:
        if self.assignment not in ("nearest", "longest_idle"):
            raise ValueError("assignment must be 'nearest' or 'longest_idle'")
        if abs(sum(self.class_mix) - 1) > 1e-9:
            raise ValueError("class_mix must sum to 1")
        if abs(self.alpha + self.beta + self.eps - 1) > 1e-9:
            raise ValueError("alpha + beta + eps must equal 1")
        if abs(self.w_u + self.w_d + self.w_r + self.w_c - 1) > 1e-9:
            raise ValueError("priority weights must sum to 1")
        for k, lo in (("height", 1), ("width", 1), ("n_agents", 1), ("steps", 1),
                      ("n_moving_obstacles", 0), ("window", 1), ("lookahead", 1)):
            if getattr(self, k) < lo:
                raise ValueError(f"{k} must be at least {lo}")
        if self.task_rate < 0:
            raise ValueError("task_rate must be >= 0")
        if self.map_style not in ("random", "rooms"):
            raise ValueError("map_style must be 'random' or 'rooms'")
        if self.room_size < 3 or not 1 <= self.door_width < self.room_size - 1:
            raise ValueError("need room_size >= 3 and 1 <= door_width < room_size - 1")
        if not 0 <= self.obstacle_density < 0.6:
            raise ValueError("obstacle_density out of range")
        self.flags()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        known = {f.name for f in fields(cls)}
        extra = set(d) - known
        if extra:
            raise ValueError(f"unknown config keys: {sorted(extra)}")
        d = dict(d)
        for k in ("class_mix", "deadline_factors"):
            if k in d:
                d[k] = tuple(d[k])
        c = cls(**d)
        c.validate()
        return c

    def digest(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, default=list)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]
