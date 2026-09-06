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
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


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


def brier_score(y_true: Sequence[int], y_prob: Sequence[float]) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_prob, dtype=float)
    return float(np.mean((p - y) ** 2))


def brier_skill_score(y_true: Sequence[int], y_prob: Sequence[float]) -> float:
    """BSS vs climatology; decomposes into reliability+resolution-uncertainty."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_prob, dtype=float)
    bs_model = float(np.mean((p - y) ** 2))
    base_rate = float(np.mean(y))
    bs_clim = base_rate * (1.0 - base_rate)
    if bs_clim == 0:
        return 0.0
    return 1.0 - bs_model / bs_clim


def pr_auc(y_true: Sequence[int], y_score: Sequence[float]) -> float:
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

    def summary(self) -> Dict[str, float]:
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
    y_true: Sequence[int],
    y_prob: Sequence[float],
    threshold: float = 0.5,
) -> Dict[str, float]:
    """One-shot evaluation at a fixed operating threshold."""
    cm = ConfusionMatrix()
    for yt, yp in zip(y_true, y_prob):
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
        "bss": round(brier_skill_score(y_true, y_prob), 3),
        "brier": round(brier_score(y_true, y_prob), 4),
        "pr_auc": round(pr_auc(y_true, y_prob), 3),
    }
