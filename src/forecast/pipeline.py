"""End-to-end forecast pipeline: causal features -> labels -> CV -> numbers.

Causality guarantees (WS3b contract):
- All features use TRAILING windows only (pandas rolling is trailing by
  default) -> no future leakage.
- Labels come from catalogue peak times; a sample at t is positive iff a
  qualifying peak falls in (t, t+horizon] AND t < p. Samples inside any
  flare's [p-10min, p+15min] window are masked (-1) out of training.
- Evaluation is out-of-fold only; baselines are mandatory comparators.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .metrics import evaluate_forecast, lt_vs_far_curve
from .baselines import ClimatologyBase, PersistenceBase, beats_baselines
from .train import build_labels, make_walk_forward_splits, train_with_cv


# --------------------------------------------------------------------------
# Causal feature builder (vectorized, trailing windows)
# --------------------------------------------------------------------------

FEATURE_NAMES = [
    "log_sxr", "log_hxr",
    "sxr_over_base", "hxr_over_base",
    "sxr_slope_short", "sxr_slope_long", "slope_accel",
    "hxr_slope_short",
    "hardness", "d_hardness",
    "run_diff_hxr",            # HOPE-style running difference (impulsive onset)
    "run_diff_sxr",            # HOPE-style running difference for SXR
    "temp_proxy",              # HOPE-style temperature proxy (HXR/SXR ratio)
    "d_temp_proxy",            # HOPE-style dT/dt
    "em_proxy",                # HOPE-style emission measure proxy
    "d_em_proxy",              # HOPE-style dEM/dt
    "sxr_var_short",
    "burst_flag",
    "neupert_corr",            # corr(H, dSXR/dt) over trailing window
    "neupert_resid",           # residual after Neupert model
    "hxr_leads_flag",          # HXR leads SXR flag
    "time_since_flare_min",    # history context
    "decayed_history",         # sum exp(-age/tau) over past flares
]


def build_causal_features(
    df: pd.DataFrame,
    flare_times_sec: Sequence[float],
    short_s: int = 60,
    long_s: int = 600,
    neupert_win_s: int = 120,
    burst_sigma: float = 5.0,
    tau_history_s: float = 6 * 3600.0,
) -> pd.DataFrame:
    """Compute FEATURE_NAMES columns from df(timestamp, soft, hard).

    `flare_times_sec` feeds the two history features; pass detected catalogue
    peaks (not ground truth) in production to keep labels/features consistent.
    """
    ts = pd.to_datetime(df["timestamp"])
    s = pd.to_numeric(df["soft"], errors="coerce").astype(float).clip(lower=0.0)
    h = pd.to_numeric(df["hard"], errors="coerce").astype(float).clip(lower=0.0)

    f = pd.DataFrame(index=df.index)

    f["log_sxr"] = np.log10(s + 1e-9)
    f["log_hxr"] = np.log10(h + 1e-9)

    base_s = s.rolling(long_s, min_periods=1).median()
    base_h = h.rolling(long_s, min_periods=1).median()
    f["sxr_over_base"] = (s / base_s.replace(0, np.nan)).fillna(1.0)
    f["hxr_over_base"] = (h / base_h.replace(0, np.nan)).fillna(1.0)

    ds = s.diff()
    f["sxr_slope_short"] = s.diff(short_s) / short_s
    f["sxr_slope_long"] = s.diff(long_s) / long_s
    f["slope_accel"] = f["sxr_slope_short"] - f["sxr_slope_long"]
    f["hxr_slope_short"] = h.diff(short_s) / short_s

    f["hardness"] = (h / s.replace(0, np.nan)).fillna(0.0)
    f["d_hardness"] = f["hardness"].diff().fillna(0.0)

    f["run_diff_hxr"] = h.diff(neupert_win_s // 2).fillna(0.0)
    f["run_diff_sxr"] = s.diff(neupert_win_s // 2).fillna(0.0)

    # HOPE-style temperature proxy: HXR/SXR ratio (spectral hardening)
    f["temp_proxy"] = (h / s.replace(0, np.nan)).fillna(0.0)
    f["d_temp_proxy"] = f["temp_proxy"].diff().fillna(0.0)

    # HOPE-style emission measure proxy: EM ~ SXR * HXR (simplified)
    f["em_proxy"] = (s * h).replace(0, np.nan).fillna(0.0)
    f["d_em_proxy"] = f["em_proxy"].diff().fillna(0.0)

    f["sxr_var_short"] = s.rolling(short_s, min_periods=5).var().fillna(0.0)

    mu_h = h.rolling(short_s, min_periods=5).mean()
    sd_h = h.rolling(short_s, min_periods=5).std().replace(0, np.nan)
    f["burst_flag"] = (h > mu_h + burst_sigma * sd_h).astype(float).fillna(0.0)

    dSdt = ds.fillna(0.0).rolling(3, min_periods=1).mean()  # smooth derivative
    mp = max(3, min(20, neupert_win_s // 2))
    f["neupert_corr"] = (
        h.rolling(neupert_win_s, min_periods=mp).corr(dSdt).fillna(0.0).clip(-1, 1)
    )

    # Neupert residual: dSXR/dt - predicted from HXR (Neupert model)
    neupert_model = h * 0.19  # simplified Neupert scaling
    f["neupert_resid"] = (dSdt - neupert_model).fillna(0.0)

    # HXR leads SXR flag: HXR onset precedes SXR onset
    hxr_onset = (h.diff(5) > h.diff(5).rolling(60, min_periods=5).std() * 5).astype(int)
    sxr_onset = (s.diff(5) > s.diff(5).rolling(60, min_periods=5).std() * 5).astype(int)
    f["hxr_leads_flag"] = (hxr_onset.shift(5) > sxr_onset).astype(int).fillna(0)

    peaks = np.asarray(sorted(flare_times_sec), dtype=float)
    tsec = (ts - ts.iloc[0]).dt.total_seconds().to_numpy()

    if len(peaks):
        idx = np.searchsorted(peaks, tsec, side="right") - 1
        age = np.where(idx >= 0, tsec - peaks[np.clip(idx, 0, len(peaks) - 1)], np.inf)
        # decayed history: causal prefix loop (fine for <= few 100k rows)
        dec = np.zeros(len(tsec))
        j = 0
        for i, t in enumerate(tsec):
            while j < len(peaks) and peaks[j] <= t:
                j += 1
            if j > 0:
                dec[i] = np.exp(-(t - peaks[:j]) / tau_history_s).sum()
        f["time_since_flare_min"] = np.where(np.isfinite(age), age, np.nan) / 60.0
        f["decayed_history"] = dec
    else:
        f["time_since_flare_min"] = np.nan
        f["decayed_history"] = 0.0

    return f[FEATURE_NAMES]


def alert_crossing_times(
    prob: np.ndarray, times_sec: np.ndarray, thresholds: Sequence[float]
) -> Dict[float, np.ndarray]:
    """Upward threshold crossings -> alert times per threshold (causal rule).

    NaN probabilities (untrained / uncovered periods) never generate alerts.
    """
    safe = np.nan_to_num(prob, nan=-1.0)
    out = {}
    for th in thresholds:
        cur = safe >= th
        crossings = np.where(cur & ~np.roll(cur, 1))[0]
        if len(cur) and cur[0]:
            crossings = np.unique(np.concatenate(([0], crossings)))
        out[float(th)] = times_sec[crossings]
    return out


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

@dataclass
class PipelineReport:
    n_samples: int = 0
    n_labelled: int = 0
    n_positives: int = 0
    n_catalogue_peaks: int = 0
    horizon_min: int = 15
    chosen_threshold: float = 0.5
    oof: dict = field(default_factory=dict)
    baseline_compare: dict = field(default_factory=dict)
    lt_far_table: List[dict] = field(default_factory=list)
    lt_far_table_kofm: List[dict] = field(default_factory=list)
    beats_baselines: bool = False


class FlareForecastPipeline:
    def __init__(
        self,
        horizon_min: int = 15,
        n_folds: int = 4,
        window_min: int = 30,
        min_class_flux: float = 1e-6,   # >=C events count as flares
        theta_grid: Optional[Sequence[float]] = None,
        use_lightgbm: bool = True,
        feat_short_s: int = 60,
        feat_long_s: int = 600,
        neupert_win_s: int = 120,
        det_baseline_window: Optional[int] = None,
        det_h_c_sigma: float = 25.0,
        det_alpha: float = 0.01,
    ) -> None:
        self.horizon_min = horizon_min
        self.n_folds = n_folds
        self.window_min = window_min
        self.min_class_flux = min_class_flux
        self.theta_grid = theta_grid or np.round(np.arange(0.1, 0.95, 0.05), 2)
        self.use_lightgbm = use_lightgbm
        # Feature/detector windows are expressed in SAMPLES so native cadences
        # (1-s SoLEXS vs 1-min GOES) both work without resampling.
        self.feat_short_s = feat_short_s
        self.feat_long_s = feat_long_s
        self.neupert_win_s = neupert_win_s
        self.det_baseline_window = det_baseline_window
        self.det_h_c_sigma = det_h_c_sigma
        self.det_alpha = det_alpha

    def run(self, df: pd.DataFrame, truth_peaks: Optional[Sequence[Tuple[float, float]]] = None) -> PipelineReport:
        """df columns: timestamp, soft, hard (1-s cadence assumed).

        truth_peaks: optional [(peak_sec, peak_flux)] ground truth used ONLY to
        sanity-check the detected catalogue size, never for training.
        """
        rep = PipelineReport(horizon_min=self.horizon_min)
        df = df.sort_values("timestamp").reset_index(drop=True)
        t0 = pd.to_datetime(df["timestamp"]).iloc[0]
        tsec = (pd.to_datetime(df["timestamp"]) - t0).dt.total_seconds().to_numpy()

        # ---- Stage 1: detect -> catalogue peaks (self-labelling) ----
        peaks, fluxes = self._detect_catalogue_peaks(df)
        rep.n_catalogue_peaks = len(peaks)
        rep.detected_peaks = list(peaks)
        if truth_peaks is not None:
            rep.truth_check = {
                "truth_n": len(truth_peaks),
                "detected_n": len(peaks),
                "matched_within_300s": _match_count(
                    [p for p, _ in truth_peaks], peaks, tol_s=300
                ),
            }

        # ---- Stage 2: causal features ----
        X = build_causal_features(
            df, peaks,
            short_s=self.feat_short_s,
            long_s=self.feat_long_s,
            neupert_win_s=self.neupert_win_s,
        )
        X = X.replace([np.inf, -np.inf], np.nan)
        X["time_since_flare_min"] = X["time_since_flare_min"].fillna(1e4)

        # ---- Stage 3: labels ----
        # Mask = flare itself + decay tail ONLY (front guard 60 s). Never mask
        # the pre-peak window: those samples ARE the positive precursors.
        y = build_labels(
            tsec,
            peaks,
            horizon_s=self.horizon_min * 60,
            mask_in_flare_s=(-60, 900),
            min_class_flux=self.min_class_flux,
            peak_fluxes=fluxes,
        )

        labelled = y != -1
        rep.n_samples = len(y)
        rep.n_labelled = int(labelled.sum())
        rep.n_positives = int((y == 1).sum())
        if rep.n_positives < 5:
            rep.oof = {"error": "too few positives to train"}
            return rep

        # ---- Stage 4: walk-forward CV ----
        folds = make_walk_forward_splits(
            df["timestamp"], n_folds=self.n_folds,
            horizon_min=self.horizon_min, window_min=self.window_min,
        )
        cv = train_with_cv(
            X.to_numpy(), y, folds,
            use_lightgbm=self.use_lightgbm,
            threshold_grid=self.theta_grid,
        )
        rep.chosen_threshold = float(cv["chosen_threshold"])
        rep.oof = cv["oof"]

        # ---- Stage 5: OOF probabilities -> baselines comparison ----
        oof_prob = self._oof_probabilities(X.to_numpy(), y, folds, cv)
        covered = ~np.isnan(oof_prob)
        if covered.sum() < 20:
            rep.oof = {"error": "insufficient OOF coverage"}
            return rep

        y_cov = y[covered]
        clim = ClimatologyBase().fit(y_cov).predict_proba(int(covered.sum()))
        peaks_arr = np.asarray(peaks)
        age = np.full(len(tsec), np.inf)
        if len(peaks_arr):
            idx = np.searchsorted(peaks_arr, tsec, side="right") - 1
            ok = idx >= 0
            age[ok] = tsec[ok] - peaks_arr[idx[ok]]
        pers_cov = PersistenceBase().predict_proba(age[covered])

        rep.baseline_compare = {
            "model": evaluate_forecast(y_cov, oof_prob[covered], rep.chosen_threshold),
            "climatology": evaluate_forecast(y_cov, clim, rep.chosen_threshold),
            "persistence": evaluate_forecast(y_cov, pers_cov, rep.chosen_threshold),
            "oof_coverage_frac": round(float(covered.mean()), 3),
        }
        rep.beats_baselines = beats_baselines(rep.baseline_compare)

        # ---- Stage 6: LT-vs-FAR sweep vs catalogue peaks ----
        # crossings computed on the FULL timeline (absolute seconds), matching
        # peak-time coordinates; masked gaps simply yield no alerts.
        alerts_by_theta = alert_crossing_times(oof_prob, tsec, self.theta_grid)
        rep.lt_far_table = lt_vs_far_curve(
            peaks_arr[peaks_arr >= 0],
            {k: v for k, v in alerts_by_theta.items()},
            window_s=(self.horizon_min + 15) * 60,
        )


        # Hysteresis (k-of-m) variant: same sweep through AlertEngine
        from .alerts import alerts_by_theta_kofm

        kofm_alerts = alerts_by_theta_kofm(oof_prob, tsec, self.theta_grid)
        rep.lt_far_table_kofm = lt_vs_far_curve(
            peaks_arr[peaks_arr >= 0],
            {k: v for k, v in kofm_alerts.items()},
            window_s=(self.horizon_min + 15) * 60,
        )
        return rep

    # ---------------- internals ----------------

    def _detect_catalogue_peaks(self, df: pd.DataFrame):
        """Run soft CUSUM + hard stack; merge via MasterCatalogue (Neupert-aware).

        Uses MasterCatalogue.associate so soft-only and HXR-only events survive
        (the legacy CrossBandAssociator drops unmatched soft detections).
        """
        from datetime import timedelta

        from ..nowcast.soft_detector import CUSUMDetector
        from ..nowcast.hard_detector import HardDetector
        from ..catalog.master_catalog import MasterCatalogue, Detection
        from ..types import Instrument

        _ts = pd.to_datetime(df["timestamp"])
        _tsec = (_ts - _ts.iloc[0]).dt.total_seconds().to_numpy()
        soft = pd.to_numeric(df["soft"], errors="coerce").clip(lower=0).to_numpy()
        hard = pd.to_numeric(df["hard"], errors="coerce").clip(lower=0).to_numpy()

        base_dt = _ts.iloc[0].to_pydatetime()

        bw = self.det_baseline_window or min(600, max(60, len(df) // 8))
        csd = CUSUMDetector(baseline_window=bw,
                            cusum_k_sigma=1.0, h_c_sigma=self.det_h_c_sigma,
                            alpha=self.det_alpha)
        hsd = HardDetector(mu0=max(float(np.median(hard[:200])), 1.0))

        cat = MasterCatalogue()
        soft_dets: List[Detection] = []
        hard_dets: List[Detection] = []
        open_soft: List[dict] = []

        for i in range(len(df)):
            _, alert, status, meta = csd.update(float(soft[i]), timestamp=float(_tsec[i]))
            if status == "ONSET":
                open_soft.append({"start": float(_tsec[i]), "peak": float(_tsec[i]),
                                  "end": float(_tsec[i]), "val": float(soft[i])})
            elif status in ("INCREASING", "DECAYING", "REPEAK", "SUSTAINED"):
                ev = open_soft[-1] if open_soft else None
                if ev is not None:
                    ev["end"] = float(_tsec[i])
                    if float(soft[i]) > ev["val"]:
                        ev["val"] = float(soft[i])
                        ev["peak"] = float(_tsec[i])
            if alert and open_soft:
                ev = open_soft.pop()
                soft_dets.append(Detection(
                    instrument=Instrument.SOLEXS_SDD2,
                    t_start=base_dt + timedelta(seconds=ev["start"]),
                    t_peak=base_dt + timedelta(seconds=ev["peak"]),
                    t_end=base_dt + timedelta(seconds=ev["end"]),
                    peak_value=float(ev["val"]),
                    p_detect=0.9,
                    band="soft",
                ))

            _, h_alert, h_status, hmeta = hsd.update(float(hard[i]), timestamp=float(_tsec[i]))
            if h_alert and isinstance(hmeta.get("peak_time"), (int, float)):
                pt = float(hmeta["peak_time"])
                st = float(hmeta.get("start_time", pt))
                hard_dets.append(Detection(
                    instrument=Instrument.HEL1OS_CDTE,
                    t_start=base_dt + timedelta(seconds=st),
                    t_peak=base_dt + timedelta(seconds=pt),
                    t_end=base_dt + timedelta(seconds=pt),
                    peak_value=float(hmeta.get("peak_value", hard[i])),
                    p_detect=0.85,
                    band="hard",
                ))

        # Unclosed trailing event at end-of-stream: close it now
        if open_soft:
            ev = open_soft.pop()
            soft_dets.append(Detection(
                instrument=Instrument.SOLEXS_SDD2,
                t_start=base_dt + timedelta(seconds=ev["start"]),
                t_peak=base_dt + timedelta(seconds=ev["peak"]),
                t_end=base_dt + timedelta(seconds=_tsec[-1]),
                peak_value=float(ev["val"]),
                p_detect=0.75,
                band="soft",
            ))

        events = cat.associate(soft_dets, hard_dets)
        cat.dedupe()
        events = cat.all_events

        peaks, fluxes = [], []
        for e in sorted(events, key=lambda x: x.peak_time):
            ps = (e.peak_time - base_dt).total_seconds()
            peaks.append(ps)
            fluxes.append(max(e.peak_flux_solexs, e.peak_flux_hel1os))
        return peaks, fluxes

    def _oof_probabilities(self, X, y, folds, cv) -> np.ndarray:
        """Out-of-fold probabilities. Positions never covered by any test
        fold (the expanding-window head) stay NaN -> excluded from metrics
        and incapable of raising alerts."""
        factory = train_with_cv.__globals__["_make_model_factory"](self.use_lightgbm)
        oof = np.full(len(y), np.nan)
        valid_pos = np.where(y != -1)[0]
        for tr, te, emb in folds:
            pos_tr = valid_pos[np.isin(valid_pos, tr)]
            pos_te = valid_pos[np.isin(valid_pos, te)]
            if len(pos_te) < 5 or len(pos_tr) < 20:
                continue
            m = factory()
            m.fit(X[pos_tr], y[pos_tr])
            oof[pos_te] = m.predict_proba(X[pos_te])[:, 1]
        return oof


def _match_count(a: Sequence[float], b: Sequence[float], tol_s: float) -> int:
    used = set()
    n = 0
    for x in a:
        cands = [j for j, y in enumerate(b) if j not in used and abs(x - y) <= tol_s]
        if cands:
            used.add(min(cands))
            n += 1
    return n
