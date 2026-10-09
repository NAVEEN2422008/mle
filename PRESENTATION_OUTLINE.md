# 🌞 Presentation Outline: Solar Flare Nowcasting with Aditya-L1
## 20-Minute Technical Presentation + 10-Minute Q&A

---

## Slide 1: Title Slide (30 sec)
**Title**: Solar Flare Nowcasting with Aditya-L1: Neupert Physics Meets ML
**Subtitle**: First Verifiable Benchmark on Real Aditya-L1 SoLEXS/HEL1OS Data
**Presenter**: [Name], [Affiliation]
**Date**: [Date]

---

## Slide 2: The Problem (2 min)
**Solar Flares Disrupt Critical Infrastructure**
- Satellites (GPS, comms), Power grids, Aviation, Astronaut safety
- Current forecasting: GOES soft X-ray only, no genuine hard X-ray
- **Gap**: No causal physical features in operational ML models

**Aditya-L1 Opportunity**: First Indian mission with simultaneous SXR (SoLEXS) + HXR (HEL1OS)

---

## Slide 3: The Physics - Neupert Effect (3 min)
**Neupert Effect (1968)**: SXR flux ∝ ∫HXR dt
- Non-thermal electrons (HXR) heat chromosphere → thermal plasma emits SXR
- **Prediction**: SXR should track ∫HXR, not HXR directly

**Our Test**: First simultaneous SXR+HXR Neupert test on Aditya-L1
- SoLEXS: 2-22 keV (SXR, thermal)
- HEL1OS CZT: 40-60 keV (genuine HXR, above SoLEXS ceiling)

---

## Slide 4: The Critical Correction (3 min)
**Earlier Claim**: "5/5 X-class flares deviate from Neupert effect"
**Reality**: Measurement artifacts (5 bugs) → **Corrected: 4/4 support standard Neupert**

| Bug | Original Error | Fix |
|-----|----------------|-----|
| Band selection | "CDT" matched all CDTE → 1.8-90 keV | Parse EXTNAME, require >22 keV |
| Baseline | np.median=0 under zero-inflation | Median of nonzero GTI samples |
| Sentinel -1.0 | Failed fit won tie-break | Sentinel=-9.0, require r≥0.3 |
| Zero-inflation | Shared zeros faked correlation | Reject >90% zero windows |
| NaN propagation | X9.0 silently dropped | Interpolate finite, mask NaN |

**Result**: 4/4 usable events support standard Neupert (r=0.82, lead 3.5 min)

---

## Slide 5: ML Nowcasting Pipeline (3 min)
```
Aditya-L1 Data → Causal Features → Walk-Forward CV → LightGBM → TSS/BSS/LT-vs-FAR
     │              │                    │              │
     ▼              ▼                    ▼              ▼
  SoLEXS+HEL1OS  22 Causal Features   NOAA Ground Truth  LightGBM
  (SXR + HXR)    (Neupert + History)  (Pre-peak only)   Walk-Forward CV
```

**Key Innovation**: Neupert causal features as ML inputs
- `neupert_alpha`: trailing OLS α in dSXR/dt = α·HXR
- `neupert_resid`: residual after Neupert prediction
- `hxr_leads_flag`: HXR onset precedes SXR

---

## Slide 6: Ablation Study - Neupert Features Work (2 min)

| Model | Features | TSS (fixed) | TSS (tuned) | ΔTSS |
|-------|----------|-------------|-------------|------|
| A | Soft X-ray only | 0.18 | 0.24 | — |
| B | + Soft proxy | 0.16 | 0.22 | -0.02 ❌ |
| C | + Real HXR | 0.22 | 0.28 | **+0.04** ✅ |
| D | + Neupert features | **0.28** | **0.32** | **+0.04** ✅ |

**Top Feature**: `neupert_alpha` (trailing OLS α in dSXR/dt = α·HXR)

---

## Slide 7: Results Summary (2 min)

| Metric | Value | Benchmark |
|--------|-------|-----------|
| **TSS (θ=0.5)** | **0.28** | First verifiable benchmark |
| **TSS (tuned)** | **0.32** | Optimized threshold |
| **POD** | 0.34 | Low (only 4 X-class events) |
| **FAR** | 0.90 | High (quiet Sun week) |
| **PR-AUC** | 0.35 | Precision-Recall |
| **Brier** | 0.064 | Calibration |
| **BSS** | -2.17 | Needs calibration |

**Key**: First verifiable Aditya-L1 nowcasting benchmark

---

## Slide 8: Band Sensitivity Sweep (1 min)
**19/20 event-band combinations favor INTEGRAL**

| Date | CDTE 30-40 | CDTE 40-60 | CZT 40-60 | CZT 60-80 | CZT 80-150 |
|------|------------|------------|-----------|-----------|------------|
| 2024-05-11 | INTEGRAL | INTEGRAL | INTEGRAL | INTEGRAL | INTEGRAL |
| 2024-05-14 | INTEGRAL | INTEGRAL | INTEGRAL | INTEGRAL | INTEGRAL |
| 2024-10-01 | INTEGRAL | INTEGRAL | INTEGRAL | INTEGRAL | INTEGRAL |
| 2024-10-03 | INTEGRAL | INTEGRAL | INTEGRAL | INTEGRAL | INTEGRAL |
| 2024-05-10 | NO_COUPLING | NO_COUPLING | NO_COUPLING | NO_COUPLING | NO_COUPLING |

**19/20 event-band combos favor INTEGRAL** — robust across bands

---

## Slide 9: The 2024-05-10 X3.9 Anomaly (1 min)
**Not a physics anomaly — data gap**

- X3.9 peak: **06:54:00 UTC** (NOAA)
- HEL1OS segment starts: **06:54:25 UTC** (25s AFTER peak)
- Impulsive HXR phase completely missed
- SoLEXS shows clear peak at 06:54:00 (19,937 cts/s)
- HEL1OS has NO data before 06:54:25

**Lesson**: HEL1OS segmented data has gaps; must check segment timing

---

## Slide 10: Operational Readiness (2 min)

| Criterion | Status | Gap |
|-----------|--------|-----|
| Physics validity | ✅ | Neupert validated |
| ML skill | ⚠️ | TSS=0.28 (modest) |
| Calibration | ❌ | BSS negative |
| FAR | ❌ | 0.90 too high |
| Lead time | ✅ | 3.5 min median |
| Generalization | ❓ | Only X-class events |

### Path to Operations
1. **Tier-1 Data**: 6-12 months GOES+NOAA (hundreds of events)
2. **More Aditya Events**: Target 25-50 paired events
3. **Calibration**: Platt scaling / Isotonic regression
4. **M/C-class**: Extend beyond X-class only

---

## Slide 11: Reproducibility & Code Quality (1 min)

| Component | Status |
|-----------|--------|
| **Tests** | 50 passed (20 Neupert QC regression tests) |
| **Neupert bugs** | 5 fixed, 20 regression tests |
| **Walk-forward CV** | 4-fold, embargo ≥ horizon+window |
| **Labels** | NOAA ground truth only (strictly pre-peak) |
| **Baselines** | Climatology + Persistence (mandatory) |
| **Primary metric** | TSS (class-ratio insensitive) |

```bash
# Reproduce everything
python scripts/neupert_analysis.py --raw data/raw --band CZT2 --sweep-bands
python scripts/evaluate_aditya_real.py
python -m pytest tests/ -q  # 50 passed
```

---

## Slide 12: Next Steps & Ask (1 min)

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| 1 | Download 25-50 more Aditya paired events | Medium | High |
| 2 | Build 6-12 month GOES+NOAA dataset | High | High |
| 3 | Calibration (Platt/Isotonic) | Medium | High |
| 4 | M/C-class generalization | High | High |
| 5 | Operational calibration | High | High |

**Ask**: Support for PRADAN bulk download access + compute for Tier-1 dataset

---

## Slide 13: Key Takeaways (1 min)

1. **Physics**: Neupert effect validated on Aditya-L1 (4/4 events, r=0.82)
2. **ML**: Neupert causal features add +0.04 TSS (neupert_alpha = top feature)
3. **Honest benchmark**: TSS=0.28 (first verifiable Aditya-L1 result)
4. **Corrected science**: Retracted false "5/5 deviation" claim
5. **Path forward**: More data + calibration → operational readiness

---

## Slide 13: Backup Slides (if needed)

### Appendix A: 5 Bugs Fixed
| Bug | Effect | Fix |
|-----|--------|-----|
| F5.1 Band selection | CDT matched all CDTE | Parse EXTNAME, require >22 keV |
| F5.2 Baseline collapse | median=0 under zero-inflation | Nonzero median |
| F5.3 Sentinel -1.0 | Failed fit won tie-break | Sentinel=-9.0 |
| F5.4 Zero-inflation | Shared zeros faked correlation | Reject >90% zeros |
| F5.5 NaN propagation | X9.0 silently dropped | Interpolate finite |

### Appendix B: 20 Regression Tests
- `tests/test_neupert_qc.py` — 20 tests covering all 5 bugs
- All 50 tests pass: `python -m pytest tests/ -q`

### Appendix C: Data Availability
- 5 genuine PRADAN SoLEXS + 5 HEL1OS archives in `data/raw/`
- 169,505 1-min samples across 5 dates
- 4 X-class events with NOAA ground truth

---

## Speaker Notes (Key Talking Points)

1. **Lead with the correction story** — it builds credibility
2. **Emphasize "first verifiable benchmark"** — differentiates from inflated claims
3. **Show the ablation table** — visual proof Neupert features work
4. **Be honest about limitations** — builds trust for operational path
5. **End with clear ask** — specific, actionable next steps

---

## Timing Checklist (20 min + 10 Q&A)

| Section | Time | Cumulative |
|---------|------|------------|
| Title | 0:30 | 0:30 |
| Problem | 2:00 | 2:30 |
| Neupert Physics | 3:00 | 5:30 |
| Critical Correction | 3:00 | 8:30 |
| ML Pipeline | 3:00 | 11:30 |
| Ablation Study | 2:00 | 13:30 |
| Results Summary | 2:00 | 15:30 |
| Band Sweep | 1:00 | 16:30 |
| Data Gap | 1:00 | 17:30 |
| Operational Readiness | 2:00 | 19:30 |
| Reproducibility | 1:00 | 20:30 |
| Next Steps | 1:00 | 21:30 |
| **Total** | **21:30** | |
| **Q&A** | **10:00** | **31:30** |

---

*Prepared for [Audience] | [Date] | [Presenter]*