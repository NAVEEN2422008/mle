# 🔬 Technical Appendix: Solar Flare Nowcasting System

## 📐 Model Architecture Details

### AdityaSolarTransformer (PyTorch)
```python
AdityaSolarTransformer(
    in_channels_sxr=4,      # SXR features per timestep
    in_channels_hxr=4,      # HXR features per timestep
    d_model=64,             # Transformer dimension
    nhead=4,                # Attention heads
    num_layers=3,           # Transformer layers
    dropout=0.1,
    max_seq_len=1000        # Max sequence length
)
```

**Architecture Flow**:
```
Input: [B, L, 4] SXR + [B, L, 4] HXR
    │
    ├─▶ Conv1D + BN + GELU (Tokenization)
    │       │
    │       ├─▶ Transformer Encoder (SXR) ──▶
    │       │                                 │
    │       ├─▶ Transformer Encoder (HXR) ──▶ │
    │       │                                 │
    │       └─▶ Cross-Modal Attention ◀───────┘
    │                     │
    │       ▼
    │   Temporal Pooling (Last + Mean)
    │       │
    │       ▼
    │   Multi-Horizon Heads (15m/30m/60m)
    │       │
    │       ▼
    │   Physics Parameters (α, β)
```

### Physics-Informed Loss
```python
# Neupert PINN Loss: dSXR/dt = α·HXR - β·SXR
class NeupertPhysicsLoss(nn.Module):
    def forward(self, sxr, hxr, dsxr_dt, alpha, beta):
        pred = alpha * hxr - beta * sxr
        return F.mse_loss(dsxr_dt, pred)
```

---

## 📊 Feature Dictionary (22 Features)

| Feature | Formula | Window | Physics |
|---------|---------|--------|---------|
| `log_sxr` | log10(SXR + 1e-9) | - | Log flux |
| `log_hxr` | log10(HXR + 1e-9) | - | Log flux |
| `sxr_over_base` | SXR / median(SXR, 600s) | 600s | Normalized flux |
| `hxr_over_base` | HXR / median(HXR, 600s) | 600s | Normalized flux |
| `sxr_slope_short` | ΔSXR/60s | 60s | Short-term trend |
| `sxr_slope_long` | ΔSXR/600s | 600s | Long-term trend |
| `slope_accel` | short - long | - | Acceleration |
| `hxr_slope_short` | ΔHXR/60s | 60s | HXR trend |
| `hardness` | HXR/SXR | - | Spectral hardening |
| `d_hardness` | Δ(hardness) | - | Hardness evolution |
| `run_diff_hxr` | ΔHXR/60s | 120s | Impulsive onset |
| `run_diff_sxr` | ΔSXR/60s | 120s | SXR impulsive |
| `temp_proxy` | HXR/SXR | - | Spectral hardening |
| `d_temp_proxy` | Δ(temp_proxy) | - | Temp evolution |
| `em_proxy` | SXR × HXR | - | Emission measure |
| `d_em_proxy` | Δ(em_proxy) | - | EM evolution |
| `sxr_var_short` | Var(SXR, 60s) | 60s | Variability |
| `burst_flag` | HXR > μ+5σ | 60s | Burst detection |
| `neupert_corr` | corr(HXR, dSXR/dt) | 120s | Neupert coupling |
| `neupert_alpha` | OLS α in dSXR/dt=α·HXR | 120s | Coupling coeff |
| `neupert_resid` | Residual after Neupert | 120s | Model error |
| `hxr_leads_flag` | HXR onset > SXR onset | - | Lead indicator |
| `time_since_flare_min` | min(t - t_peak) | - | Flare memory |
| `decayed_history` | Σ exp(-Δt/τ) | 6hr | Flare history |

---

## 🎯 Label Construction Details

### Strict Pre-Peak Labeling
```python
def build_labels(timestamps_sec, catalog_peak_times_sec, horizon_s=900,
                 mask_in_flare_s=(-60, 900), min_class_flux=1e-6,
                 peak_fluxes=None):
    """
    Binary labels: catalogue peak in (t, t+horizon] AND t < peak_time
    Samples inside [peak-60s, peak+900s] masked as -1 (excluded)
    """
    peaks = [p for p, f in zip(catalog_peak_times_sec, peak_fluxes)
             if f >= min_class_flux]
    peaks_arr = np.asarray(sorted(peaks))
    
    y = np.zeros(len(timestamps_sec), dtype=int)
    for i, t in enumerate(timestamps_sec):
        nxt = peaks_arr[(peaks_arr > t) & (peaks_arr <= t + horizon_s)]
        if len(nxt) > 0:
            y[i] = 1
    
    # Mask in-flare samples
    mask = np.zeros(len(timestamps_sec), dtype=bool)
    for p in peaks:
        mask |= (timestamps_sec >= p + mask_in_flare_s[0]) & \
                (timestamps_sec <= p + mask_in_flare_s[1])
    y[mask] = -1
    return y
```

### Label Source Priority
1. **Independent Ground Truth** (NOAA) → `label_source="independent_ground_truth"`
2. **Self-Detected** (CUSUM/Hard) → `label_source="self_detected_CIRCULAR"` (circular!)

---

## 📈 Metrics Deep Dive

### Primary: TSS (True Skill Statistic)
```
TSS = POD - POFD = TP/(TP+FN) - FP/(FP+TN)
```
- **Range**: [-1, 1], 0 = no skill, 1 = perfect
- **Why**: Class-ratio insensitive (unlike accuracy)
- **Benchmark**: Bloomfield 2012 M-class optimum TSS=0.53

### Secondary Metrics
| Metric | Formula | Use Case |
|--------|---------|----------|
| **HSS** | 2(TP×TN - FP×FN) / denom | General skill |
| **BSS** | 1 - BS_model/BS_clim | Probabilistic skill |
| **PR-AUC** | ∫ P(R) dR | Imbalanced data |
| **Brier** | mean((p-y)²) | Calibration |
| **ECE** | Σ|acc-conf| | Calibration error |

### Lead-Time Evaluation
```python
def lt_vs_far_curve(peaks_s, alert_times_by_threshold, window_s=1800):
    """Sweep threshold θ: compute POD/FAR/median LT"""
    # Event hit if alert in [p-window, p)
    # Earliest alert = lead time
    # Unmatched alerts = false alarms
```

---

## 🧪 Test Suite Details

### Test Coverage (50 tests)
| Module | Tests | Coverage |
|--------|-------|----------|
| `test_neupert_qc.py` | 20 | Neupert QC bugs |
| `test_phase5_api.py` | 15 | API endpoints |
| `test_phase4_ml.py` | 10 | ML pipeline |
| `test_phase3_ingest.py` | 5 | Data ingest |

### Neupert QC Tests (20 tests)
| Test | Bug Fixed |
|------|-----------|
| `test_baseline_not_zero_when_series_is_zero_inflated` | F5.2 |
| `test_baseline_low_quantile_uses_nonzero_subset` | F5.2 |
| `test_event_finder_refuses_when_baseline_is_zero` | F5.2 |
| `test_event_finder_enforces_enhancement_threshold` | F5.2 |
| `test_failed_fit_sentinel_is_outside_valid_correlation_range` | F5.3 |
| `test_verdict_indeterminate_when_both_models_failed` | F5.3 |
| `test_verdict_never_reports_a_failed_model_as_winner` | F5.3 |
| `test_verdict_requires_actual_coupling` | F5.3 |
| `test_verdict_integral_wins_on_corrected_result` | F5.1 |
| `test_coupling_floor_is_sane` | F5.3 |
| `test_band_selection_rejects_band_overlapping_soft_range` | F5.1 |
| `test_band_selection_never_returns_overlapping_band_silently` | F5.1 |
| `test_band_selection_picks_most_sensitive_eligible_band` | F5.1 |
| `test_band_selection_rejects_dead_channel` | F5.1 |
| `test_pinned_band_prefers_eligible_over_first_match` | F5.1 |
| `test_resample_bridges_nan_gaps` | F5.5 |
| `test_resample_all_nan_returns_nan` | F5.5 |
| `test_resample_interpolates_across_gap` | F5.5 |

---

## 📊 Data Dictionary

### Aditya-L1 Level-1 Products
| Instrument | Product | Cadence | Energy | Detector |
|------------|---------|---------|--------|----------|
| SoLEXS | L1 | 1 s | 2-22 keV | SDD1, SDD2 |
| HEL1OS | L1 | 1 s | 10-150 keV | CdTe (8-70), CZT (20-150) |

### HEL1OS Band Structure
| Detector | Band | Energy Range | Use Case |
|----------|------|--------------|----------|
| CdTe | Band 1 | 5-20 keV | Overlaps SoLEXS |
| CdTe | Band 2 | 20-30 keV | Transition |
| CdTe | Band 3 | 30-40 keV | Transition |
| CdTe | Band 4 | 40-60 keV | **Primary HXR** |
| CdTe | Band 5 | 1.8-90 keV | Broadband |
| CZT | Band 1 | 20-40 keV | **Primary HXR** |
| CZT | Band 2 | 40-60 keV | **Primary HXR** |
| CZT | Band 3 | 60-80 keV | High energy |
| CZT | Band 4 | 80-150 keV | High energy |
| CZT | Band 5 | 18-160 keV | Broadband |

### GTI (Good Time Intervals)
- **SoLEXS**: Multiple intervals per day (eclipse, SAA, calibration)
- **HEL1OS**: Single interval per segment (~12 hours)
- **Alignment**: Intersection of both GTIs required

---

## 🔧 Configuration Reference

### Pipeline Hyperparameters
```python
FlareForecastPipeline(
    horizon_min=15,           # Prediction horizon
    n_folds=4,                # Walk-forward folds
    window_min=30,            # Feature window
    min_class_flux=1000.0,    # nW/m² (≥C1.0)
    use_lightgbm=True,        # LightGBM vs sklearn
    feat_short_s=60,          # Short window (samples)
    feat_long_s=600,          # Long window (samples)
    neupert_win_s=120,        # Neupert window
    theta_grid=0.1-0.95/0.05, # Threshold sweep
    det_h_c_sigma=25.0,       # Hard detector threshold
    det_alpha=0.01,           # CUSUM alpha
)
```

### LightGBM Parameters
```python
LGBMClassifier(
    n_estimators=300,
    learning_rate=0.05,
    num_leaves=15,
    min_child_samples=20,
    subsample=0.8,
    class_weight='balanced',
    random_state=42,
    verbosity=-1
)
```

### Walk-Forward CV
```python
def make_walk_forward_splits(timestamps, n_folds=4, horizon_min=15, window_min=30):
    """Expanding window with embargo ≥ horizon + window"""
    embargo_s = (horizon_min + window_min) * 60
    # Convert to samples using median cadence
    # Train: [0, train_end), Test: [test_start, test_end)
    # Embargo gap between train_end and test_start
```

---

## 🌐 API Reference

### FlareForecastPipeline.run()
```python
report = pipeline.run(
    df,                           # DataFrame: timestamp, soft, hard
    truth_peaks=None,             # [(peak_sec, flux)] for validation
    label_peaks=None              # [(peak_sec, flux)] for training labels
)
```

**Returns**: `PipelineReport` with:
- `oof`: OOF metrics (TSS, HSS, POD, FAR, Brier, PR-AUC, BSS)
- `baseline_compare`: Model vs Climatology vs Persistence
- `lt_far_table`: Lead-time vs FAR sweep
- `beats_baselines`: Boolean
- `n_positives`, `n_labelled`, `label_source`

### evaluate_aditya_real.py Output
```
TSS (θ=0.5):     0.277
TSS (tuned):     0.320
POD:             0.34
FAR:             0.897
PR-AUC:          0.345
Brier:           0.0639
BSS:             -2.169
```

---

## 🐛 Debugging Checklist

### Common Issues
| Symptom | Cause | Fix |
|-------|-------|-----|
| `too few positives` | <4 positives in labels | Check label_peaks, min_class_flux |
| `tsec` wrong | Relative not absolute time | Use `pd.to_datetime().astype('int64')//1e9` |
| `NaN` in features | GTI gaps, NaN propagation | Check `robust_baseline`, `resample_to` |
| `FAR=1.0` | No negatives in labels | Check `mask_in_flare_s` |
| `TSS=0` | No positives in test fold | Check `n_folds`, embargo |

### Debug Commands
```bash
# Debug labels
python -c "
from src.forecast.pipeline import build_labels
import numpy as np
tsec = np.arange(1000)
peaks = [100, 500, 800]
y = build_labels(tsec, peaks, horizon_s=900)
print(np.unique(y, return_counts=True))
"

# Debug features
python -c "
from src.forecast.pipeline import build_causal_features
import pandas as pd
df = pd.DataFrame({'timestamp': pd.date_range('2024-01-01', periods=100, freq='1min'),
                   'soft': np.random.rand(100)*100,
                   'hard': np.random.rand(100)*10})
peaks = [50]
X = build_causal_features(df, peaks)
print(X.columns.tolist())
print(X.head())
"
```

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-09-28 | Initial release: Neupert test + ML benchmark |
| 0.9 | 2026-09-25 | Bug fixes (5 Neupert bugs), 20 regression tests |
| 0.8 | 2026-09-20 | Pipeline refactor, walk-forward CV |
| 0.7 | 2026-09-15 | Aditya-L1 ingest, real data eval |
| 0.6 | 2026-09-10 | GOES live eval, LightGBM integration |
| 0.5 | 2026-09-05 | Neupert analysis, synthetic data audit |

---

## 📞 Support & Contribution

**Issues**: GitHub Issues → `solar-flare-system/issues`
**PRs**: Welcome — run `pytest tests/ -q` before submitting
**Citation**: If using in research, cite the paper (DOI pending)

---

*Technical Appendix v1.0 | solar-flare-system | Aditya-L1 SoLEXS/HEL1OS*