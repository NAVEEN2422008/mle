"""Multi-Tier Model Architecture for Solar Flare Forecasting (Phase 3).

Provides:
- Tier 1: Baseline ML (Logistic Regression & Balanced Random Forest)
- Tier 2: Gradient Boosted Trees (LightGBM with Gini Importance)
- Tier 3: Deep Sequence & Physics-Informed Models (ST-GT + PINN & CNN-LSTM)
- Unified multi-tier benchmarking & ablation comparison
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

try:
    from lightgbm import LGBMClassifier
    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False

from .metrics import ConfusionMatrix, brier_skill_score, pr_auc
from .deep_models import (
    CNNLSTMSolarForecaster,
    SpatioTemporalGraphTransformer,
    BinaryFocalLoss,
    NeupertPhysicsLoss,
)


class MultiTierFlareForecastPipeline:
    """Manages training and comparative evaluation across all 3 model tiers."""

    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.scaler = StandardScaler()
        
        # Tier 1 Models
        self.tier1_logistic = LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            C=1.0,
            random_state=random_state,
        )
        self.tier1_rf = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=random_state,
        )
        
        # Tier 2 Model
        if HAS_LGBM:
            self.tier2_lgbm = LGBMClassifier(
                n_estimators=150,
                learning_rate=0.05,
                num_leaves=31,
                class_weight="balanced",
                n_jobs=-1,
                random_state=random_state,
                verbose=-1,
            )
        else:
            self.tier2_lgbm = None

    def train_tabular_tiers(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Trains Tier 1 (Logistic, RF) and Tier 2 (LightGBM) on tabular feature matrices."""
        X_scaled = self.scaler.fit_transform(X_train)
        
        # 1. Train Logistic Regression
        self.tier1_logistic.fit(X_scaled, y_train)
        
        # 2. Train Random Forest
        self.tier1_rf.fit(X_train, y_train)
        rf_importance = dict(zip(
            feature_names or [f"f{i:02d}" for i in range(X_train.shape[1])],
            self.tier1_rf.feature_importances_
        ))
        
        # 3. Train LightGBM
        lgbm_importance = {}
        if self.tier2_lgbm is not None:
            self.tier2_lgbm.fit(X_train, y_train)
            lgbm_importance = dict(zip(
                feature_names or [f"f{i:02d}" for i in range(X_train.shape[1])],
                self.tier2_lgbm.feature_importances_
            ))

        return {
            "rf_feature_importance": rf_importance,
            "lgbm_feature_importance": lgbm_importance,
        }

    def predict_tabular_tiers(self, X_test: np.ndarray) -> Dict[str, np.ndarray]:
        """Outputs predicted probabilities for Tier 1 and Tier 2 models."""
        X_scaled = self.scaler.transform(X_test)
        
        p_log = np.asarray(self.tier1_logistic.predict_proba(X_scaled))
        p_rf = np.asarray(self.tier1_rf.predict_proba(X_test))
        preds = {
            "tier1_logistic": p_log[:, 1],
            "tier1_rf": p_rf[:, 1],
        }
        
        if self.tier2_lgbm is not None:
            p_lgbm = np.asarray(self.tier2_lgbm.predict_proba(X_test))
            preds["tier2_lgbm"] = p_lgbm[:, 1]
            
        return preds

    def evaluate_tier_predictions(
        self,
        y_true: np.ndarray,
        y_probs: np.ndarray,
        model_name: str,
    ) -> Dict[str, Any]:
        """Calculates operational skill metrics across an optimal threshold sweep."""
        best_tss = -1.0
        best_th = 0.5
        best_scores = {}

        for th in np.linspace(0.05, 0.95, 91):
            tp = int(np.sum((y_true == 1) & (y_probs >= th)))
            fp = int(np.sum((y_true == 0) & (y_probs >= th)))
            fn = int(np.sum((y_true == 1) & (y_probs < th)))
            tn = int(np.sum((y_true == 0) & (y_probs < th)))

            cm = ConfusionMatrix(tp=tp, fp=fp, fn=fn, tn=tn)
            if cm.tss > best_tss and tp > 0:
                best_tss = cm.tss
                best_th = th
                best_scores = {
                    "model": model_name,
                    "optimal_threshold": float(th),
                    "tss": float(cm.tss),
                    "hss": float(cm.hss),
                    "pod": float(cm.pod),
                    "far": float(cm.far),
                    "pr_auc": float(pr_auc(y_true, y_probs)),
                    "bss": float(brier_skill_score(y_true, y_probs)),
                }

        return best_scores or {
            "model": model_name,
            "optimal_threshold": 0.5,
            "tss": 0.0,
            "hss": 0.0,
            "pod": 0.0,
            "far": 1.0,
            "pr_auc": 0.0,
            "bss": 0.0,
        }
