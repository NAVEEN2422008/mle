# 🌞 Executive Summary: Solar Flare Nowcasting with Aditya-L1

## 🎯 One-Sentence Summary
**First verifiable solar flare nowcasting benchmark using real Aditya-L1 data: Neupert physics validated (4/4 events, r=0.82), causal ML features add +0.04 TSS, honest benchmark at TSS=0.28.**

---

## 🎯 The Problem
Solar flares disrupt satellites, power grids, GPS, and aviation. Current forecasting relies on GOES soft X-ray proxies with no genuine hard X-ray data. Aditya-L1 (ISRO) provides the first Indian simultaneous soft + hard X-ray observations.

## 🔬 What We Did
1. **Downloaded & aligned** 5 genuine Aditya-L1 SoLEXS (SXR) + HEL1OS (HXR) Level-1 archives from PRADAN
2. **Tested Neupert effect** on real data: SXR ~ ∫HXR (standard model) vs SXR ~ HXR (direct)
3. **Built ML nowcaster** with Neupert causal features (α, residual, HXR-leads flag)
4. **Validated** with walk-forward CV on NOAA ground truth (strictly pre-peak labels)

## 🔬 Key Findings

### Physics: Neupert Effect Validated ✅
| Result | Value | Significance |
|--------|-------|--------------|
| Events supporting Neupert | 4/4 | 100% of usable events |
| Median r (integral) | 0.82 | Strong correlation |
| Median r (direct) | 0.22 | Weak direct correlation |
| Median lead time | 3.5 min | HXR leads SXR |
| Band robustness | 19/20 | Band-independent |

**Correction**: Earlier draft claimed "5/5 flares deviate from Neupert" — **RETRACTED**. Was measurement artifact (5 bugs fixed).

### ML Nowcasting: First Honest Benchmark
| Metric | Value | Status |
|--------|-------|--------|
| TSS (θ=0.5) | 0.28 | First verifiable benchmark |
| TSS (tuned) | 0.32 | Optimized threshold |
| POD | 0.34 | Low (only 4 X-class events) |
| FAR | 0.90 | High (quiet Sun week) |
| BSS | -2.17 | Needs calibration |

### Ablation: Neupert Features Add Value
| Model | Features | TSS (fixed) | ΔTSS |
|-------|----------|-------------|------|
| A | Soft X-ray only | 0.18 | — |
| B | + Soft proxy | 0.16 | -0.02 ❌ |
| C | + Real HXR | 0.22 | +0.04 ✅ |
| D | + Neupert features | **0.28** | **+0.04** ✅ |

**Top feature**: `neupert_alpha` (trailing OLS α in dSXR/dt = α·HXR)

---

## 🚨 Critical Corrections Made

| Bug | Original Error | Fix |
|-----|----------------|-----|
| Band selection | "CDT" matched all CDTE → 1.8-90 keV | Parse EXTNAME, require >22 keV |
| Baseline | np.median=0 under zero-inflation | Median of nonzero GTI samples |
| Sentinel -1.0 | Failed fit won tie-break | Sentinel=-9.0, require r≥0.3 |
| Zero-inflation | Shared zeros faked correlation | Reject >90% zero windows |
| NaN propagation | X9.0 silently dropped | Interpolate finite, mask NaN |

---

## 🚀 Operational Readiness: Not Ready Yet

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

## 📁 Deliverables Ready

| Asset | Status | Location |
|--------|--------|----------|
| **Paper (LaTeX)** | ✅ Ready | `paper/paper.tex` |
| **Paper (Markdown)** | ✅ Ready | `paper/PAPER_DRAFT.md` |
| **Paper (Word)** | ✅ Ready | `paper/PAPER_DRAFT.docx` |
| **Figures (10)** | ✅ Generated | `paper/figures/` |
| **ML Pipeline** | ✅ Tested | `src/forecast/pipeline.py` |
| **Neupert Analysis** | ✅ Verified | `scripts/neupert_analysis.py` |
| **ML Evaluation** | ✅ Verified | `scripts/evaluate_aditya_real.py` |
| **Tests** | 50 passed | `tests/` (20 Neupert QC) |

---

## 🚀 Next Steps (Priority Order)

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| 1 | Download 25-50 more Aditya paired events | Medium | High |
| 2 | Build 6-12 month GOES+NOAA dataset | High | High |
| 3 | Calibration (Platt/Isotonic) | Medium | High |
| 4 | M/C-class generalization | High | High |
| 5 | Operational calibration | High | High |

---

## 📞 Contact & Reproducibility

```bash
# Reproduce everything
python scripts/neupert_analysis.py --raw data/raw --band CZT2 --sweep-bands
python scripts/evaluate_aditya_real.py
python -m pytest tests/ -q  # 50 passed
```

**Data**: `data/raw/` (5 SoLEXS + 5 HEL1OS genuine PRADAN archives)  
**Code**: `src/forecast/pipeline.py`, `scripts/neupert_analysis.py`  
**Tests**: `python -m pytest tests/ -q` (50 passed, 20 Neupert QC)

---

*Prepared for: [Stakeholder/Review Committee]*  
*Date: September 2026*  
*Project: Solar Flare Nowcasting with Aditya-L1 SoLEXS/HEL1OS*