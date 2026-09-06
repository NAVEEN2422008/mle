# Aditya FlareCast — Research Gap Analysis
## Comprehensive Audit: Literature, Implementation, Evaluation, and Deployment

**Generated:** September 2026  
**Status:** Pre-deployment gap analysis  

---

## 1. LITERATURE GAPS (Papers We Cite But Haven't Fully Exploited)

### 1.1 HOPE Technique (arXiv:2509.05234)
| Aspect | HOPE State-of-the-Art | Our Implementation | Gap |
|--------|----------------------|-------------------|-----|
| Running-difference T/EM | Full temperature/emission-measure decomposition from spectral fits | Simplified HXR/SXR ratio proxy | **HIGH** — We don't do spectral fitting; our proxy is order-of-magnitude less discriminating |
| MLP for magnitude+time | Trained MLP predicts peak magnitude + time-to-peak | Logistic regression (LightGBM sigmoid head) | **MEDIUM** — We predict probability, not magnitude/time jointly |
| 5-15 min pre-peak alerts | Validated on 2014-2024 GOES data | Only synthetic + limited real SoLEXS | **HIGH** — No statistical validation on real flare population |
| Sub-GOES sensitivity classes | Detects A/B-class microflares | Only ≥C class flares | **MEDIUM** — Misses microflare precursors |

### 1.2 Onboard Detection (DOI 10.1007/s11207-026-02645-x)
| Aspect | Paper State-of-the-Art | Our Implementation | Gap |
|--------|----------------------|-------------------|-----|
| 69.5% detection @35% FP | Validated on 2587 ≥C1.0 GOES flares | No formal FP analysis on real population | **HIGH** — Missing false-positive characterization |
| Onboard-computable trigger | Explicitly designed for microcontroller | O(1) primitives exist but no onboard deployment | **MEDIUM** — Hardware validation missing |
| Event characterization | Duration, peak time, rise/decay rates | Only start/peak/end | **LOW** — We have the metadata |

### 1.3 Neupert Effect Statistics (C3, C4, C5)
| Aspect | Literature State | Our Implementation | Gap |
|--------|-----------------|-------------------|-----|
| 149-event cross-correlation (C4) | Statistical sample of Neupert correlations | Rolling correlation on single event | **HIGH** — No population statistics |
| Deviations catalog (C5) | Catalogues when Neupert breaks (non-thermal dominated) | Binary hxr_leads_flag only | **MEDIUM** — No deviation classification |
| Microwave correlation (C5) | Multi-wavelength Neupert validation | Only SXR+HXR | **LOW** — Microwave not in Aditya-L1 |

### 1.4 Survey Paper (arXiv:2511.20465)
| Aspect | Survey Recommendations | Our Implementation | Gap |
|--------|----------------------|-------------------|-----|
| Multi-instrument fusion | Magnetogram + EUV + X-ray | Only SXR + HXR | **HIGH** — No magnetic field features |
| SHARP parameters | 25 magnetic field parameters | Not implemented (Aditya-L1 has no magnetogram) | **N/A** — Instrument limitation |
| DeepSun/DeepFlareNet | CNN on full-disk images | Tabular features only | **MEDIUM** — No image-based approach |
| MViT (Vision Transformer) | Multi-scale attention on solar images | Not applicable to point-source data | **N/A** — Different data modality |
| Ensemble methods | Stack/blend multiple models | Single LightGBM | **MEDIUM** — No ensemble |

### 1.5 Comparative ML (D5)
| Aspect | Literature Finding | Our Implementation | Gap |
|--------|-------------------|-------------------|-----|
| GBT-family wins on tabular | XGBoost/LightGBM best for tabular data | LightGBM only | **LOW** — We chose the winner |
| RF/KNN baselines | Random Forest competitive at small data | Not compared | **MEDIUM** — Missing ablation |
| Feature importance analysis | SHAP values for interpretability | No interpretability layer | **HIGH** — Black-box model |

---

## 2. IMPLEMENTATION GAPS (Planned But Not Done)

### 2.1 From PLAN.md v2
| Plan Item | Status | Gap Description |
|-----------|--------|-----------------|
| HOPE-inspired features | ✅ Added (running diff, temp/em proxy) | Simplified — no spectral decomposition |
| Metrics-first evaluation | ✅ TSS is primary | Missing: calibration curves, reliability diagrams |
| Mandatory baselines | ✅ Climatology + Persistence | Missing: persistence with class-dependent decay |
| SDD arbitration | ✅ Implemented | Not validated on saturation events (no M/X data) |
| GOES end-rule | ✅ Implemented | Missing: complex event sub-peak merging validation |
| Benchmark to beat | ⚠️ TSS=0.282 vs target 0.74 | **HIGH** — 63% gap to target |

### 2.2 From ARCHITECTURE.md (Referenced in Bibliography)
| Architecture Item | Status | Gap Description |
|-------------------|--------|-----------------|
| TCN multi-horizon | ✅ `deep_forecaster.py` exists | Not trained on real data (random weights) |
| LightGBM production | ✅ Trained | Poor TSS on real data |
| Wavelet features | ❌ Not implemented | **HIGH** — Wavelet decompositions capture QPPs (Quasi-Periodic Pulsations) |
| Spectral index evolution | ❌ Not implemented | **HIGH** — Thermal/non-thermal decomposition |
| GOES cross-calibration | ⚠️ Linear model only | **MEDIUM** — Need instrumental response functions |
| ONNX export | ❌ Not implemented | **MEDIUM** — No edge deployment format |

---

## 3. EVALUATION GAPS (What We Don't Measure)

### 3.1 Missing Metrics
| Metric | Why Needed | Status |
|--------|-----------|--------|
| **Calibration curve** | Is P(flare=0.7) actually 70% accurate? | ❌ Not implemented |
| **Reliability diagram** | Probability calibration quality | ❌ Not implemented |
| **Sharpness** | How concentrated are predictions? | ❌ Not implemented |
| **ROC-AUC** (per-class) | Per-class discrimination (despite survey ban) | ❌ Deliberately excluded |
| **Brier decomposition** | Reliability + resolution + uncertainty | ⚠️ BSS computed but not decomposed |
| **ROC curve** | Visual discrimination at all thresholds | ❌ Not plotted |
| **PR curve** | Precision-recall tradeoff visualization | ❌ Not plotted |
| **Bootstrap CIs** | Confidence intervals on all metrics | ❌ Point estimates only |
| **Per-class TSS** | TSS for ≥B, ≥C, ≥M, ≥X separately | ❌ Only aggregate TSS |
| **Seasonal variation** | Performance vs solar cycle phase | ❌ Single validation period |

### 3.2 Missing Validation
| Validation | Why Needed | Status |
|-----------|-----------|--------|
| **Cross-instrument** | Train on GOES, test on Aditya-L1 | ❌ Not done |
| **Cross-era** | Train on Solar Cycle 24, test on 25 | ❌ Not done |
| **Cross-flare-type** | Performance on impulsive vs gradual flares | ❌ Not done |
| **Temporal stability** | Does model degrade over time? | ❌ No drift detection |
| **Adversarial testing** | Performance on worst-case inputs | ❌ Not tested |
| **Missing data robustness** | Performance with 10%, 30%, 50% missing | ❌ Not tested |
| **Noise sensitivity** | Performance at SNR=5, 10, 20 | ❌ Not tested |
| **Latency profiling** | P50/P95/P99 inference time | ❌ Not measured |

### 3.3 Missing Comparisons
| Comparison | Why Needed | Status |
|-----------|-----------|--------|
| **Random Forest** | Baseline tree model | ❌ Not compared |
| **XGBoost** | Alternative GBDT | ❌ Not compared |
| **Logistic Regression** | Linear baseline | ❌ Not compared |
| **SVM** | Kernel method baseline | ❌ Not compared |
| **Neural network (MLP)** | Deep learning baseline | ❌ Not compared |
| **Rule-based** | GOES FSM operational rule | ⚠️ Compared via baselines.py |
| **Persistence (class-dependent)** | Different decay for M vs C vs B | ❌ Not implemented |
| **HOPE method** | Direct competitor | ❌ Not implemented |

---

## 4. FEATURE ENGINEERING GAPS

### 4.1 Missing Physics Features
| Feature | Physics | Why Important | Priority |
|---------|---------|--------------|----------|
| **Wavelet coefficients** | Time-frequency decomposition | Captures QPPs (Quasi-Periodic Pulsations) that precede flares | HIGH |
| **Spectral index (γ)** | Power-law fit to HXR spectrum | Thermal/non-thermal decomposition; γ < 4 indicates impulsive phase | HIGH |
| **Emission measure (EM)** | From thermal continuum fit | EM rise precedes temperature rise (Neupert signature) | HIGH |
| **Temperature (T_max)** | From multi-band ratio | T_max peaks before EM peak (evaporation dynamics) | HIGH |
| **HXR pulse count** | Number of HXR spikes per minute | Multiple pulses indicate complex event | MEDIUM |
| **SXR decay time** | τ_decay from exponential fit | Long decay → gradual event; short → impulsive | MEDIUM |
| **Rise-to-decay ratio** | Rise time / Decay time | Classifies impulsive vs gradual | MEDIUM |
| **Harmonic content** | FFT fundamental + harmonics | Detects oscillatory precursor signals | MEDIUM |
| **Cross-correlation lag** | Time lag of max corr(HXR, dSXR/dt) | Physical loop length indicator | LOW |
| **Magnetic connectivity** | Active region distance | Far-side flares have different characteristics | N/A (no mag data) |

### 4.2 Missing Statistical Features
| Feature | Formula | Why Important | Priority |
|---------|---------|--------------|----------|
| **Hurst exponent** | Rescaled range analysis | Long-memory processes indicate persistence | MEDIUM |
| **Fractal dimension** | Higuchi method | Complexity of light curve | LOW |
| **Entropy** | Sample entropy | Regularity/predictability | LOW |
| **Autocorrelation** | ACF at lags 1,5,10,30,60 | Temporal structure | MEDIUM |
| **Partial autocorrelation** | PACF at lags | Direct temporal dependencies | MEDIUM |
| **Skewness/Kurtosis** | Rolling window | Distribution shape changes | LOW |
| **Change-point count** | Number of regime changes | Multi-stage eruption indicator | MEDIUM |

### 4.3 Missing Operational Features
| Feature | Source | Why Important | Priority |
|---------|--------|--------------|----------|
| **Solar cycle phase** | F10.7 radio flux | Flare probability varies with cycle | HIGH |
| **Active region number** | NOAA AR catalogue | Some ARs are flare-productive | HIGH (if available) |
| **Helographic position** | AR coordinates | Limb darkening affects detection | MEDIUM |
| **Previous 24h flare count** | Catalogue | Active regions produce clusters | MEDIUM |
| **Time since last M/X flare** | Catalogue | Large flares suppress further activity | MEDIUM |
| **GOES proton flux** | NOAA | SEP events correlate with large flares | LOW |

---

## 5. MODEL ARCHITECTURE GAPS

### 5.1 Missing Architectures
| Architecture | Paper Reference | Why Important | Priority |
|-------------|----------------|--------------|----------|
| **TCN (Temporal ConvNet)** | Our `deep_forecaster.py` | Multi-scale temporal patterns | HIGH — exists but untrained |
| **LSTM/GRU** | D3, D4 | Sequential dependencies | HIGH |
| **Transformer** | D1 survey | Self-attention over time series | MEDIUM |
| **CNN-1D** | DeepSun | Local pattern detection | MEDIUM |
| **Graph Neural Network** | Emerging in solar physics | Multi-instrument relationships | LOW |
| **Variational Autoencoder** | Anomaly detection literature | Unsupervised precursor detection | MEDIUM |
| **Gaussian Process** | Probabilistic forecasting | Uncertainty quantification | HIGH |

### 5.2 Missing Training Techniques
| Technique | Why Important | Status |
|-----------|--------------|--------|
| **Hyperparameter search** | Bayesian optimization | ❌ Manual grid only |
| **Learning rate scheduling** | Better convergence | ❌ Fixed lr=0.05 |
| **Early stopping** | Prevent overfitting | ❌ Not implemented |
| **Cross-validation ensembling** | Fold averaging | ❌ Single fold |
| **Feature selection** | Remove irrelevant features | ❌ All 23 features used |
| **Class-weighted loss** | Better imbalance handling | ⚠️ scale_pos_weight only |
| **Focal loss** | Focus on hard examples | ❌ Not implemented |
| **Label smoothing** | Prevent overconfident predictions | ❌ Not implemented |
| **Mixup augmentation** | Regularization | ❌ Not implemented |
| **Temporal ensembling** | Smooth predictions | ❌ Not implemented |

### 5.3 Missing Inference Techniques
| Technique | Why Important | Status |
|-----------|--------------|--------|
| **Monte Carlo dropout** | Uncertainty estimation | ❌ Not implemented |
| **Ensemble variance** | Model disagreement uncertainty | ❌ Not implemented |
| **Conformal prediction** | Distribution-free confidence intervals | ❌ Not implemented |
| **Calibrated probabilities** | Isotonic/Platt scaling | ❌ Not implemented |
| **Temporal smoothing** | Reduce alert flickering | ⚠️ Hysteresis gate only |
| **Adaptive thresholding** | Threshold adapts to base rate | ❌ Fixed threshold |

---

## 6. DATA GAPS

### 6.1 Missing Data Sources
| Data Source | URL/Source | Why Important | Priority |
|------------|-----------|--------------|----------|
| **HEL1OS historical** | PRADAN portal (only last 2 days available) | Core instrument for Neupert features | **CRITICAL** |
| **GOES XRS L2 (1s)** | data.ngdc.noaa.gov | High-cadence training surrogate | HIGH |
| **HEK flare catalogue** | SunPy Fido | Independent label validation | HIGH |
| **SHARP parameters** | HMI/SDO | Magnetic field features (if co-observing) | MEDIUM |
| **EUV images** | AIA/SDO | Spatial context | LOW |
| **Kaggle SoLEXS parquet** | kaggle datasets | Quick-start soft-band data | LOW (we have real data) |
| **Microwave data** | Various radio telescopes | Multi-wavelength Neupert validation | LOW |

### 6.2 Data Quality Issues
| Issue | Impact | Status |
|-------|--------|--------|
| **HEL1OS mock data date range** | 2024-05-15 to 2083-04-10 (spurious future dates) | ⚠️ Known, affects statistics |
| **SoLEXS gaps** | Aug 10, 11, 12, 16 missing | ⚠️ Portal limitation |
| **No M/X class flares in data** | Only 1 M-class, 2 C-class detected | ⚠️ Insufficient for rare-event evaluation |
| **Single-instrument validation** | No HEL1OS hard X-ray for Aug 10-21 | ⚠️ Core limitation |
| **No spectral data** | Only broadband counts | ⚠️ Instrument limitation |

---

## 7. PHYSICS GAPS

### 7.1 Unmodeled Physical Phenomena
| Phenomenon | Physics | Impact on Forecasting | Priority |
|-----------|---------|----------------------|----------|
| **Non-thermal electron acceleration** | HXR bremsstrahlung from accelerated electrons | Direct precursor to flare peak | HIGH |
| **Chromospheric evaporation** | Plasma heated → rises into corona | EM rise precedes SXR peak | HIGH |
| **Magnetic reconnection rate** | dΦ/dt from electric field | Fundamental driver (no mag data) | N/A |
| **Current helicity injection** | Twist accumulation | Proxy for free energy | N/A |
| **Coronal dimming** | Mass ejection signatures | CME-associated flares | LOW |
| **Type II/III radio bursts** | Shock/accelerated electrons | Multi-wavelength precursor | LOW |

### 7.2 Simplified Physics in Our Model
| Simplification | Reality | Impact | Fix |
|---------------|---------|--------|-----|
| **Neupert scaling α=0.19** | α varies by event (0.05-0.5) | Feature may be noisy | Event-adaptive α |
| **EM_proxy = SXR × HXR** | EM from thermal continuum fit | Order-of-magnitude error | Proper EM estimation |
| **Temp_proxy = HXR/SXR** | T from multi-band ratio | Non-thermal contamination | Spectral decomposition |
| **No loop geometry** | Loops have length, density, field | Missing physics | Not available from L1 |
| **No photospheric input** | Magnetic field drives reconnection | Missing root cause | Need SDO/HMI data |

---

## 8. OPERATIONAL/DEPLOYMENT GAPS

### 8.1 Missing for Operational Use
| Requirement | Why Needed | Status |
|------------|-----------|--------|
| **Real-time data pipeline** | Continuous ingestion from PRADAN | ⚠️ Manual download only |
| **Automated model retraining** | Adapt to solar cycle changes | ❌ Not implemented |
| **Alert escalation** | Different actions for B vs C vs M vs X | ❌ Single threshold |
| **Notification system** | Email/SMS/pager alerts | ❌ Dashboard only |
| **Data archival** | Long-term storage of predictions | ❌ In-memory only |
| **Audit trail** | Track all predictions for post-analysis | ❌ Not implemented |
| **SLA monitoring** | Uptime, latency, throughput | ❌ Not implemented |
| **Disaster recovery** | Backup/restore procedures | ❌ Not implemented |
| **Security** | Authentication, rate limiting | ❌ Open API |
| **Multi-tenancy** | Multiple users/agencies | ❌ Single user |

### 8.2 Missing for ISRO BAH 2026 Submission
| Requirement | Why Needed | Status |
|------------|-----------|--------|
| **Docker deployment** | Reproducible environment | ✅ Dockerfile exists |
| **Dashboard** | Visual interface | ✅ Zero-dep dashboard |
| **Offline mode** | Zero-credentials operation | ✅ Synthetic fallback |
| **Test suite** | Verification | ✅ 4 test suites pass |
| **Documentation** | Explain the system | ✅ Research paper + PLAN |
| **Benchmark comparison** | Show improvement over baselines | ⚠️ Beats baselines but not SOTA |
| **Edge deployment** | ONNX/TFLite export | ❌ Not implemented |

---

## 9. CRITICAL GAPS (Top 10 to Fix First)

| # | Gap | Category | Impact | Effort |
|---|-----|----------|--------|--------|
| 1 | **HEL1OS data unavailability** | Data | Cannot validate Neupert features | External (ISRO) |
| 2 | **TSS=0.282 vs target 0.74** | Evaluation | 63% performance gap | Medium |
| 3 | **No spectral decomposition** | Physics | Missing thermal/non-thermal | High |
| 4 | **No calibration curves** | Evaluation | Unknown probability quality | Low |
| 5 | **No feature importance** | Interpretability | Black-box model | Low |
| 6 | **No uncertainty quantification** | Deployment | No confidence intervals | Medium |
| 7 | **No wavelet features** | Features | Missing QPP signals | Medium |
| 8 | **No ensemble methods** | Model | Single model limitation | Medium |
| 9 | **No temporal stability check** | Evaluation | Unknown drift behavior | Low |
| 10 | **No cross-instrument validation** | Evaluation | Unknown generalization | Medium |

---

## 10. GAPS BY PRIORITY MATRIX

### HIGH Priority (Fix for BAH 2026 submission)
1. Get HEL1OS data for Aug 10-21 (external dependency)
2. Add calibration curves and reliability diagrams
3. Add feature importance (SHAP values)
4. Add per-class TSS (≥B, ≥C, ≥M, ≥X)
5. Add bootstrap confidence intervals
6. Add wavelet features (QPP detection)
7. Add proper EM/T_max estimation from broadband data
8. Add Gaussian Process for uncertainty quantification
9. Train TCN/LSTM on real data
10. Add Random Forest and XGBoost baselines

### MEDIUM Priority (Post-submission)
11. Add spectral index (γ) estimation
12. Add ensemble methods (stacking)
13. Add conformal prediction
14. Add temporal stability monitoring
15. Add cross-instrument validation
16. Add missing data robustness testing
17. Add noise sensitivity testing
18. Add latency profiling
19. Add ONNX export
20. Add automated retraining pipeline

### LOW Priority (Future work)
21. Add Hurst exponent features
22. Add fractal dimension features
23. Add entropy features
24. Add GNN for multi-instrument
25. Add VAE for anomaly detection
26. Add CNN-1D for pattern detection
27. Add adversarial testing
28. Add multi-wavelength validation
29. Add operational alert escalation
30. Add security/authentication

---

## 11. GAP RESOLUTION ROADMAP

### Phase 1: BAH 2026 Submission (Current)
- [x] Fix all bugs (5 found, 5 fixed)
- [x] Write research paper
- [x] Add HOPE-inspired features
- [x] Tune LightGBM hyperparameters
- [ ] Add calibration curves
- [ ] Add feature importance (SHAP)
- [ ] Add per-class TSS
- [ ] Add bootstrap CIs
- [ ] Add wavelet features
- [ ] Add RF/XGBoost baselines

### Phase 2: Performance Improvement
- [ ] Get HEL1OS data
- [ ] Train TCN/LSTM on real data
- [ ] Add spectral decomposition
- [ ] Add ensemble methods
- [ ] Add uncertainty quantification
- [ ] Target: TSS > 0.50

### Phase 3: Operational Deployment
- [ ] ONNX export
- [ ] Automated retraining
- [ ] Alert escalation
- [ ] Real-time pipeline
- [ ] Security/auth
- [ ] Target: TSS > 0.74

---

*This gap analysis was generated by systematic cross-referencing of the research bibliography, PLAN.md, ARCHITECTURE.md, and full codebase audit.*
