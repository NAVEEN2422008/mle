# 📊 Data Dictionary: Solar Flare Nowcasting System

## 📁 Data Inventory

### Raw Data (`data/raw/`)
| File | Instrument | Date | Size | Description |
|------|------------|------|------|-------------|
| `AL1_SLX_L1_20240510_v1.0.zip` | SoLEXS | 2024-05-10 | 11 MB | X3.9 flare (HEL1OS gap) |
| `AL1_SLX_L1_20240511_v1.0.zip` | SoLEXS | 2024-05-11 | 12 MB | X5.8 flare |
| `AL1_SLX_L1_20240514_v1.0.zip` | SoLEXS | 2024-05-14 | 11 MB | X8.7 flare |
| `AL1_SLX_L1_20241001_v1.0.zip` | SoLEXS | 2024-10-01 | 9 MB | X7.1 flare |
| `AL1_SLX_L1_20241003_v1.0.zip` | SoLEXS | 2024-10-03 | 10 MB | X9.0 flare |
| `HLS_20240510_065424_18323sec_lev1_V111.zip` | HEL1OS | 2024-05-10 | 45 MB | X3.9 (starts after peak) |
| `HLS_20240511_000005_22291sec_lev1_V111.zip` | HEL1OS | 2024-05-11 | 296 MB | X5.8 flare |
| `HLS_20240514_120751_42723sec_lev1_V111.zip` | HEL1OS | 2024-05-14 | 485 MB | X8.7 flare |
| `HLS_20241001_120001_43189sec_lev1_V111.zip` | HEL1OS | 2024-10-01 | 244 MB | X7.1 flare |
| `HLS_20241003_120003_43190sec_lev1_V111.zip` | HEL1OS | 2024-10-03 | 231 MB | X9.0 flare |

**Total**: 10 archives, ~1.1 GB

---

## 📊 Processed Data Schema

### Pipeline Input DataFrame (`df_pipe`)
| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `timestamp` | datetime64[ns, UTC] | UTC | Sample timestamp |
| `soft` | float64 | cts/s | SoLEXS SDD2 (2-22 keV) |
| `hard` | float64 | cts/s | HEL1OS CZT 40-60 keV |
| `date` | string | YYYYMMDD | Observation date |

### Feature DataFrame (`X` from `build_causal_features`)
| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `log_sxr` | float64 | log(cts/s) | log10(SXR + 1e-9) |
| `log_hxr` | float64 | log(cts/s) | log10(HXR + 1e-9) |
| `sxr_over_base` | float64 | ratio | SXR / median(SXR, 600s) |
| `hxr_over_base` | float64 | ratio | HXR / median(HXR, 600s) |
| `sxr_slope_short` | float64 | cts/s² | ΔSXR/60s |
| `sxr_slope_long` | float64 | cts/s² | ΔSXR/600s |
| `slope_accel` | float64 | cts/s² | short - long slope |
| `hxr_slope_short` | float64 | cts/s² | ΔHXR/60s |
| `hardness` | float64 | ratio | HXR/SXR (spectral hardening) |
| `d_hardness` | float64 | ratio/s | Δ(hardness) |
| `run_diff_hxr` | float64 | cts/s | ΔHXR/60s (impulsive) |
| `run_diff_sxr` | float64 | cts/s | ΔSXR/60s |
| `temp_proxy` | float64 | ratio | HXR/SXR (temp proxy) |
| `d_temp_proxy` | float64 | ratio/s | Δ(temp_proxy) |
| `em_proxy` | float64 | cts²/s² | SXR × HXR (EM proxy) |
| `d_em_proxy` | float64 | cts²/s³ | Δ(em_proxy) |
| `sxr_var_short` | float64 | cts²/s² | Var(SXR, 60s) |
| `burst_flag` | float64 | 0/1 | HXR > μ+5σ (60s) |
| `neupert_corr` | float64 | [-1,1] | corr(HXR, dSXR/dt) 120s |
| `neupert_alpha` | float64 | - | OLS α in dSXR/dt=α·HXR |
| `neupert_resid` | float64 | cts/s | Residual after Neupert |
| `hxr_leads_flag` | int | 0/1 | HXR onset > SXR onset |
| `time_since_flare_min` | float64 | min | Min since last flare |
| `decayed_history` | float64 | - | Σ exp(-Δt/τ), τ=6hr |

---

## 🏷️ Label Schema (`y`)

### Label Values
| Value | Meaning |
|-------|---------|
| `1` | Positive: flare peak in (t, t+15min] AND t < peak_time |
| `0` | Negative: no flare in horizon |
| `-1` | Masked: in [peak-60s, peak+900s] (in-flare/decay) |

### Label Construction Parameters
```python
build_labels(
    timestamps_sec,           # Absolute Unix seconds
    catalog_peak_times_sec,   # NOAA peak times (Unix sec)
    horizon_s=900,            # 15 min = 900s
    mask_in_flare_s=(-60, 900),  # Mask [peak-60s, peak+900s]
    min_class_flux=1e-6,      # GOES 1-8Å ≥ C1.0 (W/m²)
    peak_fluxes=...           # GOES peak fluxes (W/m²)
)
```

---

## 📈 Evaluation Metrics Schema

### PipelineReport Fields
| Field | Type | Description |
|-------|------|-------------|
| `n_samples` | int | Total samples |
| `n_labelled` | int | Samples with y ≠ -1 |
| `n_positives` | int | Samples with y=1 |
| `n_catalogue_peaks` | int | Self-detected peaks |
| `detected_peaks` | List[float] | Peak times (sec) |
| `label_source` | str | "independent_ground_truth" or "self_detected_CIRCULAR" |
| `n_label_events` | int | Number of label events |
| `horizon_min` | int | Prediction horizon (min) |
| `chosen_threshold` | float | Operating threshold |
| `oof` | dict | OOF metrics dict |
| `baseline_compare` | dict | Model vs baselines |
| `lt_far_table` | List[dict] | LT-vs-FAR sweep |
| `beats_baselines` | bool | Model > baselines |

### OOF Metrics Dict (`report.oof["model"]`)
| Key | Type | Description |
|-----|------|-------------|
| `threshold` | float | Operating threshold |
| `pod` | float | Probability of Detection |
| `far` | float | False Alarm Ratio |
| `tss` | float | True Skill Statistic |
| `hss` | float | Heidke Skill Score |
| `bss` | float | Brier Skill Score |
| `brier` | float | Brier Score |
| `pr_auc` | float | PR-AUC |

### Baseline Compare (`report.baseline_compare`)
| Key | Type | Description |
|-----|------|-------------|
| `model` | dict | Model metrics at chosen θ |
| `climatology` | dict | Climatology baseline |
| `persistence` | dict | Persistence baseline |
| `oof_coverage_frac` | float | OOF coverage fraction |

---

## 🛰️ Aditya-L1 Instrument Specs

### SoLEXS (Solar Low Energy X-ray Spectrometer)
| Parameter | Value |
|-----------|-------|
| Energy Range | 2–22 keV |
| Detectors | SDD1, SDD2 (7.1 mm² each) |
| Cadence | 1 s |
| Energy Resolution | 170 eV @ 5.9 keV |
| FOV | 6° × 6° |
| Dynamic Range | 10⁻⁴ – 10⁴ cts/s |

### HEL1OS (High Energy L1 Orbiting Spectrometer)
| Parameter | Value |
|-----------|-------|
| Energy Range | 10–150 keV |
| Detectors | CdTe (8–70 keV), CZT (20–150 keV) |
| CdTe Area | 0.5 cm² |
| CZT Area | 32 cm² |
| Cadence | 1 s |
| Energy Resolution | ~1 keV @ 60 keV |
| FOV | 6° × 6° |

### HEL1OS Band Definitions
| Detector | Band | Energy Range | Use Case |
|----------|------|--------------|----------|
| CdTe | Band 1 | 5–20 keV | Overlaps SoLEXS |
| CdTe | Band 2 | 20–30 keV | Transition |
| CdTe | Band 3 | 30–40 keV | Transition |
| CdTe | Band 4 | 40–60 keV | Transition |
| CdTe | Band 5 | 1.8–90 keV | Broadband |
| CZT | Band 1 | 20–40 keV | **Primary HXR** |
| CZT | Band 2 | 40–60 keV | **Primary HXR** |
| CZT | Band 3 | 60–80 keV | High energy |
| CZT | Band 4 | 80–150 keV | High energy |
| CZT | Band 5 | 18–160 keV | Broadband |

---

## 🌐 External Data Sources

### NOAA SWPC
| Endpoint | Data | Cadence |
|----------|------|---------|
| `https://services.swpc.noaa.gov/json/goes/primary/xray-flares-latest.json` | Flare events | Real-time |
| `https://services.swpc.noaa.gov/json/goes/primary/xrays-1-minute.json` | XRS flux | 1 min |

### PRADAN (ISRO)
| Portal | URL |
|--------|-----|
| Main | https://pradan.issdc.gov.in/al1/ |
| SoLEXS | `/al1/protected/browse.xhtml?id=solexs` |
| HEL1OS | `/al1/protected/browse.xhtml?id=hel1os` |

---

## 🔧 Environment & Dependencies

### Core Requirements
```txt
numpy>=1.24
pandas>=2.0
scikit-learn>=1.3
lightgbm>=4.0
torch>=2.0 (optional, for deep_forecaster)
matplotlib>=3.7
seaborn>=0.12
astropy>=5.3
```

### Optional (for deep learning)
```txt
torch>=2.0
torchvision>=0.15
```

---

## 📝 File Naming Conventions

### PRADAN Archives
```
SoLEXS: AL1_SLX_L1_YYYYMMDD_vM.N.zip
HEL1OS: HLS_YYYYMMDD_HHMMSS_XXXXsec_lev1_VNNN.zip
```

### Extracted FITS
```
SoLEXS: AL1_SOLEXS_YYYYMMDD_SDD{1,2}_L1.lc.gz
HEL1OS: lightcurve_cdte{1,2}.fits, lightcurve_czt{1,2}.fits
GTI: aux/gticdte{1,2}.fits, aux/gticzt{1,2}.fits
```

---

## 🔑 Key Constants

```python
# Physical constants
SOLEXS_HIGH_KEV = 22.0          # SoLEXS upper energy (keV)
C1_WM2 = 1e-6                   # C1.0 flare threshold (W/m²)
MIN_CLASS_FLUX_NWM2 = 1000.0    # nW/m² (pipeline units)

# Time constants
HORIZON_S = 15 * 60             # 15 min = 900s
WINDOW_S = 30 * 60              # 30 min = 1800s
EMBARGO_S = (15 + 30) * 60      # 45 min = 2700s
NEUPERT_WIN_S = 120             # 2 min
MASK_IN_FLARE_S = (-60, 900)    # [peak-60s, peak+900s]

# Detector thresholds
DET_H_C_SIGMA = 25.0            # Hard detector CUSUM threshold
DET_ALPHA = 0.01                # CUSUM alpha
BURST_SIGMA = 5.0               # Burst detection sigma
MIN_COUPLING_R = 0.3            # Minimum |r| for verdict
FIT_FAILED = -9.0               # Sentinel for failed fits
```

---

## 📂 Directory Structure

```
solar-flare-system/
├── data/
│   ├── raw/                    # 10 PRADAN archives (~1.1 GB)
│   ├── goes_cache/             # GOES XRS cache
│   └── noaa_xclass_labels.csv  # Manual X-class labels
├── paper/
│   ├── paper.tex               # LaTeX manuscript
│   ├── PAPER_DRAFT.md          # Markdown version
│   ├── PAPER_DRAFT.docx        # Word document
│   ├── references.bib          # 38 references
│   └── figures/                # 10 figures (PDF+PNG)
├── scripts/
│   ├── evaluate_aditya_real.py     # Main evaluation
│   ├── neupert_analysis.py         # Neupert physics test
│   ├── evaluate_live_data.py       # GOES live eval
│   ├── generate_figures.py         # Figure generation
│   ├── bulk_download.py            # PRADAN bulk download
│   ├── download_with_playwright.py # Playwright automation
│   └── debug_page.py               # Page debugging
├── src/
│   ├── forecast/
│   │   ├── pipeline.py         # Main pipeline
│   │   ├── deep_forecaster.py  # Transformer + NumPy fallback
│   │   ├── metrics.py          # TSS, HSS, BSS, PR-AUC, etc.
│   │   ├── train.py            # Walk-forward CV, LightGBM
│   │   ├── baselines.py        # Climatology, Persistence
│   │   ├── alerts.py           # Alert engine
│   │   ├── deep_models.py      # Transformer, CNN-LSTM
│   │   ├── forecast_model.py   # LightGBM wrapper
│   │   ├── stacking_meta_learner.py
│   │   └── multi_tier_pipeline.py
│   ├── ingest/
│   │   ├── aditya_l1.py        # SoLEXS+HEL1OS alignment
│   │   ├── goes_fetcher.py     # GOES XRS + NOAA events
│   │   ├── hel1os_reader.py    # HEL1OS FITS reader
│   │   ├── solexs_reader.py    # SoLEXS FITS reader
│   │   ├── pradhan_download.py # PRADAN downloader
│   │   ├── fits_pure.py        # Pure FITS parser
│   │   └── synth.py            # Synthetic data
│   ├── nowcast/
│   │   ├── hard_detector.py    # HXR CUSUM
│   │   ├── soft_detector.py    # SXR CUSUM
│   │   ├── neupert_engine.py   # Neupert nowcast
│   │   └── primitives.py       # Base classes
│   ├── preprocess/
│   │   ├── fusion.py           # Multi-instrument fusion
│   │   └── merge.py            # Time alignment
│   ├── catalog/
│   │   └── master_catalog.py   # Event catalog
│   ├── api/
│   │   └── main.py             # FastAPI server
│   ├── constants.py
│   └── types.py
├── tests/
│   ├── test_neupert_qc.py      # 20 Neupert QC tests
│   ├── test_phase5_api.py      # API tests
│   └── test_phase4_ml.py       # ML tests
├── data/raw/                   # 10 PRADAN archives
├── paper/                      # Publication package
├── ML_MODEL_DASHBOARD.md       # Full dashboard
├── ML_MODEL_QUICK_REFERENCE.md # Quick reference
├── EXECUTIVE_SUMMARY.md        # Executive summary
├── PRESENTATION_OUTLINE.md     # 20-min presentation
├── TECHNICAL_APPENDIX.md       # Technical details
├── DATA_DICTIONARY.md          # This file
└── MANUAL_DOWNLOAD_GUIDE.md    # PRADAN manual guide
```

---

*Data Dictionary v1.0 | solar-flare-system | Aditya-L1 SoLEXS/HEL1OS*