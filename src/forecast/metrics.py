"""Forecast evaluation metrics, per review arXiv:2511.20465 conventions.

Primary metric: TSS (True Skill Statistic) - class-ratio insensitive.
Secondary: HSS, BSS (probabilistic), POD, FAR, PR-AUC.
Lead-time: distribution of p - t_alert over verified events, plus the
LT-vs-FAR sweep which is THE operating-point plot.

Accuracy and ROC-AUC are deliberately NOT provided: they mislead on rare
events. Do not add them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

ArrayLike = Union[Sequence[Any], np.ndarray, pd.Series]


@dataclass
class ConfusionMatrix:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def pod(self) -> float:
        """Probability of Detection (= recall / TPR)."""
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def far(self) -> float:
        """False Alarm Ratio = FP / (TP + FP)."""
        return self.fp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def pofd(self) -> float:
        """Probability of False Detection = FP / (FP + TN)."""
        return self.fp / (self.fp + self.tn) if (self.fp + self.tn) else 0.0

    @property
    def tss(self) -> float:
        """True Skill Statistic = POD - POFD. Primary metric."""
        return self.pod - self.pofd

    @property
    def hss(self) -> float:
        """Heidke Skill Score vs random chance."""
        num = 2.0 * (self.tp * self.tn - self.fp * self.fn)
        den = (
            (self.tp + self.fn) * (self.fn + self.tn)
            + (self.tp + self.fp) * (self.fp + self.tn)
        )
        return num / den if den else 0.0

    @property
    def csi(self) -> float:
        """Critical Success Index (Threat Score) = TP / (TP + FP + FN)."""
        den = self.tp + self.fp + self.fn
        return self.tp / den if den else 0.0

    @property
    def ets(self) -> float:
        """Equitable Threat Score (Gilbert Skill Score).
        Adjusts CSI for random hits: a_r = (TP + FP) * (TP + FN) / Total.
        """
        total = self.tp + self.fp + self.fn + self.tn
        if total == 0:
            return 0.0
        a_r = ((self.tp + self.fp) * (self.tp + self.fn)) / total
        num = self.tp - a_r
        den = self.tp + self.fp + self.fn - a_r
        return num / den if den else 0.0

    def f_beta(self, beta: float = 2.0) -> float:
        """F-beta score prioritizing recall (detection) over precision when beta > 1."""
        precision = self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0
        recall = self.pod
        if precision + recall == 0:
            return 0.0
        b2 = beta ** 2
        return (1.0 + b2) * (precision * recall) / (b2 * precision + recall)


def compute_expected_calibration_error(
    y_true: ArrayLike,
    y_prob: ArrayLike,
    n_bins: int = 10,
) -> float:
    """Computes Expected Calibration Error (ECE) across uniform probability bins.
    
    ECE = sum_{m=1}^M (|B_m| / N) * |acc(B_m) - conf(B_m)|
    """
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(y_prob, dtype=float)
    if len(y) == 0:
        return 0.0

    bin_boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n_samples = len(y)

    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        in_bin = (p >= bin_lower) & (p < bin_upper) if i < n_bins - 1 else (p >= bin_lower) & (p <= bin_upper)
        bin_size = np.sum(in_bin)

        if bin_size > 0:
            avg_confidence = np.mean(p[in_bin])
            avg_accuracy = np.mean(y[in_bin])
            ece += (bin_size / n_samples) * np.abs(avg_accuracy - avg_confidence)

    return float(ece)


def brier_score(y_true: ArrayLike, y_prob: ArrayLike) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_prob, dtype=float)
    return float(np.mean((p - y) ** 2))


def brier_skill_score(y_true: ArrayLike, y_prob: ArrayLike) -> float:
    """BSS vs climatology; decomposes into reliability+resolution-uncertainty."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_prob, dtype=float)
    bs_model = float(np.mean((p - y) ** 2))
    base_rate = float(np.mean(y))
    bs_clim = base_rate * (1.0 - base_rate)
    if bs_clim == 0:
        return 0.0
    return 1.0 - bs_model / bs_clim


def pr_auc(y_true: ArrayLike, y_score: ArrayLike) -> float:
    """Area under Precision-Recall curve (step-wise). Better than ROC under imbalance."""
    y = np.asarray(y_true)
    s = np.asarray(y_score)
    order = np.argsort(-s)
    y = y[order]
    tp = fp = 0
    precisions, recalls = [], []
    n_pos = max(int(y.sum()), 1)
    for label in y:
        if label == 1:
            tp += 1
        else:
            fp += 1
        precisions.append(tp / (tp + fp))
        recalls.append(tp / n_pos)
    # trapezoid over recall axis, anchored at (0, 1)
    auc = 0.0
    prev_r, prev_p = 0.0, 1.0
    for r, p in zip(recalls, precisions):
        auc += (r - prev_r) * prev_p
        prev_r, prev_p = r, p
    return float(auc)


@dataclass
class LeadTimeReport:
    values_s: List[float] = field(default_factory=list)

    def add(self, lead_s: float) -> None:
        if lead_s > 0:
            self.values_s.append(lead_s)

    @property
    def median_s(self) -> float:
        return float(np.median(self.values_s)) if self.values_s else 0.0

    @property
    def iqr_s(self) -> Tuple[float, float]:
        if not self.values_s:
            return (0.0, 0.0)
        q25, q75 = np.percentile(self.values_s, [25, 75])
        return (float(q25), float(q75))

    def fraction_at_least(self, minutes: float) -> float:
        if not self.values_s:
            return 0.0
        thresh = minutes * 60
        return float(np.mean([v >= thresh for v in self.values_s]))

    def summary(self) -> Dict[str, Any]:
        q25, q75 = self.iqr_s
        return {
            "n_verified": len(self.values_s),
            "median_lead_min": self.median_s / 60,
            "iqr_lead_min": (q25 / 60, q75 / 60),
            "frac_ge_5min": self.fraction_at_least(5),
            "frac_ge_10min": self.fraction_at_least(10),
            "frac_ge_15min": self.fraction_at_least(15),
        }


def lt_vs_far_curve(
    peaks_s: Sequence[float],           # flare peak times (s, monotonically increasing)
    alert_times_by_threshold: Dict[float, Sequence[float]],  # theta -> alert times (s)
    window_s: float = 1800.0,
) -> List[Dict[str, float]]:
    """Sweep probability threshold theta: for each, compute POD/FAR/median LT.

    An event is 'hit' if some alert fires in [p - window, p); the earliest such
    alert defines its lead time. Alerts not matched to any event are false alarms.
    """
    rows = []
    for theta, alerts in sorted(alert_times_by_threshold.items()):
        cm = ConfusionMatrix()
        lt_report = LeadTimeReport()
        used_alerts = set()

        for p in peaks_s:
            hits = [
                (p - a, k)
                for k, a in enumerate(alerts)
                if 0 < (p - a) <= window_s and k not in used_alerts
            ]
            if hits:
                lt, k = min(hits)  # earliest alert => largest lead
                used_alerts.add(k)
                cm.tp += 1
                lt_report.add(lt)
            else:
                cm.fn += 1

        cm.fp = len(alerts) - len(used_alerts)
        rows.append(
            {
                "theta": theta,
                "pod": round(cm.pod, 3),
                "far": round(cm.far, 3),
                "tss": round(cm.tss, 3),
                "median_lt_min": round(lt_report.median_s / 60, 2),
                "false_alarms": cm.fp,
            }
        )
    return rows


def evaluate_forecast(
    y_true: ArrayLike,
    y_prob: ArrayLike,
    threshold: float = 0.5,
) -> Dict[str, float]:
    """One-shot evaluation at a fixed operating threshold."""
    cm = ConfusionMatrix()
    yt_arr = np.asarray(y_true, dtype=int)
    yp_arr = np.asarray(y_prob, dtype=float)
    for yt, yp in zip(yt_arr, yp_arr):
        pred = 1 if yp >= threshold else 0
        if yt == 1 and pred == 1:
            cm.tp += 1
        elif yt == 0 and pred == 1:
            cm.fp += 1
        elif yt == 1 and pred == 0:
            cm.fn += 1
        else:
            cm.tn += 1
    return {
        "threshold": threshold,
        "pod": round(cm.pod, 3),
        "far": round(cm.far, 3),
        "tss": round(cm.tss, 3),
        "hss": round(cm.hss, 3),
        "bss": round(brier_skill_score(yt_arr, yp_arr), 3),
        "brier": round(brier_score(yt_arr, yp_arr), 4),
        "pr_auc": round(pr_auc(yt_arr, yp_arr), 3),
    }


def compute_contingency_scores(
    y_true: ArrayLike,
    y_prob: ArrayLike,
    threshold: float = 0.5,
) -> Dict[str, float]:
    """Computes operational space weather verification metrics (TSS, HSS, POD, FAR)."""
    y_t = np.asarray(y_true, dtype=int)
    y_p = np.asarray(y_prob, dtype=float)
    y_pred = (y_p >= threshold).astype(int)

    tp = int(np.sum((y_pred == 1) & (y_t == 1)))
    tn = int(np.sum((y_pred == 0) & (y_t == 0)))
    fp = int(np.sum((y_pred == 1) & (y_t == 0)))
    fn = int(np.sum((y_pred == 0) & (y_t == 1)))

    pod = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    pofd = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    far = fp / (tp + fp) if (tp + fp) > 0 else 0.0
    tss = pod - pofd

    num_hss = 2.0 * (tp * tn - fp * fn)
    den_hss = (tp + fn) * (fn + tn) + (tp + fp) * (fp + tn)
    hss = (num_hss / den_hss) if den_hss > 0 else 0.0

    return {
        "TSS": float(tss),
        "HSS": float(hss),
        "POD": float(pod),
        "FAR": float(far),
        "POFD": float(pofd),
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
    }


class LeadTimeEvaluator:
    """
    Evaluates exact chronological Lead Time (minutes prior to flare peak)
    provided by the forecasting system over verified catalogue events.
    """
    def __init__(self, alert_threshold: float = 0.50):
        self.threshold = alert_threshold

    def evaluate_lead_times(
        self,
        timestamps: Sequence[datetime],
        predicted_probs: Sequence[float],
        catalogue_peak_times: Sequence[datetime],
        window_minutes: float = 60.0,
    ) -> List[Dict[str, Union[float, str, bool]]]:
        ts_arr = pd.to_datetime(list(timestamps))
        probs_arr = np.asarray(predicted_probs, dtype=float)
        results = []

        for p_t in catalogue_peak_times:
            p_dt = pd.to_datetime(p_t)
            pre_start = p_dt - pd.Timedelta(minutes=window_minutes)

            mask = (ts_arr >= pre_start) & (ts_arr <= p_dt)
            win_times = ts_arr[mask]
            win_probs = probs_arr[mask]

            if len(win_probs) == 0:
                continue

            alert_indices = np.where(win_probs >= self.threshold)[0]
            first_alert_time = None

            for idx in alert_indices:
                if idx + 3 <= len(win_probs) and np.all(win_probs[idx:idx + 3] >= self.threshold):
                    first_alert_time = win_times[idx]
                    break

            if first_alert_time is not None:
                lead_min = (p_dt - first_alert_time).total_seconds() / 60.0
                detected = True
            else:
                lead_min = 0.0
                detected = False

            results.append({
                "peak_time": str(p_dt),
                "alert_triggered": detected,
                "lead_time_minutes": round(float(lead_min), 2),
            })
        return results


def reliability_diagram(
    y_true: Sequence[int],
    y_prob: Sequence[float],
    n_bins: int = 10,
) -> Dict[str, Union[List[float], List[int], float]]:
    """Compute reliability diagram bins and Brier score decomposition (Murphy 1973).

    Returns:
        bin_centers: Mean predicted probability in each bin
        observed_freq: Actual fraction of positives in each bin
        bin_counts: Number of samples in each bin
        reliability: Weighted mean squared error between forecast and observed (lower is better)
        resolution: Ability to resolve distinct probabilities from base rate (higher is better)
        uncertainty: Inherent sample variance = base_rate * (1 - base_rate)
    """
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_prob, dtype=float)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_centers = []
    obs_freqs = []
    counts = []

    n_total = len(y)
    base_rate = float(np.mean(y)) if n_total > 0 else 0.0

    rel = 0.0
    res = 0.0

    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            mask = (p >= low) & (p <= high)
        else:
            mask = (p >= low) & (p < high)

        n_k = int(np.sum(mask))
        counts.append(n_k)

        if n_k > 0:
            p_k = float(np.mean(p[mask]))
            o_k = float(np.mean(y[mask]))
            bin_centers.append(round(p_k, 4))
            obs_freqs.append(round(o_k, 4))

            rel += (n_k / n_total) * ((p_k - o_k) ** 2)
            res += (n_k / n_total) * ((o_k - base_rate) ** 2)
        else:
            mid = float((low + high) / 2.0)
            bin_centers.append(round(mid, 4))
            obs_freqs.append(0.0)

    unc = base_rate * (1.0 - base_rate)
    brier = rel - res + unc

    return {
        "bin_centers": bin_centers,
        "observed_freq": obs_freqs,
        "bin_counts": counts,
        "reliability": round(float(rel), 5),
        "resolution": round(float(res), 5),
        "uncertainty": round(float(unc), 5),
        "brier_decomposed": round(float(brier), 5),
    }

