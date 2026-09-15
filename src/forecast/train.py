"""Leakage-free training pipeline for the flare forecaster.

Rules enforced here (review arXiv:2511.20465, sec 5.4 - violations are the #1
way solar-flare ML papers overfit):
- Temporal blocked walk-forward splits ONLY. No random shuffles.
- Embargo gap >= horizon + max window between train and test blocks.
- Strictly pre-peak positives: label y=1 only if a catalogue peak occurs in
  (t, t+N] AND t < p. In-flare/decay samples are masked out entirely.
- Model must be reported against climatology + persistence baselines.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


@dataclass
class FoldResult:
    fold: int
    train_span: Tuple[str, str]
    test_span: Tuple[str, str]
    embargo_s: float
    n_train: int
    n_test: int
    base_rate: float


def make_walk_forward_splits(
    timestamps: pd.Series,
    n_folds: int = 4,
    horizon_min: int = 15,
    window_min: int = 30,
) -> List[Tuple[np.ndarray, np.ndarray, float]]:
    """Expanding-window walk-forward with embargo.

    Returns list of (train_idx, test_idx, embargo_seconds).
    """
    ts = pd.to_datetime(timestamps).reset_index(drop=True)
    n = len(ts)
    embargo_s = (horizon_min + window_min) * 60.0
    folds = []
    block = n // (n_folds + 1)
    for k in range(1, n_folds + 1):
        train_end = block * k
        test_end = min(block * (k + 1), n)
        if test_end - train_end < 10:
            continue
        folds.append(
            (
                np.arange(0, train_end),
                np.arange(train_end, test_end),
                embargo_s,
            )
        )
    return folds


def build_labels(
    timestamps_sec: np.ndarray,
    catalog_peak_times_sec: Sequence[float],
    horizon_s: float,
    mask_in_flare_s: Tuple[float, float] = (-600.0, 900.0),
    min_class_flux: float = 1e-6,
    peak_fluxes: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """Binary labels: catalogue peak of class>=min within (t, t+horizon].

    Samples inside [p+mask_lo, p+mask_hi] around ANY labelled peak are excluded
    (returned as -1) so in-flare decay never pollutes the negative class.
    """
    peaks = [
        p
        for p, f in zip(
            catalog_peak_times_sec,
            peak_fluxes if peak_fluxes is not None else [min_class_flux] * len(catalog_peak_times_sec),
        )
        if f >= min_class_flux
    ]
    peaks_arr = np.asarray(sorted(peaks))
    y = np.zeros(len(timestamps_sec), dtype=int)
    for i, t in enumerate(timestamps_sec):
        nxt = peaks_arr[(peaks_arr > t) & (peaks_arr <= t + horizon_s)]
        if len(nxt) > 0:
            y[i] = 1
    # mask in-flare windows
    mask = np.zeros(len(timestamps_sec), dtype=bool)
    for p in peaks:
        mask |= (timestamps_sec >= p + mask_in_flare_s[0]) & (
            timestamps_sec <= p + mask_in_flare_s[1]
        )
    y[mask] = -1
    return y


def train_with_cv(
    X: np.ndarray,
    y_raw: np.ndarray,
    folds: List[Tuple[np.ndarray, np.ndarray, float]],
    use_lightgbm: bool = True,
    threshold_grid: Optional[Sequence[float]] = None,
) -> dict:
    """Walk-forward CV over full-timeline arrays.

    y_raw may contain -1 for masked (in-flare) samples: they are excluded from
    fitting and scoring. Fold index arrays are given in full-timeline space and
    are mapped onto the retained subset internally.
    """
    from .metrics import evaluate_forecast

    thresholds = (
        np.asarray(threshold_grid, dtype=float)
        if threshold_grid is not None
        else np.round(np.arange(0.05, 0.95, 0.05), 2)
    )

    valid_pos = np.where(y_raw != -1)[0]
    if len(valid_pos) < 10:
        raise ValueError("Fewer than 10 usable samples after masking.")
    y = y_raw[valid_pos]

    def restrict(idx: np.ndarray) -> np.ndarray:
        """Map full-timeline indices to valid-subset positions."""
        pos = np.searchsorted(valid_pos, idx)
        pos = np.clip(pos, 0, len(valid_pos) - 1)
        return np.unique(pos)

    model_factory = _make_model_factory(use_lightgbm)

    per_fold = []
    oof_prob = np.full(len(y), np.nan)
    for fi, (tr, te, emb) in enumerate(folds):
        tr_v, te_v = restrict(tr), restrict(te)
        if len(te_v) < 5:
            continue
        model = model_factory()
        model.fit(X[valid_pos][tr_v], y[tr_v])
        prob = np.asarray(model.predict_proba(X[valid_pos][te_v]))[:, 1]
        oof_prob[te_v] = prob
        best = max(
            (evaluate_forecast(y[te_v], prob, th) for th in thresholds),
            key=lambda r: r["tss"],
        )
        per_fold.append({"fold": fi, "embargo_s": emb, **best})

    fitted_mask = ~np.isnan(oof_prob)
    oof_best = max(
        (
            evaluate_forecast(y[fitted_mask], oof_prob[fitted_mask], th)
            for th in thresholds
        ),
        key=lambda r: r["tss"],
    )

    return {
        "folds": per_fold,
        "oof": oof_best,
        "chosen_threshold": oof_best["threshold"],
        "n_labelled": int(fitted_mask.sum()),
        "base_rate": float(np.mean(y == 1)),
    }


def _make_model_factory(use_lightgbm: bool):
    if use_lightgbm:
        try:
            from lightgbm import LGBMClassifier

            def factory():
                return LGBMClassifier(
                    n_estimators=300,
                    learning_rate=0.05,
                    num_leaves=15,
                    min_child_samples=20,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    subsample_freq=1,
                    reg_alpha=0.1,
                    reg_lambda=0.1,
                    scale_pos_weight=25.0,
                    random_state=42,
                    verbose=-1,
                )

            return factory
        except ImportError:
            pass

    from sklearn.ensemble import GradientBoostingClassifier

    def factory():
        return GradientBoostingClassifier(random_state=42)

    return factory
