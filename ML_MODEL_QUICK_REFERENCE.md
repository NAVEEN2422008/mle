# 🚀 Solar Flare Nowcasting - Quick Reference Card

## 🎯 One-Line Summary
**First verifiable Aditya-L1 flare nowcasting benchmark using genuine HXR (HEL1OS CZT 40-60 keV) + Neupert causal features → TSS=0.28 (fixed) / 0.32 (tuned)**

---

## 🎯 Key Numbers at a Glance

| Metric | Value | Context |
|--------|-------|---------|
| **TSS (θ=0.5)** | **0.28** | Primary metric |
| **TSS (tuned)** | **0.32** | Optimized threshold |
| **POD** | 0.34 | Probability of Detection |
| **FAR** | 0.90 | High (quiet Sun) |
| **PR-AUC** | 0.35 | Precision-Recall |
| **Brier** | 0.064 | Calibration |
| **BSS** | -2.17 | Needs calibration |
| **r_integral** | 0.82 | Neupert correlation |
| **r_direct** | 0.22 | Weak direct correlation |
| **Lead time** | 3.5 min | HXR leads SXR |

---

## 🔬 Physics: Neupert Effect Validation

| Event | Flare | Band | r_direct | r_integral | Lag | Verdict |
|-------|-------|------|----------|------------|-----|---------|
| 2024-05-11 | X5.8 | CZT 40-60 | 0.22 | **0.92** | 220s | INTEGRAL |
| 2024-05-14 | X8.7 | CZT 40-60 | 0.18 | **0.74** | 320s | INTEGRAL |
| 2024-10-01 | X7.1 | CZT 40-60 | 0.14 | **0.90** | 150s | INTEGRAL |
| 2024-10-03 | X9.0 | CZT 40-60 | 0.19 | **0.69** | 200s | INTEGRAL |
| 2024-05-10 | X3.9 | — | — | — | — | NO_COUPLING |

**Summary**: 4/4 usable events → **INTEGRAL wins** (standard Neupert holds)

---

## 🤖 ML Ablation: Neupert Features Work!

| Model | Features | TSS (fixed) | TSS (tuned) | ΔTSS |
|-------|----------|-------------|-------------|------|
| A | Soft X-ray only | 0.18 | 0.24 | — |
| B | + Soft proxy | 0.16 | 0.22 | -0.02 |
| C | + Real HXR | 0.22 | 0.28 | **+0.04** |
| D | + Neupert features | **0.28** | **0.32** | **+0.04** |

**Top Feature**: `neupert_alpha` (trailing OLS α in dSXR/dt = α·HXR)

---

## ⚡ Quick Commands

```bash
# Neupert physics test
python scripts/neupert_analysis.py --raw data/raw --band CZT2 --sweep-bands

# ML evaluation on real Aditya data
python scripts/evaluate_aditya_real.py

# GOES-only live evaluation
python scripts/evaluate_live_data.py

# All tests (50 passed)
python -m pytest tests/ -q
```

---

## 📊 Key Files at a Glance

| File | Purpose |
|------|---------|
| `src/forecast/pipeline.py` | End-to-end pipeline (500 lines) |
| `src/forecast/deep_forecaster.py` | AdityaSolarTransformer + NumPy fallback |
| `src/forecast/pipeline.py` | Feature engineering (22 features) |
| `src/forecast/train.py` | Walk-forward CV + LightGBM |
| `src/forecast/metrics.py` | TSS, HSS, BSS, PR-AUC, ECE, LT-vs-FAR |
| `scripts/neupert_analysis.py` | Neupert physics test |
| `scripts/evaluate_aditya_real.py` | ML evaluation on real data |
| `scripts/evaluate_live_data.py` | GOES live evaluation |

---

## 🎯 Key Takeaways for Stakeholders

| Audience | Key Message |
|----------|-------------|
| **Scientists** | Neupert effect validated on Aditya-L1 (4/4 events, r=0.82) |
| **ML Engineers** | Neupert features add +0.04 TSS; neupert_alpha is top feature |
| **Operations** | Not ready for ops (FAR=0.90, BSS negative) - needs calibration |
| **Management** | First verifiable Aditya-L1 benchmark; physics-validated ML |

---

## 🚨 Critical Corrections Made

| Bug | Original Claim | Corrected |
|-----|----------------|-----------|
| Band selection | "CDT" matched all CDTE → 1.8-90 keV | Parse EXTNAME, require >22 keV |
| Baseline | np.median=0 under zero-inflation | Median of nonzero GTI samples |
| Sentinel -1.0 | Failed fit won tie-break | Sentinel=-9.0, require r≥0.3 |
| Zero-inflation | Shared zeros faked correlation | Reject >90% zero windows |
| NaN propagation | X9.0 silently dropped | Interpolate finite, mask NaN |

---

## 🚀 Next Steps Priority

| Priority | Task | Effort |
|----------|------|--------|
| 1 | Download 25-50 more Aditya paired events | Medium |
| 2 | Build 6-12 month GOES+NOAA Tier-1 dataset | High |
| 3 | Calibration (Platt/Isotonic) | Medium |
| 4 | M/C-class generalization | High |
| 5 | Operational calibration (Platt/Isotonic) | High |

---

## 📁 Key Files Quick Access

```
solar-flare-system/
├── paper/PAPER_DRAFT.md          # Full paper (Markdown)
├── paper/PAPER_DRAFT.docx        # Word document
├── paper/paper.tex               # LaTeX source
├── paper/figures/                # 10 publication figures
├── scripts/evaluate_aditya_real.py    # Main evaluation
├── scripts/neupert_analysis.py       # Neupert physics test
├── src/forecast/pipeline.py          # End-to-end pipeline
├── src/forecast/deep_forecaster.py   # Transformer + NumPy fallback
└── tests/test_neupert_qc.py          # 20 regression tests
```

---

## 🚀 One-Liner for Slides

> **"First verifiable Aditya-L1 flare nowcasting benchmark: Neupert physics validated (4/4 events, r=0.82), causal ML features add +0.04 TSS, honest benchmark at TSS=0.28."**

---

*Generated from solar-flare-system v1.0 | 50 tests passing | 20 Neupert QC regression tests*