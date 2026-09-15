"""Automated Unit Tests for Phase 2: 30-Dimensional Precursor Physics Feature Engineering."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.preprocess.fusion import compute_physics_features, compute_wavelet_qpp_power


def test_compute_30d_physics_features():
    """Verify that all 30 precursor physics features are computed cleanly with no NaNs/Infs."""
    np.random.seed(42)
    n = 200
    times = pd.date_range("2024-05-15 00:00:00", periods=n, freq="1s")
    
    # Synthetic rising flare profile
    t = np.arange(n)
    soft = 100.0 + 50.0 * np.exp(-((t - 100) / 20.0) ** 2) + np.random.normal(0, 1.0, n)
    hard = 20.0 + 30.0 * np.exp(-((t - 90) / 10.0) ** 2) + np.random.normal(0, 0.5, n) # HXR leads SXR
    
    df = pd.DataFrame({"timestamp": times, "soft": soft, "hard": hard})
    
    featured = compute_physics_features(df, cadence_s=1.0)
    
    # Check that all 30 numbered features are present
    expected_f_keys = [f"f{i:02d}_" for i in range(1, 31)]
    present_cols = featured.columns.tolist()
    
    for k in expected_f_keys:
        matched = [c for c in present_cols if c.startswith(k)]
        assert len(matched) >= 1, f"Missing feature starting with {k}"
        
        # Verify no unhandled NaNs or Infs
        assert not bool(featured[matched[0]].isna().any()), f"Feature {matched[0]} contains NaNs"
        assert not bool(np.isinf(featured[matched[0]].to_numpy()).any()), f"Feature {matched[0]} contains Infs"


def test_neupert_cross_band_acceleration():
    """Verify that 1st derivative (velocity) and 2nd derivative (acceleration) capture flare surges."""
    n = 100
    t = np.linspace(0, 10, n)
    # Quadratic rise -> constant acceleration
    soft = 10.0 + 2.0 * (t ** 2)
    hard = 5.0 + 1.5 * t
    
    df = pd.DataFrame({"timestamp": pd.date_range("2024-05-15 00:00:00", periods=n, freq="1s"), "soft": soft, "hard": hard})
    featured = compute_physics_features(df, cadence_s=1.0)
    
    # SXR 1st derivative should be positive and increasing
    d_soft = np.asarray(featured["f05_d_soft_dt"].values, dtype=float)
    assert bool((d_soft[10:90] > 0).all())
    
    # SXR 2nd derivative (acceleration) should be positive
    d2_soft = np.asarray(featured["f07_d2_soft_dt2"].values, dtype=float)
    assert bool((d2_soft[10:90] > 0).all())


def test_morlet_wavelet_qpp_power():
    """Verify that Morlet continuous wavelet detects high-frequency pulsations."""
    n = 200
    t = np.linspace(0, 20, n)
    # 0.5 Hz high-frequency oscillation burst between index 50 and 100
    signal_burst = np.sin(2 * np.pi * 0.5 * t)
    signal_burst[:50] = 0.0
    signal_burst[100:] = 0.0
    
    qpp = compute_wavelet_qpp_power(signal_burst, num_scales=8)
    
    assert len(qpp) == n
    # Power inside the burst region should be significantly greater than outside
    assert np.mean(qpp[60:90]) > 5.0 * np.mean(qpp[10:40])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
