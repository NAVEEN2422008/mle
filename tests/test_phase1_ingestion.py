"""Automated Unit Tests for Phase 1: Multi-Satellite Ingestion & Synchronization."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.preprocess.merge import (
    apply_light_travel_time_correction,
    despike_mad_series,
    interpolate_pchip_series,
    synchronize_timestamps,
)
from src.constants import LTT_OFFSET_ADITYA_L1_S


def test_ltt_correction():
    """Verify that Aditya-L1 observations receive exact +5.0s LTT shift to Earth frame."""
    t0 = pd.Timestamp("2024-05-15 12:00:00")
    df = pd.DataFrame({
        "timestamp": [t0, t0 + pd.Timedelta(seconds=1)],
        "counts": [100.0, 105.0]
    })
    
    # Aditya-L1
    df_l1 = apply_light_travel_time_correction(df, "ADITYA_L1_SOLEXS")
    expected_t0 = t0 + pd.Timedelta(seconds=LTT_OFFSET_ADITYA_L1_S)
    assert df_l1["timestamp"].iloc[0] == expected_t0
    assert df_l1["ltt_offset_s"].iloc[0] == 5.0

    # GOES (Earth Geostationary)
    df_goes = apply_light_travel_time_correction(df, "GOES")
    assert df_goes["timestamp"].iloc[0] == t0
    assert df_goes["ltt_offset_s"].iloc[0] == 0.0


def test_mad_despiking():
    """Verify that cosmic ray spikes are suppressed while flare slopes remain intact."""
    np.random.seed(42)
    t = np.arange(100)
    # Background flux + rising flare
    flux = 50.0 + 2.0 * t + np.random.normal(0, 1.0, 100)
    
    # Inject isolated cosmic ray spike at index 50
    flux[50] = 500.0 # 10x spike
    
    s = pd.Series(flux)
    cleaned = despike_mad_series(s, window_size=15, threshold_sigma=4.0)
    
    # Spike at 50 should be replaced with local median (~150)
    assert cleaned.iloc[50] < 200.0
    # Flare slope at index 40 and 60 should remain unchanged
    assert abs(cleaned.iloc[40] - s.iloc[40]) < 1e-3
    assert abs(cleaned.iloc[60] - s.iloc[60]) < 1e-3


def test_pchip_interpolation_and_outage_preservation():
    """Verify PCHIP fills short gaps <= max_gap_steps and preserves large outages as NaN."""
    # 300 steps
    vals = np.sin(np.linspace(0, 4*np.pi, 300)) * 100.0 + 150.0
    s = pd.Series(vals)
    
    # Short gap (10 steps)
    s.iloc[50:60] = np.nan
    # Long outage (200 steps)
    s.iloc[100:300] = np.nan
    
    interpolated = interpolate_pchip_series(s, max_gap_steps=30)
    
    # Short gap should be smoothly filled
    assert not interpolated.iloc[50:60].isna().any()
    # Long outage should remain NaN
    assert interpolated.iloc[150:250].isna().all()


def test_synchronize_timestamps_multi_satellite():
    """Verify end-to-end synchronization of SoLEXS, HEL1OS, and GOES streams."""
    t0 = pd.Timestamp("2024-05-15 00:00:00")
    times = pd.date_range(t0, periods=60, freq="1s")
    
    df_solexs = pd.DataFrame({"timestamp": times, "counts": np.random.uniform(50, 60, 60)})
    df_hel1os = pd.DataFrame({"timestamp": times, "counts": np.random.uniform(10, 20, 60)})
    df_goes = pd.DataFrame({
        "timestamp": times + pd.Timedelta(seconds=5), # Aligned with L1 Earth arrival
        "flux_long": np.random.uniform(1e-7, 2e-7, 60),
        "flux_short": np.random.uniform(1e-8, 2e-8, 60),
    })
    
    synced = synchronize_timestamps(
        solexs_df=df_solexs,
        hel1os_df=df_hel1os,
        goes_df=df_goes,
        cadence_s=1,
        max_gap_s=60,
    )
    
    assert not synced.empty
    assert "timestamp" in synced.columns
    assert "soft" in synced.columns
    assert "hard" in synced.columns
    assert len(synced) >= 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
