"""Automated Unit Tests for Phase 4: Stacking Meta-Learner & Decision Engine."""
import sys
from pathlib import Path
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.forecast.stacking_meta_learner import (
    MetaLearnerStackingEngine,
    MetaLearnerEvaluationReport,
)


def test_meta_learner_fit_and_predict():
    """Verify that the Stacking Meta-Learner trains on multi-model predictions and predicts probabilities."""
    np.random.seed(42)
    n_samples = 400
    n_models = 5  # Logistic, RF, LightGBM, Transformer, CNN-LSTM
    
    # Ground truth: 10% positive flares
    y = (np.random.rand(n_samples) < 0.10).astype(int)
    
    # Generate realistic model predictions correlated with true target + individual noise
    meta_X = np.zeros((n_samples, n_models))
    for m in range(n_models):
        # Base true signal with model-specific noise
        signal = y * 0.7 + np.random.normal(0.15, 0.1, n_samples)
        meta_X[:, m] = np.clip(signal, 0.01, 0.99)
        
    split = int(n_samples * 0.75)
    X_train, X_test = meta_X[:split], meta_X[split:]
    y_train, y_test = y[:split], y[split:]
    
    engine = MetaLearnerStackingEngine(C=1.0, random_state=42)
    engine.fit(X_train, y_train)
    
    probs = engine.predict_proba(X_test)
    assert len(probs) == len(y_test)
    assert (probs >= 0.0).all() and (probs <= 1.0).all()
    
    # Calibrated probabilities should have high correlation with true outcomes
    pos_mean = np.mean(probs[y_test == 1]) if np.sum(y_test == 1) > 0 else 0.5
    neg_mean = np.mean(probs[y_test == 0]) if np.sum(y_test == 0) > 0 else 0.1
    assert pos_mean > neg_mean


def test_hysteresis_filter_noise_suppression():
    """Verify that k-of-m hysteresis filter suppresses single-step noise flashes."""
    # Sequence of 20 time steps:
    # Index 5: isolated false alarm spike (1.0) -> should be suppressed
    # Index 12-14: persistent true flare precursor (1.0, 1.0, 1.0) -> should be confirmed
    probs = np.zeros(20)
    probs[5] = 0.90 # isolated spike
    probs[12] = 0.85
    probs[13] = 0.88
    probs[14] = 0.92 # persistent burst
    
    # k=2 of m=3 filter at threshold 0.5
    filtered = MetaLearnerStackingEngine.apply_hysteresis_filter(probs, threshold=0.5, k=2, m=3)
    
    # Isolated spike at 5 should NOT trigger
    assert filtered[5] == 0
    # First step at 12 is only 1 spike, so not confirmed yet
    assert filtered[12] == 0
    # Second step at 13 has 2 spikes in 3 steps -> CONFIRMED
    assert filtered[13] == 1
    # Third step at 14 has 3 spikes in 3 steps -> CONFIRMED
    assert filtered[14] == 1


def test_meta_learner_evaluation_report():
    """Verify evaluation and threshold calibration report structure."""
    np.random.seed(42)
    n = 200
    y = (np.random.rand(n) < 0.15).astype(int)
    meta_X = np.zeros((n, 4))
    for m in range(4):
        meta_X[:, m] = np.clip(y * 0.8 + np.random.normal(0.1, 0.15, n), 0.01, 0.99)
        
    engine = MetaLearnerStackingEngine().fit(meta_X[:150], y[:150])
    report = engine.evaluate_and_calibrate(y[150:], meta_X[150:], k_hysteresis=2, m_hysteresis=3)
    
    assert isinstance(report, MetaLearnerEvaluationReport)
    assert report.tss >= 0.0
    assert report.hss >= 0.0
    assert report.pod >= 0.0
    assert report.far <= 1.0
    assert 0.05 <= report.optimal_threshold <= 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
