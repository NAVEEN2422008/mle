# Telemetry Data Dictionary & Ingestion Manual
## Aditya-L1 Solar Flare Early Warning & Nowcasting System

This document consolidates the complete data dictionary, telemetry schemas, and PRADAN download runbooks into a single authoritative reference.

---

# Part 1: Telemetry Data Dictionary & Schema
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

---

# Part 2: Manual PRADAN Portal Download Guide
# Manual Download Guide for Aditya-L1 Data from PRADAN

## Overview
The PRADAN portal (https://pradan.issdc.gov.in/al1/) has session expiration issues that prevent full automation. This guide provides step-by-step instructions for manual download of additional Aditya-L1 SoLEXS/HEL1OS paired events.

## Current Status
**Already Downloaded & Analyzed (5 pairs):**
| Date | Flare | SoLEXS | HEL1OS | Status |
|------|-------|--------|--------|--------|
| 2024-05-10 | X3.9 | ✅ | ⚠️ (starts after peak) | Analyzed |
| 2024-05-11 | X5.8 | ✅ | ✅ | Analyzed |
| 2024-05-14 | X8.7 | ✅ | ✅ | Analyzed |
| 2024-10-01 | X7.1 | ✅ | ✅ | Analyzed |
| 2024-10-03 | X9.0 | ✅ | ✅ | Analyzed |

**Target:** Download 25-50 more paired events for HXR ablation study.

## Manual Download Procedure

### 1. Login to PRADAN
1. Go to: https://pradan.issdc.gov.in/al1/
2. Click "Browse and Download" → Select "HEL1OS" or "SoLEXS"
3. Log in with your ISRO credentials

### 2. Filter for Specific Date Range
For each instrument:

**HEL1OS:**
1. Go to: https://pradan.issdc.gov.in/al1/protected/browse.xhtml?id=hel1os
2. Set filter:
   - ObservationTime → "In"
   - From: `2024-05-01 00:00:00`
   - To: `2024-05-31 23:59:59` (for May 2024)
   - Or: `2024-10-01 00:00:00` to `2024-10-31 23:59:59` (for Oct 2024)
3. Click "Filter"

**SoLEXS:**
1. Go to: https://pradan.issdc.gov.in/al1/protected/browse.xhtml?id=solexs
2. Set same filter as above
3. Click "Filter"

### 3. Bulk Download (Recommended)
**For each instrument after filtering:**
1. Click **"Select, Zip and DOWNLOAD (max 1024.0MB data)"** button
2. Wait for zip file to generate
3. Save as: `hel1os_may2024.zip` or `solexs_may2024.zip`
2. Extract to `data/raw/`

### 4. Alternative: Select and Download in Bulk with Script
1. Click **"Select and Download in Bulk with Script"**
2. This generates a shell script with wget/curl commands
3. Run the script to download all files

## Target Dates for Additional Downloads

### Priority 1: May 2024 (X-class flares)
| Date | Flare Class | Notes |
|------|-------------|-------|
| 2024-05-01 to 2024-05-31 | Multiple | Already have 5/10, need 5 more |

### Priority 2: October 2024 (X-class flares)
| Date | Flare Class | Notes |
|------|-------------|-------|
| 2024-10-01 to 2024-10-31 | X7.1, X9.0 | Already have 2/2 |

### Priority 3: Other months with X/M-class flares
Check NOAA flare catalog for:
- 2024-01 to 2024-12: All X-class and M-class flares
- Focus on dates where both SoLEXS and HEL1OS have data

## Expected File Counts (Estimated)
| Instrument | May 2024 | Oct 2024 | Other months |
|------------|----------|----------|--------------|
| SoLEXS | ~31 files | ~31 files | ~31/month |
| HEL1OS | ~30+ files | ~30+ files | ~30/month |

## File Naming Patterns
**SoLEXS:** `AL1_SLX_L1_YYYYMMDD_v1.0.zip`
**HEL1OS:** `HLS_YYYYMMDD_HHMMSS_XXXXsec_lev1_V111.zip`

## Post-Download Processing
After downloading and extracting to `data/raw/`:
```bash
# Run Neupert analysis on new data
python scripts/neupert_analysis.py --raw data/raw --band CZT2 --sweep-bands

# Run ML evaluation
python scripts/evaluate_aditya_real.py
```

## Troubleshooting
- **Session expires:** Re-login and re-apply filters
- **Filter not working:** Clear filter and re-apply
- **Download fails:** Try "Select, Zip and DOWNLOAD" instead of individual downloads
- **Missing HEL1OS for a date:** Check if HEL1OS segment covers the flare time (some segments start after flare peak)

## Data Already Available
The following 5 pairs are already downloaded and analyzed in `data/raw/`:
- 2024-05-10 (X3.9) - HEL1OS starts after peak
- 2024-05-11 (X5.8) - Complete pair
- 2024-05-14 (X8.7) - Complete pair
- 2024-10-01 (X7.1) - Complete pair
- 2024-10-03 (X9.0) - Complete pair

## Next Steps for HXR Ablation Study
1. Download ~25-50 more paired events
2. Run band sensitivity sweep on new data
3. Retrain ML models with expanded dataset
4. Update paper with new results

## Contact
For issues with PRADAN portal: Check FAQ at https://pradan.issdc.gov.in/al1/faq.xhtml

---

# Part 3: PRADAN CLI Automation Runbook
# PRADAN DAY RUNBOOK — Aditya-L1 Real-Data Ingest

Goal: go from "I have a PRADAN account" to flare catalogue + forecast numbers
on genuine SoLEXS/HEL1OS Level-1 telemetry in under an hour.

---

## 0. One-time setup (~5 min)

```powershell
cd "C:\Users\Naveen S\OneDrive\Documents\mle\solar-flare-system"
python -m pip install -r requirements.txt        # astropy pyarrow lightgbm fastapi uvicorn ...
```

Register (free): https://pradan1.issdc.gov.in/al1/  → "Register" → email OTP.
Login once in the browser to confirm access to the AL1 section.

## 1. Download the data

**Route A - interactive downloader (primary, verified against live portal):**
Open your OWN PowerShell (not this chat) and run:
```powershell
cd "C:\Users\Naveen S\OneDrive\Documents\mle\solar-flare-system"
python scripts\download_pradan.py
```
- Prompts: username/email, then password (hidden input - never stored or displayed)
- Range prompt: press Enter for last ~14 days, or type `20240515:20240615`
- Instruments: Enter = both SoLEXS + HEL1OS
- Zips land directly in `data\raw\`

Auth flow used (verified 2026-08): PRADAN -> Keycloak (idp.issdc.gov.in,
realm issdc) -> session cookies; script parses the dynamic form action.

**Route B - browser fallback:** pradan1.issdc.gov.in/al1 -> Browse Data ->
SLX/HLD sections -> **Bulk Download** -> drop `AL1_*_L1_*.zip` into `data\raw\`.

> ⚠️ Remove mock files first if present:
> `Remove-Item data\raw\AL1_*_L1_*.zip, data\raw\truth_mock.json`

## 2. Run the stack (one command)

```powershell
python scripts\run_pradan.py --raw data/raw
```

What you'll see: scan counts → rows read after SDD arbitration & band collapse →
fused stream size → **flare catalogue CSV** at `data\processed\flare_catalogue.csv`
→ forecast CV vs climatology/persistence → truth validation (mock mode only).

Cadence note: SoLEXS native = 1 s; HEL1OS L1 LC = 1 s. If you also grabbed GOES
for cross-checks, the real-data suite (`tests/test_realdata_goes.py`) handles its
1-min cadence separately — no mixing required.

## 3. Data-volume guidance (from dress rehearsal)

| Days of data | Detection catalogue | Forecast CV |
|---|---|---|
| 1-3 | works immediately | SKIPPED (<10 independent episodes) |
| ~7 | better sensitivity tuning possible | borderline |
| ≥14 (≈30+ flares) | solid | full TSS/HSS/BSS + lead-time report |

The runner prints this guidance automatically when it skips training.

## 4. Sanity checklist on first REAL run

- [ ] `[read]` row counts ≈ 86,400 × days (SoLEXS) — large drops ⇒ gaps/GTIs (fine)
- [ ] No `date-src=FALLBACK(unknown)` in provenance (means header+filename lacked date)
- [ ] Catalogue peaks visually match obvious bumps: open
      `data/processed/fused.parquet` in a quick matplotlib plot vs `flare_catalogue.csv`
- [ ] Cross-check a few catalogue peaks against the official GOES/SWPC event list
      (same timestamps ±1 min expected — Sun-as-a-star instruments agree well)

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `No usable TIME+counts table` | unusual FITS layout | send me the member listing: `python -c "from astropy.io import fits; print(fits.info('FILE'))"` |
| All events on one date | missing DATE-OBS & nonstandard name | keep original PRADAN filenames |
| Detector deaf / too many events | threshold mismatch to real background | tune `--` (edit `det_h_c_sigma` in scripts/run_pradan.py; start 8-15) |
| Forecast skipped | not enough episodes yet | download more days |

---
*Mock rehearsal evidence: see research_report.md Appendix 5.*

