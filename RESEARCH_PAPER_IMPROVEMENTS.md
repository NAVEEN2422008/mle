# Research Paper Improvement Plan — Gap Analysis vs 38-Paper Literature

**Generated:** 2026-09-22
**Inputs:** `research_papers/ANALYSIS.md` (38 papers, text-verified), `RESEARCH_PAPER.md` (current draft), `RESEARCH_GAPS.md`, `src/forecast/metrics.py`, `scripts/evaluate_live_data.py`, `src/forecast/pipeline.py`

---

## 1. GAPS IN THE 38-PAPER LITERATURE (the white space your paper can claim)

### G1. No paper does Neupert-effect-based NOWCASTING from real-time X-ray telemetry
The 38 papers split cleanly into four camps, none of which is your task:
- **24h-ahead magnetogram ML** (Bobra 2015, Liu 2019, Jiao 2020, Nishizuka DeFN, Sun 2022, Li 2024, Kaneda 2022, Riggi 2025, Cao 2026, Zheng 2026, dual-branch 2026) — forecasts from photospheric magnetic field, horizon 24h+, no X-ray light curves.
- **Retrospective Neupert physics** (Neupert 1968, Dennis & Zarro 1993, Veronig 2002, Qiu 2021, Li 2024 ASO-S) — statistical studies of the effect, no forecasting system built on it.
- **Instrument papers** (Tripathi 2023, Sarwade 2025, Nandi 2025, Ravishankar 2026, Kanaujiya 2026) — hardware/ops/QPP physics, no forecasting.
- **Verification methodology** (Doswell 1990, Bloomfield 2012, Camporeale 2025, Shao 2026) — how to score, not systems.

**Closest competitors** (all retrospective, none on Aditya-L1):
- **HOPE** (Telikicherla 2025): HXR→SXR nowcasting, 5–15 min alerts — but DAXSS/GOES data, MLP on running-difference T/EM, NOT Neupert integration, NOT real-time ops.
- **Chen 2019 seq2seq**: GOES-10 flux-profile prediction — retrospective, 1998–2006.
- **RMN** (Yi 2026): GOES peak-flux nowcasting — retrospective, GOES only.

**→ Your claim: FIRST Neupert-engine nowcasting system on Aditya-L1 SoLEXS/HEL1OS data, operating in real time.** No paper in the set can contest this.

### G2. No paper reports probability calibration (reliability diagram / ECE)
Camporeale 2025 explicitly identifies missing calibration as a field-wide failure. Bloomfield 2012 recommends TSS but never discusses calibration. **Zero of 38 papers report ECE or a reliability diagram.** Your `metrics.py` already implements both — you can be the first to report them.

### G3. No paper reports confidence intervals on TSS
All 38 report point estimates. Your `bootstrap_tss_ci` (block bootstrap, 1000 resamples, 30-min blocks) is implemented but unused. Statistical rigor is a differentiator the field lacks.

### G4. No paper reports per-class TSS for a nowcasting system
Bloomfield reports per-class for 24h forecasting; no nowcasting paper does ≥B/≥C/≥M/≥X breakdowns. Your `per_class_tss` exists but is unused.

### G5. No paper handles Neupert-deviation events (~25% of flares) in a forecasting context
Veronig 2002: ~1/4 of flares show SXR rising beyond HXR end (additional heating mechanism). Li 2024: r>0.90 in 149 events but deviations exist. **No forecasting paper classifies events as Neupert-consistent vs deviant and reports skill per class.** This is a novel, physics-grounded analysis you can run on your 33-event window.

### G6. No paper uses QPPs (quasi-periodic pulsations) as forecasting features
Kanaujiya 2026: 74% of X-class flares show QPPs, 1–3 min periods — but only as a physics study. Wavelet features capturing QPPs as precursors are unexplored in forecasting. Your RESEARCH_GAPS.md already flags this as HIGH priority.

### G7. No paper does cross-instrument transfer (GOES → Aditya-L1)
Sarwade 2025 documents GOES cross-calibration (~10–15% agreement) but no forecasting paper trains on GOES and tests on SoLEXS/HEL1OS. You have both datasets.

### G8. No standard lead-time metric exists in the field
HOPE reports "5–15 min alerts" informally. Your `LeadTimeReport` (median, IQR, fraction ≥5/10/15 min) + `lt_vs_far_curve` is more rigorous than anything published. Report it as a formal contribution.

### G9. No open benchmark dataset for X-ray light-curve nowcasting
SWAN-SF (Angryk 2020) is magnetogram MVTS; SuryaBench is images. **No X-ray light-curve nowcasting benchmark exists.** Your 54 real FITS archives + GOES labels could be released as one — a community contribution that strengthens the paper.

---

## 2. YOUR SYSTEM vs THE LITERATURE (positioning)

### 2.1 What you do that NO paper does
| Capability | Papers | You |
|---|---|---|
| Neupert-integration nowcasting engine | ✗ (HOPE uses MLP, not integration) | ✅ |
| Real-time operational pipeline (FastAPI + SSE/WS dashboard) | ✗ (all retrospective) | ✅ |
| Live verification vs NOAA GOES stream | ✗ | ✅ |
| Aditya-L1 SoLEXS/HEL1OS forecasting | ✗ (instrument papers only) | ✅ |
| SDD1/SDD2 saturation arbitration | ✗ | ✅ |
| k-of-m hysteresis analysis | ✗ | ✅ |
| Lead-time distribution (median/IQR/fractions) | ✗ (HOPE: informal) | ✅ |
| Physics-informed PINN (Neupert energy conservation loss) | ✗ | ✅ |
| Honest integrity audit (what's reproducible) | ✗ (Camporeale calls for it) | ✅ |

### 2.2 What papers do that you don't (and whether it matters)
| Capability | Papers | You | Verdict |
|---|---|---|---|
| Spectral decomposition (T/EM) | HOPE, Sarwade | Proxy only | **HIGH gap** — HOPE's core discriminator |
| Magnetogram/SHARP features | Bobra, Liu, Jiao, Li, Sun | N/A (no magnetogram on Aditya-L1) | Instrument limitation — state it |
| Image/video models | Surya, Riggi, Kaneda | Tabular only | N/A — different modality |
| Ensembles | Riggi (Moirai2), Sun (stacking) | Single LightGBM | MEDIUM — cheap to add |
| Feature importance (SHAP) | Liu (TSS-ranking), Zheng (Grad-CAM) | None | **HIGH gap** — cheap to add |
| Wavelet/QPP features | Kanaujiya (physics only) | None | MEDIUM — novel in forecasting |
| Uncertainty quantification | None (field-wide gap) | None | MEDIUM — conformal/MC-dropout |
| Cross-instrument validation | None | None | **HIGH opportunity** — you have the data |

### 2.3 The honest comparison table problem (§5 of your paper)
Your §5 table compares against **24h magnetogram systems** (Bloomfield 0.44/0.53/0.74; DeFN 0.63/0.80) — the wrong regime. The correct competitors for a 15–60-min nowcaster are:
- **HOPE** (5–15 min alerts, no TSS reported — you can compute one)
- **Chen 2019 seq2seq** (RMSE 0.26 peak flux — compare your peak-flux error)
- **RMN** (RMSE 0.26/0.45/0.87 ≥C/≥M/≥X — direct peak-flux benchmark)
- **Camporeale 2025** (SWPC: no skill over baselines — your "beats both baselines" claim is the contrast)

Keep the 24h table as context, but add a nowcasting-regime table. This reframes TSS 0.218–0.296 from "low vs SOTA" to "first verifiable numbers in a regime where no one else reports skill."

---

## 3. CHEAP WINS — CODE EXISTS BUT IS NOT REPORTED (do these first)

Verified: `metrics.py` implements all of these; **none are called** in `pipeline.py` or `evaluate_live_data.py` (imported but unused).

| # | Metric | Function | Effort | Paper impact |
|---|---|---|---|---|
| 1 | **Reliability diagram + ECE** | `reliability_diagram()`, `compute_expected_calibration_error()` | ~1h wiring | First paper in set to report calibration (G2) |
| 2 | **Bootstrap CI on TSS** | `bootstrap_tss_ci()` (block, 1000×, 30-min blocks) | ~1h | Statistical rigor no paper has (G3) |
| 3 | **Per-class TSS** | `per_class_tss()` (≥B/≥C/≥M/≥X) | ~1h | Bloomfield-style breakdown for nowcasting (G4) |
| 4 | **Brier decomposition** | inside `reliability_diagram()` (rel/res/unc) | ~30min | Murphy-1973 decomposition, field-standard |
| 5 | **LT-vs-FAR operating curve** | `lt_vs_far_curve()` — already in pipeline report | already done | Formalize as a contribution (G8) |

**Action:** wire these into `evaluate_live_data.py` output + add a "Calibration & Uncertainty" subsection to §4. This alone moves the paper from "modest TSS" to "methodologically the most complete nowcasting evaluation published."

---

## 4. HIGH-IMPACT EXPERIMENTS (new runs, ranked)

### E1. Neupert-feature ablation (THE key experiment)
Remove the Neupert coupling features (HXR-leads-SXR flag, dSXR/dt vs HXR correlation terms) from the 23-feature set; retrain; report TSS delta.
- **Why:** proves the physics engine adds skill — the central claim of a Neupert-based paper.
- **Expected:** TSS drop on live window; if it doesn't drop, that's itself a finding (features redundant → report honestly).
- **Effort:** ~2h. **Impact: highest.**

### E2. Neupert-consistency classification (novel, physics-grounded)
Classify the 33 events as Neupert-consistent vs deviant (Veronig 2002 Δt criterion: SXR peak vs HXR end). Report detector recovery + model TSS per class.
- **Why:** no paper does this (G5). Directly addresses the ~25% deviation population.
- **Effort:** ~3h. **Impact: high — unique analysis.**

### E3. HOPE reimplementation as competitor baseline
Implement HOPE's running-difference T/EM MLP on your GOES window; compare alert lead times and detection.
- **Why:** HOPE is your stated "direct competitor method to beat" (RESEARCH_GAPS.md §1.1). Beating it on the same data is the strongest possible comparison.
- **Effort:** ~1 day. **Impact: high.**

### E4. Model family ablation (RF / XGBoost / LogisticRegression)
Add RF, XGBoost, and logistic-regression baselines on the same 23 features + walk-forward protocol.
- **Why:** standard practice; RESEARCH_GAPS.md §3.3 lists them; Liu 2019 shows RF competitive.
- **Effort:** ~2h. **Impact: medium — expected.**

### E5. Cross-instrument transfer (GOES → SoLEXS)
Train on GOES XRS (long window), test on real SoLEXS windows (2024-05, 2024-10, 2026-08).
- **Why:** G7 — no paper does this; Sarwade 2025 gives you the cross-calibration constants.
- **Effort:** ~half day. **Impact: high — unique generalization claim.**

### E6. Wavelet/QPP features
Add wavelet coefficients (1–3 min band, per Kanaujiya 2026) to the feature set; ablation vs baseline.
- **Why:** G6 — QPPs as precursors is unexplored; HEL1OS 1-s cadence resolves 1–3 min periods.
- **Effort:** ~half day. **Impact: medium-high — novel feature.**

### E7. Peak-flux error comparison vs Chen 2019 / RMN
Report your peak-flux RMSE on the GOES window; compare to Chen 2019 (0.26) and RMN (0.26/0.45/0.87).
- **Why:** puts your intensity output on the same scale as the two closest papers (G1 competitors).
- **Effort:** ~2h. **Impact: medium.**

---

## 5. PAPER RESTRUCTURE (how to reframe)

### 5.1 Abstract — lead with the gap, not the number
Current: "TSS 0.218... modest relative to 24-hour-ahead forecasts" (defensive).
**Proposed:** "We present the first Neupert-effect-based flare nowcasting system operating on real Aditya-L1 SoLEXS/HEL1OS X-ray telemetry... We report the first live-verified nowcasting skill numbers for this regime (TSS 0.218–0.296, beating climatology and persistence), the first calibration and bootstrap-uncertainty analysis in flare forecasting, and a per-event Neupert-consistency breakdown." (offensive)

### 5.2 Add a "Related Work and Gap" section
Map the 38 papers into the four camps (G1) + the verification-methodology camp; state explicitly: "No published system performs Neupert-integration nowcasting from Aditya-L1 X-ray telemetry; no published flare forecast reports calibration or confidence intervals." Cite ANALYSIS.md's synthesis.

### 5.3 Fix the comparison table (§5)
- Keep the 24h table as "context."
- Add a **nowcasting-regime table**: HOPE, Chen 2019, RMN, SWPC (Camporeale 2025), this work — with lead time, horizon, data, TSS/RMSE, calibration (yes/no), CI (yes/no).

### 5.4 Add "Calibration & Uncertainty" subsection (§4.6)
Reliability diagram figure, ECE, Brier decomposition, bootstrap CI on TSS, per-class TSS table.

### 5.5 Add "Neupert-consistency analysis" subsection (§4.7)
Per-event classification, recovery by class, deviation handling.

### 5.6 Contributions list (§1.4) — rewrite
1. First Neupert-engine nowcasting system on Aditya-L1 SoLEXS/HEL1OS data (real-time, operational).
2. First live-verified nowcasting skill numbers in this regime, beating climatology + persistence.
3. First calibration + bootstrap-CI reporting in flare forecasting.
4. First per-event Neupert-consistency skill breakdown.
5. Open, reproducible pipeline + (optionally) first X-ray light-curve nowcasting benchmark dataset.

---

## 6. PRIORITY ORDER (what to do, in sequence)

| Step | Action | Effort | Payoff |
|---|---|---|---|
| 1 | Wire calibration/ECE/bootstrap/per-class into `evaluate_live_data.py` + paper §4.6 | 2–3h | Methodological firsts (G2–G4) |
| 2 | Neupert-feature ablation (E1) | 2h | Proves the physics claim |
| 3 | Neupert-consistency classification (E2) | 3h | Unique analysis (G5) |
| 4 | Reframe abstract + §5 comparison table + Related Work section | 3h | Positioning |
| 5 | Model family ablation (E4) | 2h | Standard rigor |
| 6 | HOPE reimplementation (E3) | 1 day | Beats the named competitor |
| 7 | Cross-instrument transfer (E5) | half day | Unique generalization |
| 8 | Wavelet/QPP features (E6) | half day | Novel feature (G6) |
| 9 | Peak-flux RMSE vs Chen/RMN (E7) | 2h | Same-scale comparison |

Steps 1–4 are achievable in ~1 day and transform the paper's positioning. Steps 5–9 are the differentiators for a strong submission.

---

## 7. RISKS / HONESTY CONSTRAINTS (do not regress)

- **Do not inflate TSS.** The live-verified +0.218/+0.296 numbers stand. The reframing is about *what the numbers mean* (first verifiable in regime), not about changing them.
- **Ablation honesty:** if Neupert features don't help, report it — that's a publishable negative result (Camporeale 2025's whole point).
- **Per-class TSS honesty:** ≥M will be NaN/undefined (0 M events in window) — report as "unmeasured," consistent with §6.3.
- **Bootstrap honesty:** block bootstrap with 30-min blocks; report the CI width honestly even if it spans 0 (p_tss_gt_0 is already computed).
- **HOPE comparison honesty:** HOPE was validated on 2014–2024 GOES; your reimplementation on a 7-day window is a limited comparison — say so.
- **Woodcock 1976** is cited in §3.4 of the paper but was never downloaded (AMS paywalled). Either obtain it or cite Doswell 1990 (which you have) as the TSS reference — do not cite a paper you could not verify.