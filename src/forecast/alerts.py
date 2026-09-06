"""Alert rule: k-of-m persistence + hysteresis on the probability stream.

Problem it solves (measured on real GOES data, report Appendix 3): a raw
threshold crossing fires dozens of times per day because the probability
oscillates around the operating point -> event-level FAR ~0.98.

Rule (causal, O(1) per sample):
  ENTER alert when k of the last m probabilities are >= theta_enter
  EXIT  alert when prob < theta_exit for `exit_patience` consecutive samples

Only the ENTER time counts as an "alert" for lead-time accounting; the segment
stays open through the exit lag so one physical precursor yields ONE alert.
NaN probabilities (untrained periods) never enter or sustain an alert.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import math

import numpy as np


@dataclass
class AlertSegment:
    t_open: float
    t_close: Optional[float] = None

    @property
    def open(self) -> bool:
        return self.t_close is None


class AlertEngine:
    """Streaming state machine: update() per sample, segments() after batch."""

    def __init__(
        self,
        theta_enter: float = 0.5,
        theta_exit: Optional[float] = None,
        k: int = 3,
        m: int = 5,
        exit_patience: int = 5,
    ) -> None:
        if not (0.0 <= theta_exit if theta_exit is not None else True):
            raise ValueError("theta_exit must be >= 0")
        if theta_exit is not None and theta_exit > theta_enter:
            raise ValueError("hysteresis requires theta_exit <= theta_enter")
        if k > m:
            raise ValueError("k must be <= m")

        self.theta_enter = float(theta_enter)
        self.theta_exit = (
            float(theta_exit) if theta_exit is not None
            else max(0.0, float(theta_enter) * 0.6)
        )
        self.k = int(k)
        self.m = int(m)
        self.exit_patience = int(exit_patience)

        self._recent: List[bool] = []   # last m ">= theta_enter" booleans
        self._exit_streak = 0
        self._current: Optional[AlertSegment] = None
        self.segments: List[AlertSegment] = []

    # ---------------- streaming API ----------------

    def update(self, prob: float, t_sec: float) -> Optional[str]:
        """Feed one sample. Returns 'OPEN' | 'CLOSE' | None."""
        valid = prob is not None and not (isinstance(prob, float) and math.isnan(prob))

        # --- exit path first (hysteresis band is below enter threshold) ---
        if self._current is not None:
            below = (not valid) or (prob < self.theta_exit)
            self._exit_streak = self._exit_streak + 1 if below else 0
            if self._exit_streak >= self.exit_patience:
                seg = self._current
                seg.t_close = t_sec
                self.segments.append(seg)
                self._current = None
                self._exit_streak = 0
                return "CLOSE"
            return None

        # --- entry path: k-of-m persistence ---
        hit = bool(valid and prob >= self.theta_enter)
        self._recent.append(hit)
        if len(self._recent) > self.m:
            self._recent.pop(0)

        if sum(self._recent) >= self.k:
            self._current = AlertSegment(t_open=t_sec)
            self._recent.clear()
            self._exit_streak = 0
            return "OPEN"

        return None

    def flush(self, t_end: float) -> None:
        """Close any still-open segment at end of stream."""
        if self._current is not None:
            seg = self._current
            seg.t_close = t_end
            self.segments.append(seg)
            self._current = None

    def segments(self) -> List[AlertSegment]:
        """All closed segments (+ current as pending)."""
        out = list(self.segments)
        if self._current is not None:
            out.append(self._current)
        return out

    def reset(self) -> None:
        self._recent.clear()
        self._exit_streak = 0
        self._current = None
        self.segments.clear()


def alerts_by_theta_kofm(
    probs: np.ndarray,
    times_sec: np.ndarray,
    thresholds: Sequence[float],
    k: int = 2,
    m: int = 3,
    exit_frac: float = 0.6,
) -> Dict[float, np.ndarray]:
    """Batch helper: open-times per threshold via the hysteresis engine.

    NaNs (untrained head) are treated as -1 so they never trigger or hold.
    """
    safe = np.nan_to_num(np.asarray(probs, dtype=float), nan=-1.0)
    out: Dict[float, np.ndarray] = {}
    for th in thresholds:
        eng = AlertEngine(theta_enter=float(th), theta_exit=float(th) * exit_frac,
                          k=k, m=m, exit_patience=max(k, 3))
        opens: List[float] = []
        for p, t in zip(safe, times_sec):
            if eng.update(float(p), float(t)) == "OPEN":
                opens.append(float(t))
        out[float(th)] = np.asarray(opens)
    return out
