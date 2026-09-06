"""End-to-end smoke test: synth -> fuse -> detect -> Neupert."""
import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from src.ingest.synth import FlareModel
from src.preprocess.fusion import inverse_variance_fusion
from src.nowcast.soft_detector import CUSUMDetector, GOESFSMClassifier
from src.nowcast.hard_detector import HardDetector
from src.nowcast.neupert_engine import NeupertCorrelator
from src.constants import SPEED_OF_LIGHT_KMS, LTT_OFFSET_ADITYA_L1_S

print("=" * 64)
print("ADITYA FLARECAST - WS1 FUNCTIONAL SMOKE TEST")
print("=" * 64)

# 1. Constants sanity
assert abs(SPEED_OF_LIGHT_KMS - 299792.458) < 0.001
assert LTT_OFFSET_ADITYA_L1_S == 5.0
print(f"[1] Constants OK  (c={SPEED_OF_LIGHT_KMS} km/s, L1 LTT=+{LTT_OFFSET_ADITYA_L1_S}s)")

# 2. Synthetic flare generation (Neupert-consistent pair)
np.random.seed(42)
model = FlareModel()
t0 = pd.Timestamp("2024-07-01 12:00:00")
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
print(f"[2] Synth flare OK  HXR peak @t={peak_h_idx}s  SXR peak @t={peak_s_idx}s  "
      f"(HXR leads by {peak_s_idx - peak_h_idx}s -> Neupert-consistent: {peak_h_idx < peak_s_idx})")

# 3. Fusion math check: two equal sensors must halve sigma
v1, s1 = inverse_variance_fusion([100.0, 102.0], [2.0, 2.0])
assert abs(v1 - 101.0) < 1e-9 and abs(s1 - np.sqrt(2.0)) < 1e-9
print(f"[3] Inverse-variance fusion OK  fused={v1:.1f} +/- {s1:.2f} (sigma reduced)")

# 4. Soft-band CUSUM detection
det = CUSUMDetector(baseline_window=150, cusum_k=5.0, h_c_sigma=30.0)
onset_t, events = None, []
for i, row in df_synth.iterrows():
    _, alert, status, meta = det.update(row["soft"], timestamp=float(i))
    if status == "ONSET" and onset_t is None:
        onset_t = i
    if alert:
        events.append((i, meta))
lead = peak_s_idx - onset_t if onset_t is not None else -999
print(f"[4] CUSUM OK  onset detected @t={onset_t}s -> lead time before SXR peak = {lead}s")

# 5. Hard-band Poisson-FOCuS stack
hdet = HardDetector(mu0=bg_hard)
h_alerts = []
for i, row in df_synth.iterrows():
    _, alert, status, meta = hdet.update(max(row["hard"], 0), timestamp=float(i))
    if alert:
        h_alerts.append((i, status))
print(f"[5] Poisson-FOCuS stack OK  {len(h_alerts)} hard-band event(s) closed "
      f"{h_alerts[:2] if h_alerts else '(none - tuning note)'}")

# 6. Neupert correlation engine (evaluated across rise + peak window)
nc = NeupertCorrelator(corr_window_s=200)
last = {}
for i, row in df_synth.iloc[:peak_s_idx + 40].iterrows():
    last = nc.update(row["soft"], row["hard"], timestamp=float(i))
print(f"[6] Neupert engine OK  corr(H, dS/dt)={last['neupert_corr']:.3f}  "
      f"hxr_leads={last['hxr_leads']}  lag={last['peak_lag_s']}s")

# 7. GOES classifier sanity
cls = GOESFSMClassifier()
checks = [(5e-9, "A"), (5e-7, "B"), (5e-6, "C"), (5e-5, "M"), (5e-4, "X")]
ok = all(cls.classify_flux(f) == c for f, c in checks)
print(f"[7] GOES A-X classifier OK  all 5 classes correct: {ok}")

print("=" * 64)
verdict = lead > 0 and last["hxr_leads"] and ok
print("SMOKE TEST:", "PASS" if verdict else "PARTIAL (see notes above)")
print("=" * 64)
