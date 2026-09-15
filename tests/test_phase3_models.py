"""Automated Unit Tests for Phase 3: Multi-Tier Model Architecture & Training."""
import sys
from pathlib import Path
import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.forecast.multi_tier_pipeline import MultiTierFlareForecastPipeline
from src.forecast.deep_models import (
    SpatioTemporalGraphTransformer,
    CNNLSTMSolarForecaster,
    BinaryFocalLoss,
    NeupertPhysicsLoss,
)


def test_tier1_and_tier2_tabular_training():
    """Verify that Tier 1 (Logistic, RF) and Tier 2 (LightGBM) train and evaluate cleanly."""
    np.random.seed(42)
    n_samples = 300
    n_features = 30
    
    # Synthetic 30D feature matrix
    X = np.random.normal(0, 1, (n_samples, n_features))
    # 5% positive flare events
    y = (X[:, 4] + X[:, 16] + np.random.normal(0, 0.5, n_samples) > 2.0).astype(int)
    
    split = int(n_samples * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    pipeline = MultiTierFlareForecastPipeline(random_state=42)
    imp = pipeline.train_tabular_tiers(X_train, y_train)
    
    assert "rf_feature_importance" in imp
    assert len(imp["rf_feature_importance"]) == n_features
    
    preds = pipeline.predict_tabular_tiers(X_test)
    assert "tier1_logistic" in preds
    assert "tier1_rf" in preds
    assert len(preds["tier1_logistic"]) == len(y_test)
    
    # Evaluate skill scores
    scores_rf = pipeline.evaluate_tier_predictions(y_test, preds["tier1_rf"], "Tier 1 Random Forest")
    assert "tss" in scores_rf
    assert "hss" in scores_rf
    assert "pod" in scores_rf


def test_tier3_deep_models_forward_and_physics_loss():
    """Verify Tier 3 SpatioTemporalGraphTransformer and CNN-LSTM with Neupert PINN loss."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    B, L, N, F_in = 4, 60, 5, 2
    g = torch.randn(B, L, N, F_in).to(device)
    
    # 1. SpatioTemporalGraphTransformer
    st_gt = SpatioTemporalGraphTransformer(num_nodes=N, in_features_per_node=F_in, d_model=64).to(device)
    out_gt = st_gt(g)
    
    assert "logits_15m" in out_gt
    assert "logits_30m" in out_gt
    assert "logits_60m" in out_gt
    assert "alpha" in out_gt
    assert "beta" in out_gt
    assert out_gt["logits_30m"].shape == (B,)
    
    # PINN Neupert Physics Loss
    pinn_loss_fn = NeupertPhysicsLoss()
    sxr_dummy = g[:, -1, 0, 0]
    hxr_dummy = g[:, -1, 2, 0]
    p_loss = pinn_loss_fn(out_gt["dsxr_dt_pred"], sxr_dummy, hxr_dummy, out_gt["alpha"], out_gt["beta"])
    assert p_loss.item() >= 0.0
    
    # 2. CNN-LSTM Forecaster
    feat_x = torch.randn(B, L, 8).to(device)
    cnn_lstm = CNNLSTMSolarForecaster(in_channels=8, conv_channels=64, lstm_hidden=64).to(device)
    out_cnn = cnn_lstm(feat_x)
    assert "logits_15m" in out_cnn
    assert out_cnn["logits_30m"].shape == (B,)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
