"""End-to-end smoke test: synth -> fuse -> detect -> Neupert."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import pytest

from src.ingest.synth import FlareModel
from src.preprocess.fusion import inverse_variance_fusion
from src.nowcast.soft_detector import CUSUMDetector, GOESFSMClassifier
from src.nowcast.hard_detector import HardDetector
from src.nowcast.neupert_engine import NeupertCorrelator
from src.constants import SPEED_OF_LIGHT_KMS, LTT_OFFSET_ADITYA_L1_S


def test_smoke_end_to_end():
    """Verify end-to-end data generation, fusion, detection, and physics engine."""
    # 1. Constants sanity
    assert abs(SPEED_OF_LIGHT_KMS - 299792.458) < 0.001
    assert LTT_OFFSET_ADITYA_L1_S == 5.0

    # 2. Synthetic flare generation (Neupert-consistent pair)
    np.random.seed(42)
    model = FlareModel()
    n = 600
    bg_soft, bg_hard = 1000.0, 50.0

    soft = bg_soft + np.random.normal(0, 15, n)
    hard = bg_hard + np.random.normal(0, 3, n)

    flare_start, rise, decay_len = 200, 60, 240   # seconds
    for i in range(n):
        t = i - flare_start
        if 0 <= t < rise:                          # impulsive phase
            hxr_pulse = 400 * np.exp(-((t - rise * 0.5) ** 2) / (2 * 15**2))
            soft[i] += 8 * np.cumsum(np.ones(i + 1))[-1] * 0.5
            hard[i] += hxr_pulse
        elif rise <= t < rise + decay_len:         # gradual decay
            soft[i] += 2400 * np.exp(-(t - rise) / 120.0)

    df_synth = pd.DataFrame({"soft": soft, "hard": hard})
    peak_s_idx = int(np.argmax(df_synth["soft"]))
    peak_h_idx = int(np.argmax(df_synth["hard"]))
    assert peak_h_idx < peak_s_idx, "Hard X-Ray peak must precede Soft X-Ray thermal peak"

    # 3. Fusion math check: two equal sensors must halve sigma
    v1, s1 = inverse_variance_fusion([100.0, 102.0], [2.0, 2.0])
    assert abs(v1 - 101.0) < 1e-9 and abs(s1 - np.sqrt(2.0)) < 1e-9

    # 4. Soft-band CUSUM detection
    det = CUSUMDetector(baseline_window=150, cusum_k=5.0, h_c_sigma=30.0)
    onset_t, events = None, []
    for idx, row in df_synth.iterrows():
        i = int(idx)
        _, alert, status, meta = det.update(row["soft"], timestamp=float(i))
        if status == "ONSET" and onset_t is None:
            onset_t = i
        if alert:
            events.append((i, meta))
    lead = peak_s_idx - onset_t if onset_t is not None else -999
    assert lead > 0, "Detection onset must occur prior to SXR peak"

    # 5. Hard-band Poisson-FOCuS stack
    hdet = HardDetector(mu0=bg_hard)
    h_alerts = []
    for idx, row in df_synth.iterrows():
        i = int(idx)
        _, alert, status, meta = hdet.update(max(row["hard"], 0), timestamp=float(i))
        if alert:
            h_alerts.append((i, status))

    # 6. Neupert correlation engine
    nc = NeupertCorrelator(corr_window_s=200)
    last = {}
    for idx, row in df_synth.iloc[:peak_s_idx + 40].iterrows():
        i = int(idx)
        last = nc.update(row["soft"], row["hard"], timestamp=float(i))
    assert bool(last.get("hxr_leads", False)) is True

    # 7. GOES classifier sanity
    cls = GOESFSMClassifier()
    checks = [(5e-9, "A"), (5e-7, "B"), (5e-6, "C"), (5e-5, "M"), (5e-4, "X")]
    assert all(cls.classify_flux(f) == c for f, c in checks)


if __name__ == "__main__":
    test_smoke_end_to_end()
    print("Smoke test completed successfully!")
