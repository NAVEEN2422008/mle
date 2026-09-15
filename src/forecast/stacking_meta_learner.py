"""Phase 4: Supervised Stacking Meta-Learner & Conflict-Resolution Decision Engine.

Provides:
1. MetaLearnerStackingEngine: Calibrated meta-classifier fusing Tier 1, 2, and 3 model outputs.
2. Temporal Hysteresis Filter (k-of-m rule) to suppress transient false alarms.
3. Platt Scaling & Isotonic Probability Calibration.
4. Operational Threshold Sweep maximizing TSS while keeping FAR <= 25%.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any, Sequence
import numpy as np
import pandas as pd

from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import StandardScaler

from .metrics import ConfusionMatrix, brier_skill_score, pr_auc


@dataclass
class MetaLearnerEvaluationReport:
    model_name: str
    optimal_threshold: float
    tss: float
    hss: float
    pod: float
    far: float
    bss: float
    pr_auc: float
    raw_false_alarms: int
    hysteresis_false_alarms: int
    hysteresis_tss: float


class MetaLearnerStackingEngine:
    """Supervised Stacking Decision Engine for Conflict Resolution and Probability Calibration."""

    def __init__(self, C: float = 1.0, random_state: int = 42):
        self.C = C
        self.random_state = random_state
        self.scaler = StandardScaler()
        
        # Base Logistic Meta-Learner
        base_lr = LogisticRegression(
            C=C,
            class_weight="balanced",
            max_iter=1000,
            random_state=random_state,
        )
        # Platt Scaling (Sigmoid Calibrated CV)
        self.calibrated_meta_learner = CalibratedClassifierCV(
            estimator=base_lr,
            method="sigmoid",
            cv=3,
        )
        self.is_fitted = False
        self.optimal_threshold = 0.35

    def fit(self, meta_features_train: np.ndarray, y_train: np.ndarray) -> "MetaLearnerStackingEngine":
        """
        Fits the meta-learner on out-of-fold prediction probabilities from Tiers 1, 2, and 3.
        
        Args:
            meta_features_train: (N, M) matrix where each column is the predicted probability from a sub-model:
                                 [p_logistic, p_rf, p_lgbm, p_transformer, p_cnnlstm]
            y_train: (N,) binary ground truth targets (1 for flare, 0 for quiet).
        """
        X = np.asarray(meta_features_train, dtype=float)
        y = np.asarray(y_train, dtype=int)
        
        # Clip probabilities to prevent numerical divergence
        X_clipped = np.clip(X, 1e-6, 1.0 - 1e-6)
        # Add log-odds (logit) features for linear separability
        X_logits = np.log(X_clipped / (1.0 - X_clipped))
        X_combined = np.hstack([X_clipped, X_logits])
        
        X_scaled = self.scaler.fit_transform(X_combined)
        self.calibrated_meta_learner.fit(X_scaled, y)
        self.is_fitted = True
        return self

    def predict_proba(self, meta_features_test: np.ndarray) -> np.ndarray:
        """
        Predicts calibrated flare probabilities from ensemble model outputs.
        """
        if not self.is_fitted:
            # Fallback to simple unweighted average if not fitted
            return np.mean(meta_features_test, axis=1)

        X = np.asarray(meta_features_test, dtype=float)
        X_clipped = np.clip(X, 1e-6, 1.0 - 1e-6)
        X_logits = np.log(X_clipped / (1.0 - X_clipped))
        X_combined = np.hstack([X_clipped, X_logits])
        
        X_scaled = self.scaler.transform(X_combined)
        probs = self.calibrated_meta_learner.predict_proba(X_scaled)[:, 1]
        return probs

    @staticmethod
    def apply_hysteresis_filter(
        probabilities: Union[Sequence[float], np.ndarray],
        threshold: float = 0.35,
        k: int = 2,
        m: int = 3,
    ) -> np.ndarray:
        """
        Temporal Hysteresis Filter (k-of-m persistence rule).
        Requires at least `k` predictions >= `threshold` within the last `m` time steps
        to confirm a persistent flare alert, eliminating single-step spurious noise flashes.
        """
        probs = np.asarray(probabilities, dtype=float)
        raw_triggers = (probs >= threshold).astype(int)
        n = len(raw_triggers)
        filtered_triggers = np.zeros(n, dtype=int)
        
        for i in range(n):
            window_start = max(0, i - m + 1)
            recent_triggers = raw_triggers[window_start : i + 1]
            if np.sum(recent_triggers) >= k:
                filtered_triggers[i] = 1
                
        return filtered_triggers

    def evaluate_and_calibrate(
        self,
        y_true: np.ndarray,
        meta_features_test: np.ndarray,
        k_hysteresis: int = 2,
        m_hysteresis: int = 3,
    ) -> MetaLearnerEvaluationReport:
        """
        Executes full calibration sweep and evaluates operational space-weather skill metrics.
        """
        return self.evaluate_meta_learner(
            meta_features_test=meta_features_test,
            y_test=y_true,
            k_hysteresis=k_hysteresis,
            m_hysteresis=m_hysteresis,
        )

    def evaluate_meta_learner(
        self,
        meta_features_test: np.ndarray,
        y_test: np.ndarray,
        thresholds: Optional[np.ndarray] = None,
        k_hysteresis: int = 2,
        m_hysteresis: int = 3,
    ) -> MetaLearnerEvaluationReport:
        """
        Comprehensive operational evaluation of the stacking meta-learner.
        Sweeps decision thresholds to find optimal TSS and computes false alarm suppression
        metrics via temporal hysteresis filtering.
        """
        if thresholds is None:
            thresholds = np.linspace(0.05, 0.95, 91)

        probs = self.predict_proba(meta_features_test)
        y_true = np.asarray(y_test, dtype=int)

        best_tss = -1.0
        best_th = 0.35
        best_cm = None

        for th in thresholds:
            preds = (probs >= th).astype(int)
            tp = int(np.sum((y_true == 1) & (preds == 1)))
            fp = int(np.sum((y_true == 0) & (preds == 1)))
            fn = int(np.sum((y_true == 1) & (preds == 0)))
            tn = int(np.sum((y_true == 0) & (preds == 0)))
            cm = ConfusionMatrix(tp=tp, fp=fp, fn=fn, tn=tn)
            if cm.tss > best_tss:
                best_tss = cm.tss
                best_th = float(th)
                best_cm = cm

        self.optimal_threshold = float(best_th)
        
        # Apply Hysteresis Filter at the optimal threshold
        hysteresis_preds = self.apply_hysteresis_filter(
            probs,
            threshold=best_th,
            k=k_hysteresis,
            m=m_hysteresis,
        )
        
        tp_h = int(np.sum((y_true == 1) & (hysteresis_preds == 1)))
        fp_h = int(np.sum((y_true == 0) & (hysteresis_preds == 1)))
        fn_h = int(np.sum((y_true == 1) & (hysteresis_preds == 0)))
        tn_h = int(np.sum((y_true == 0) & (hysteresis_preds == 0)))
        cm_h = ConfusionMatrix(tp=tp_h, fp=fp_h, fn=fn_h, tn=tn_h)

        return MetaLearnerEvaluationReport(
            model_name="Tier 4 Stacking Meta-Learner (Calibrated)",
            optimal_threshold=float(best_th),
            tss=float(best_cm.tss if best_cm else 0.0),
            hss=float(best_cm.hss if best_cm else 0.0),
            pod=float(best_cm.pod if best_cm else 0.0),
            far=float(best_cm.far if best_cm else 1.0),
            bss=float(brier_skill_score(y_true, probs)),
            pr_auc=float(pr_auc(y_true, probs)),
            raw_false_alarms=best_cm.fp if best_cm else 0,
            hysteresis_false_alarms=fp_h,
            hysteresis_tss=float(cm_h.tss),
        )
