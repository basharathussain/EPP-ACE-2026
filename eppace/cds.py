"""CDS: Congestion Detection System.

Local density and speed -> congestion score in [0, 1] -> windowed prediction.
Two score definitions are kept side by side (design doc R2.3):
  manuscript:  w_s * D + w_v * Vbar          (mean speed magnitude, not signed sum)
  refined:     w_s * D + w_v * (1 - Vbar)    (slow + dense = congested; empty = 0)
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from .config import Config
from .emm import Snapshot


@dataclass(frozen=True)
class CongestionMap:
    t: int
    now: np.ndarray
    predicted: np.ndarray
    hotspots: tuple          # ((r, c, score), ...)


class CDS:
    def __init__(self, cfg: Config, score: str = "refined", walkable: np.ndarray | None = None):
        self.cfg = cfg
        self.walkable = walkable
        self.score = score
        self.history: deque[np.ndarray] = deque(maxlen=cfg.window)
        self.prev_predicted: np.ndarray | None = None

    def update(self, snap: Snapshot) -> CongestionMap:
        cfg = self.cfg
        # 3x3 neighbourhood, border treated as empty: rho = N(v) / |N(v)|, |N(v)| = 9
        rho = ndimage.uniform_filter(snap.count, size=3, mode="constant")
        n_sum = rho * 9.0
        s_sum = ndimage.uniform_filter(snap.speed_sum, size=3, mode="constant") * 9.0
        with np.errstate(invalid="ignore", divide="ignore"):
            vbar = np.where(n_sum > 1e-9, s_sum / np.maximum(n_sum, 1e-9), 0.0)
        D = np.minimum(1.0, rho / cfg.rho_max)
        V = np.minimum(1.0, vbar / cfg.v_max)
        if self.score == "manuscript":
            C = cfg.w_spatial * D + cfg.w_velocity * V
        else:
            C = cfg.w_spatial * D + cfg.w_velocity * (1.0 - V) * (n_sum > 1e-9)
        C = np.clip(C, 0.0, 1.0).astype(np.float32)
        if self.walkable is not None:
            C = C * self.walkable          # walls carry no congestion
        self.history.append(C)
        hist = list(self.history)[::-1]                       # newest first
        a = np.array([0.5 ** i for i in range(len(hist))])
        a /= a.sum()
        pred = sum(w * h for w, h in zip(a, hist)).astype(np.float32)
        cells = np.argwhere(C >= cfg.hotspot_threshold)
        hot = tuple((int(r), int(c), float(C[r, c])) for r, c in cells)
        return CongestionMap(snap.t, C, pred, hot)
