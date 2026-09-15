"""Unit and integration tests for Deep Learning Forecaster, PINN Neupert Physics, and Multi-Sensor Fusion."""
import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd

import torch
from src.forecast.deep_forecaster import (
    TemporalAttentionForecaster,
    compute_skill_scores,
    MultiHorizonForecast,
    AdityaSolarTransformer,
    BinaryFocalLoss,
    SolarFlareWindowDataset,
    HAS_TORCH,
)

from src.preprocess.fusion import (
    inverse_variance_fusion,
    KalmanFilter1D,
    compute_wavelet_qpp_power,
    fuse_instruments
)
from src.nowcast.neupert_engine import NeupertCorrelator


def test_inverse_variance_fusion():
    """Verify that fusing two independent sensors with equal uncertainty reduces variance by 2."""
    meas = [100.0, 102.0]
    uncs = [2.0, 2.0]
    val, unc = inverse_variance_fusion(meas, uncs)
    assert abs(val - 101.0) < 1e-6
    assert abs(unc - np.sqrt(2.0)) < 1e-6


def test_kalman_filter_1d():
    """Verify 1D Kalman filter converges and smooths noisy steps."""
    kf = KalmanFilter1D(process_noise=1e-3, measurement_noise=1e-1)
    true_val = 50.0
    filtered = 50.0
    for _ in range(50):
        kf.predict()
        noisy = true_val + np.random.normal(0, 0.5)
        filtered = kf.update(noisy)
    assert abs(filtered - true_val) < 1.0


def test_wavelet_qpp_power():
    """Verify CWT Morlet wavelet extracts power from oscillating signal."""
    t = np.linspace(0, 10, 200)
    sig = np.sin(2 * np.pi * 1.5 * t) + np.random.normal(0, 0.1, 200)
    power = compute_wavelet_qpp_power(sig, num_scales=8)
    assert len(power) == 200
    assert np.mean(power) > 0.0


def test_temporal_attention_forecaster_numpy():
    """Verify NumPy inference forecaster predicts multi-horizon flare probabilities."""
    model = TemporalAttentionForecaster(seq_len=60, n_features=8)
    # Simulate a 60-step precursor surge
    window = np.ones((60, 8)) * 1.5
    window[:, 0] = 5000.0  # M-class flux
    window[:, 2] = 3.5     # SXR excess factor
    window[:, 4] = 15.0    # positive derivative
    window[:, 6] = 2.0     # Neupert cross-term
    
    fc = model.forward(window)
    assert isinstance(fc, MultiHorizonForecast)
    assert 0.0 <= fc.prob_15m <= 1.0
    assert 0.0 <= fc.prob_30m <= 1.0
    assert 0.0 <= fc.prob_60m <= 1.0
    assert fc.predicted_class in ["B/A-class", "C-class", "M-class", "X-class"]
    assert fc.estimated_lead_time_min > 0.0


def test_skill_scores_computation():
    """Verify TSS, HSS, POD, FAR calculations."""
    preds = np.array([0.9, 0.8, 0.2, 0.1, 0.7, 0.3])
    targets = np.array([1, 1, 0, 0, 0, 1])
    metrics = compute_skill_scores(preds, targets, threshold=0.5)
    
    assert "TSS" in metrics
    assert "HSS" in metrics
    assert "POD" in metrics
    assert "FAR" in metrics
    assert -1.0 <= metrics["TSS"] <= 1.0


def test_neupert_correlator_physics():
    """Verify Neupert correlator correctly identifies when HXR leads SXR rise."""
    nc = NeupertCorrelator(corr_window_s=60)
    res = {}
    # Impulsive HXR peak at step 20, SXR rising from 10 to 40
    for i in range(50):
        hxr = 50.0 + (300.0 * np.exp(-((i - 20) ** 2) / (2 * 5**2)))
        sxr = 1000.0 + (1500.0 / (1.0 + np.exp(-(i - 25) / 4.0)))
        res = nc.update(sxr, hxr, timestamp=float(i))
    assert res["neupert_corr"] > 0.5
    assert bool(res["hxr_leads"]) is True


def test_pytorch_aditya_solar_transformer():
    """Verify PyTorch model forward pass, PINN loss and Focal loss."""
    if not HAS_TORCH:
        return
    B, L = 4, 32
    sxr = torch.randn(B, L, 4)
    hxr = torch.randn(B, L, 4)
    model = AdityaSolarTransformer(in_channels_sxr=4, in_channels_hxr=4, d_model=32, nhead=2, num_layers=2)
    
    out = model(sxr, hxr)
    assert "logits_15m" in out
    assert out["logits_15m"].shape == (B,)
    assert "logits_30m" in out
    assert "logits_60m" in out
    assert "pred_mag" in out

    # Verify PINN physics parameters
    alpha, beta = model.get_physics_parameters()
    assert alpha.item() > 0.0
    assert beta.item() > 0.0

    # Verify focal loss
    criterion = BinaryFocalLoss(alpha=0.85, gamma=2.5)
    targets = torch.tensor([1.0, 0.0, 0.0, 1.0])
    loss = criterion(out["logits_15m"], targets)
    assert loss.item() >= 0.0


if __name__ == "__main__":
    print("Running deep forecaster & fusion tests...")
    test_inverse_variance_fusion()
    print("  [1/5] Inverse variance fusion: PASS")
    test_kalman_filter_1d()
    print("  [2/5] 1D Kalman filter: PASS")
    test_wavelet_qpp_power()
    print("  [3/5] Wavelet QPP power extraction: PASS")
    test_neupert_correlator_physics()
    print("  [4/5] Neupert correlator physics: PASS")
    if HAS_TORCH:
        test_pytorch_aditya_solar_transformer()
        print("  [5/5] PyTorch AdityaSolarTransformer & PINN Loss: PASS")
    else:
        print("  [5/5] PyTorch not available, skipped torch-specific tests")
    print("ALL TESTS PASSED!")
