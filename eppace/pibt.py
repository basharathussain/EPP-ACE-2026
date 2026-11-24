"""PIBT: Priority Inheritance with Backtracking (Okumura, Machida, Defago, Tamura, AIJ 2022).

One synchronous step at a time, no paths and no reservations. Agents are taken in priority
order; each wants the neighbouring cell (or its own) closest to its goal. If a lower-priority
agent stands there, that agent is asked to move first and inherits the asker's priority; if it
cannot, the asker tries its next choice. An agent that finds nothing stays put, which is
always possible because nobody else may take a cell its owner has not left.

Priority is the published lifelong rule: the longer since an agent last reached a goal, the
higher it ranks (ties by id). Idle agents have no goal, rank last and are pushed aside.
Tie-breaking is fixed (N E S W, stay last) so a run is reproducible; the paper breaks ties
at random.
"""
from __future__ import annotations

from .world import DIRS, Cell, World


def decide(world: World, blocked, t: int) -> dict[int, Cell]:
    """Next cell for every agent that should move. `blocked` is the observed obstacle mask."""
    H, W = world.H, world.W
    agents = [a for a in world.agents]
    pos: dict[int, Cell] = {a.id: a.pos for a in agents}
    occupant: dict[Cell, int] = {a.pos: a.id for a in agents}
    by_id = {a.id: a for a in agents}
    nxt: dict[int, Cell] = {}
    claim: dict[Cell, int] = {}

    def candidates(i: int) -> list[Cell]:
        a = by_id[i]
        r, c = pos[i]
        cells = []
        for dr, dc in DIRS:
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and world.walkable[rr, cc] and not blocked[rr, cc]:
                cells.append((rr, cc))
        if a.status == "busy":
            d = world.dist_to(world.tasks[a.task].goal)
            cells.append((r, c))
            return sorted(cells, key=lambda u: (int(d[u]), u == (r, c)))
        return [(r, c)] + cells

    def push(i: int, asker: int | None) -> bool:
        for u in candidates(i):
            if u in claim:
                continue
            if asker is not None and u == pos[asker]:
                continue                      # would swap with the agent that asked
            claim[u] = i
            k = occupant.get(u)
            if k is not None and k != i and k not in nxt:
                if by_id[k].status == "failed" or not push(k, i):
                    del claim[u]
                    continue
            nxt[i] = u
            return True
        nxt[i] = pos[i]
        claim[pos[i]] = i
        return False

    for a in agents:                          # failed agents never move and cannot be pushed
        if a.status == "failed":
            nxt[a.id] = pos[a.id]
            claim[pos[a.id]] = a.id
    order = sorted((a for a in agents if a.status != "failed"),
                   key=lambda a: (0 if a.status == "busy" else 1, a.idle_since, a.id))
    for a in order:
        if a.id not in nxt:
            push(a.id, None)
    return {i: u for i, u in nxt.items() if u != pos[i]}
