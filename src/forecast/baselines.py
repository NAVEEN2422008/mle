"""Mandatory baseline forecasters (review arXiv:2511.20465, sec 5.5).

Any ML model must beat BOTH of these on TSS/HSS/BSS or it is worthless:
- ClimatologyBase: always predict the historical base rate.
- PersistenceBase: "flaring now => predict flare soon", with decayed weight.

Both are causal (use only information available at prediction time).
"""
from __future__ import annotations

from typing import Sequence, Union

import numpy as np


class ClimatologyBase:
    """Predict the training-set base rate as a constant probability."""

    def __init__(self) -> None:
        self.base_rate = 0.0

    def fit(self, y_train: Union[Sequence[int], np.ndarray]) -> "ClimatologyBase":
        self.base_rate = float(np.mean(y_train)) if len(y_train) else 0.0
        return self

    def predict_proba(self, n: int) -> np.ndarray:
        return np.full(n, self.base_rate, dtype=float)


class PersistenceBase:
    """If a flare occurred within the last `memory_s`, predict elevated prob.

    Probability decays exponentially with time since the last flare:
        p(t) = p_max * exp(-age / tau)
    This is the operational NOAA-style 'it's active today' rule and is
    famously difficult to beat at 24h horizons - hence mandatory here.
    """

    def __init__(self, p_max: float = 0.6, tau_s: float = 3 * 3600.0) -> None:
        self.p_max = p_max
        self.tau_s = tau_s

    def predict_proba(self, seconds_since_last_flare: Union[Sequence[float], np.ndarray]) -> np.ndarray:
        ages = np.asarray(seconds_since_last_flare, dtype=float)
        never = ~np.isfinite(ages) | (ages < 0)
        p = self.p_max * np.exp(-ages / self.tau_s)
        p[never] = 0.02  # quiet-Sun floor
        return p


def compare_to_baselines(
    y_true: Union[Sequence[int], np.ndarray],
    model_probs: Union[Sequence[float], np.ndarray],
    climatology: Union[Sequence[float], np.ndarray],
    persistence: Union[Sequence[float], np.ndarray],
    threshold: float = 0.5,
) -> dict:
    """Evaluate model vs both baselines at a common threshold."""
    from .metrics import evaluate_forecast

    return {
        "model": evaluate_forecast(y_true, model_probs, threshold),
        "climatology": evaluate_forecast(y_true, climatology, threshold),
        "persistence": evaluate_forecast(y_true, persistence, threshold),
        "model_beats_climatology_tss": None,  # filled below
    }


def beats_baselines(report: dict) -> bool:
    m = report["model"]["tss"]
    return (
        m > report["climatology"]["tss"]
        and m > report["persistence"]["tss"]
    )
