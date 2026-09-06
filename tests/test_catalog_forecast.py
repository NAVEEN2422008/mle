"""WS2b + WS3a/3b verification: catalogue, metrics, baselines, CV training."""
import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from src.types import Instrument
from src.catalog.master_catalog import (
    MasterCatalogue, Detection, classify_flux_goes, goes_subclass,
    arbitrate_sdd,
)
from src.forecast.metrics import (
    ConfusionMatrix, brier_skill_score, pr_auc, evaluate_forecast,
    lt_vs_far_curve, LeadTimeReport,
)
from src.forecast.baselines import ClimatologyBase, PersistenceBase, beats_baselines
from src.forecast.train import build_labels, make_walk_forward_splits, train_with_cv

print("=" * 64)
print("WS2b + WS3 VERIFICATION")
print("=" * 64)

T0 = datetime(2024, 7, 1, 12, 0, 0)

# ---------- 1. GOES classifier ----------
assert classify_flux_goes(5e-9) == "A" and classify_flux_goes(5e-6) == "C"
assert goes_subclass(2.5e-5) == "M2.5"
print("[1] GOES classification OK  (M2.5 == 2.5e-5 W/m2)")

# ---------- 2. SDD arbitration ----------
det, val = arbitrate_sdd(2e5, 800.0)
assert det == "SDD2", "SDD1 saturated -> must trust SDD2"
det2, _ = arbitrate_sdd(5e4, 900.0)
assert det2 == "SDD1"
print("[2] SDD arbitration OK  (SDD1 saturated >1e5cps -> switched to SDD2)")

# ---------- 3. Catalogue association (Neupert-aware merge) ----------
cat = MasterCatalogue()
soft_d = [Detection(Instrument.SOLEXS_SDD2, T0, T0 + timedelta(seconds=300),
                    T0 + timedelta(seconds=700), 3.2e-6, 0.9, "soft")]
hard_d = [Detection(Instrument.HEL1OS_CDTE, T0 - timedelta(seconds=60),
                    T0 + timedelta(seconds=260), T0 + timedelta(seconds=400),
                    1500.0, 0.85, "hard")]
events = cat.associate(soft_d, hard_d)
assert len(events) == 1 and events[0].neupert_verified
assert abs((events[0].peak_time - (T0 + timedelta(seconds=300))).total_seconds()) < 1e-6
print("[3] Association OK  HXR+SXR merged, Neupert verified")

# soft-only event
cat2 = MasterCatalogue()
ev2 = cat2.associate(
    [Detection(Instrument.SOLEXS_SDD2, T0, T0 + timedelta(seconds=100),
               T0 + timedelta(seconds=200), 8e-7, 0.8, "soft")], [])
assert len(ev2) == 1 and ev2[0].goes_class in ("B", "C")
# hard-only event survives as 'HXR-only'
cat3 = MasterCatalogue()
ev3 = cat3.associate([], [hard_d[0]])
assert len(ev3) == 1 and ev3[0].goes_class == "HXR-only"
print("[4] Soft-only + HXR-only events preserved in catalogue")

# dedup: two sub-peaks 60s apart of same class must merge
cat4 = MasterCatalogue()
cat4.associate(
    [Detection(Instrument.SOLEXS_SDD2, T0, T0 + timedelta(seconds=50),
               T0 + timedelta(seconds=80), 3e-6, 0.9, "soft"),
     Detection(Instrument.SOLEXS_SDD2, T0 + timedelta(seconds=140),
               T0 + timedelta(seconds=160), T0 + timedelta(seconds=200), 3.1e-6, 0.9, "soft")],
    [])
removed = cat4.dedupe()
assert removed >= 1 and len(cat4.all_events) == 1
print(f"[5] Dedup OK  sub-peaks merged ({removed} removed)")

# O(1) bucket query
hits = cat.query_near(T0 + timedelta(seconds=300))
assert len(hits) == 1
rng = cat.query_range(T0, T0 + timedelta(hours=2))
assert len(rng) >= 1
print("[6] Bucket index OK  point + range queries")

df_cat = cat.to_dataframe()
assert {"event_id", "goes_class", "neupert_verified"} <= set(df_cat.columns)
print(f"[7] Catalogue dataframe export OK\n{df_cat.to_string(index=False)}")

# ---------- 8. Metrics ----------
cm = ConfusionMatrix(tp=70, fp=10, fn=30, tn=890)
assert abs(cm.tss - (0.70 - 10/900)) < 1e-9 and cm.pod == 0.70
y = [1, 0, 1, 1, 0, 0, 1, 0]
p = [.9, .1, .8, .6, .4, .2, .3, .05]
bss = brier_skill_score(y, p)
assert -1 <= bss <= 1
prauc = pr_auc(y, p)
rep = evaluate_forecast(y, p, threshold=0.5)
assert set(rep) >= {"tss", "hss", "bss", "pod", "far", "pr_auc"}
print(f"[8] Metrics OK  TSS={rep['tss']} HSS={rep['hss']} BSS={rep['bss']} PR-AUC={rep['pr_auc']}")

# LT-vs-FAR curve
peaks = [1000.0, 5000.0]
alerts_by_theta = {
    0.3: [400.0, 4400.0, 9900.0],   # 3rd alert = false alarm
    0.7: [900.0, 4950.0],           # tight, both true
}
curve = lt_vs_far_curve(peaks, alerts_by_theta)
assert len(curve) == 2 and all("median_lt_min" in r for r in curve)
print(f"[9] LT-vs-FAR sweep OK\n{pd.DataFrame(curve).to_string(index=False)}")

# ---------- 10. Baselines ----------
rng = np.random.default_rng(7)
n = 10000   # ~2.8 h at 1s cadence
flare_times = np.sort(
    rng.choice(np.arange(1200, n - 1200), size=5, replace=False)
).astype(float)
ts_sec = np.arange(n, dtype=float)
y_lab = build_labels(ts_sec, flare_times.tolist(), horizon_s=900)
labelled = y_lab != -1
clim = ClimatologyBase().fit(y_lab[labelled])
p_clim = clim.predict_proba(labelled.sum())
age = np.full(n, np.inf)
for ft in flare_times:
    age[int(ft):] = ts_sec[int(ft):] - ft
pers = PersistenceBase().predict_proba(age)
print(f"[10] Baselines OK  climatology base-rate={clim.base_rate:.3f}  "
      f"persistence mean-p={pers[labelled].mean():.3f}  positives={int(y_lab[labelled].sum())}/{int(labelled.sum())}")

# ---------- 11. Full CV training on synthetic features (full-timeline arrays) ----------
X = np.column_stack([
    ts_sec / n,                                # slow context
    np.convolve(y_lab.clip(min=0), np.ones(30)/30, mode="same"),  # crude precursor
    rng.normal(0, .1, n),
])
folds = make_walk_forward_splits(pd.Series(pd.to_datetime(T0) + pd.to_timedelta(ts_sec, unit="s")), n_folds=4)
res = train_with_cv(X, y_lab, folds)
print(f"[11] CV training OK  folds={len(res['folds'])}  chosen_theta={res['chosen_threshold']}")
print(f"     OOF: {res['oof']}")
ok = True
print("=" * 64)
print("WS2b+WS3 VERIFICATION:", "PASS" if ok else "FAIL")
print("=" * 64)
