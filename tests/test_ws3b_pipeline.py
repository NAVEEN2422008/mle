"""WS3b: real pipeline run -> first TSS / lead-time numbers."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import pytest

from src.forecast.pipeline import FlareForecastPipeline


def test_ws3b_pipeline_run():
    """Verify full end-to-end forecasting pipeline on synthetic multi-flare stream."""
    rng = np.random.default_rng(11)
    T0 = pd.Timestamp("2024-07-01 00:00:00")
    N = 4 * 3600
    bg_s, bg_h = 1000.0, 50.0

    soft = bg_s + np.abs(rng.normal(0, 12, N))
    hard = bg_h + np.abs(rng.normal(0, 2.5, N))

    truth = []          # (peak_sec, approx_class_flux_scale)
    specs = [           # (start_sec, rise, decay, sxr_amp_counts, hxr_amp_counts, cls)
        (900,   60, 300, 1200, 260, "C"),
        (2100,  45, 200, 700,  140, "B"),
        (3600,  90, 600, 2600, 520, "M"),
        (5400,  60, 400, 1500, 300, "C"),
        (6800,  40, 180, 500,  110, "B"),
        (8300, 120, 900, 5200, 950, "X"),
        (10600, 70, 450, 1900, 380, "C"),
        (12600, 55, 350, 1300, 270, "C"),
    ]
    for start, rise, decay, amp_s, amp_h, cls in specs:
        peak_t = start + int(rise * 0.5)
        for i in range(max(start - 60, 0), min(start + rise + decay, N)):
            t = i - start
            if 0 <= t < rise:
                g = np.exp(-((t - rise * 0.5) ** 2) / (2 * (rise / 4) ** 2))
                soft[i] += amp_s * np.interp(t, [0, rise], [0.15, 1.0])
                hard[i] += amp_h * g
            elif t >= rise:
                soft[i] += amp_s * np.exp(-(t - rise) / (decay / 3))
                hard[i] += amp_h * 0.15 * np.exp(-(t - rise) / 40)
        truth.append((float(peak_t), float(amp_s)))

    df = pd.DataFrame({
        "timestamp": pd.date_range(T0, periods=N, freq="1s"),
        "soft": soft,
        "hard": hard,
    })

    pipe = FlareForecastPipeline(horizon_min=10, n_folds=4, use_lightgbm=True, det_h_c_sigma=15.0)
    rep = pipe.run(df, truth_peaks=truth)

    assert rep.n_catalogue_peaks >= 5, "Detector must identify at least 5 flares"
    tc = getattr(rep, "truth_check", {})
    matched = tc.get("matched_within_300s", 0)
    assert matched >= max(len(truth) - 2, 5), f"Catalogue truth mismatch: {tc}"


if __name__ == "__main__":
    test_ws3b_pipeline_run()
    print("WS3b pipeline test completed successfully!")
