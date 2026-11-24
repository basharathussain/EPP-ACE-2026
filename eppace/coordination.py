"""Coordination: space-time reservations (used when coordination is on) and the
execution-time arbiter (used by EVERY variant).

The arbiter is the common minimum safety rule from the design doc (5.3, A5): no two
agents ever share a cell and no two swap, whatever the planner did. What differs between
variants is how many conflicts the planner leaves for the arbiter to resolve; that count
is reported as `conflicts`, so a baseline is not credited for safety the arbiter provided.
"""
from __future__ import annotations

from collections import defaultdict

from .world import DIRS, Agent, Cell, World


class ReservationTable:
    def __init__(self):
        self.v: dict[tuple, int] = {}
        self.e: dict[tuple, int] = {}
        self.keys: dict[int, list] = defaultdict(list)

    def vertex_free(self, cell: Cell, t: int, agent: int) -> bool:
        o = self.v.get((cell[0], cell[1], t))
        return o is None or o == agent

    def edge_free(self, a: Cell, b: Cell, t: int, agent: int) -> bool:
        """Moving a->b during [t, t+1] conflicts with someone moving b->a in the same slot."""
        o = self.e.get((b[0], b[1], a[0], a[1], t))
        return o is None or o == agent

    def reserve(self, agent: int, path: list, t0: int) -> None:
        self.release(agent)
        ks = self.keys[agent]
        for k, cell in enumerate(path):
            key = (cell[0], cell[1], t0 + k)
            self.v[key] = agent
            ks.append(("v", key))
            if k and path[k - 1] != cell:
                p = path[k - 1]
                ek = (p[0], p[1], cell[0], cell[1], t0 + k - 1)
                self.e[ek] = agent
                ks.append(("e", ek))

    def release(self, agent: int) -> None:
        for kind, key in self.keys.pop(agent, ()):
            tbl = self.v if kind == "v" else self.e
            if tbl.get(key) == agent:
                del tbl[key]

    def density(self, cell: Cell, t: int, agent: int, H: int, W: int) -> float:
        """Reserved agents in the 3x3 neighbourhood of `cell` at time t (excluding `agent`)."""
        n = 0
        r0, c0 = cell
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                o = self.v.get((r0 + dr, c0 + dc, t))
                if o is not None and o != agent:
                    n += 1
        return n / 9.0


def arbitrate(world: World, intents: dict[int, Cell], dyn_blocked, rank: dict[int, tuple]):
    """Resolve one synchronous step. Returns (final positions, events).

    events: list of dicts with kind in {"vertex", "swap", "occupied", "obstacle", "yield"}.
    """
    agents = [a for a in world.agents if a.status != "failed"]
    pos = {a.id: a.pos for a in agents}
    idle = {a.id for a in agents if a.status == "idle"}
    occupant = {p: i for i, p in pos.items()}
    target = {i: intents.get(i, pos[i]) for i in pos}
    events: list[dict] = []
    forced: dict[int, str] = {}

    # moves into a moving obstacle or a dead agent never happen
    for i in list(target):
        if target[i] != pos[i] and target[i] in dyn_blocked:
            target[i] = pos[i]
            forced[i] = "obstacle"
            events.append({"kind": "obstacle", "agent": i, "cell": list(intents[i])})

    order = sorted(pos, key=lambda i: rank[i])
    # idle agents yield to a mover who wants their cell
    targeted = {target[i] for i in pos if target[i] != pos[i]}
    for i in order:
        tgt = target[i]
        if tgt == pos[i]:
            continue
        o = occupant.get(tgt)
        if o is not None and o in idle and target[o] == pos[o]:
            for dr, dc in DIRS:
                n = (tgt[0] + dr, tgt[1] + dc)
                if (0 <= n[0] < world.H and 0 <= n[1] < world.W and world.walkable[n]
                        and n not in dyn_blocked and n not in occupant and n not in targeted):
                    target[o] = n
                    targeted.add(n)
                    events.append({"kind": "yield", "agent": o, "by": i})
                    break

    stay = {i for i in pos if target[i] == pos[i]}
    movers = [i for i in order if target[i] != pos[i]]
    changed = True
    while changed:
        changed = False
        occ_final = {pos[i]: i for i in stay}
        claims: dict[Cell, list[int]] = defaultdict(list)
        for i in movers:
            if i not in stay:
                claims[target[i]].append(i)
        for i in movers:
            if i in stay:
                continue
            tgt, reason = target[i], None
            if tgt in occ_final:
                reason = "occupied"
            elif len(claims[tgt]) > 1 and i != min(claims[tgt], key=lambda x: rank[x]):
                reason = "vertex"
            else:
                j = occupant.get(tgt)
                if j is not None and j not in stay and target[j] == pos[i] and rank[i] > rank[j]:
                    reason = "swap"
            if reason:
                stay.add(i)
                forced[i] = reason
                events.append({"kind": reason, "agent": i, "cell": list(tgt)})
                changed = True
    final = {i: (pos[i] if i in stay else target[i]) for i in pos}
    return final, events, forced
