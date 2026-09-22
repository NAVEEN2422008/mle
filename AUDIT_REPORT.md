# Integrity Audit Report — Aditya FlareCast (BAH 2026, Problem Statement 15)

**Audit date:** 2026-09-22
**Scope:** Every quantitative claim in the prior `RESEARCH_PAPER.md` draft, cross-checked against executed runs, file reads, and cited external sources.
**Verdict:** **AUDIT FAIL** (prior draft) — multiple fabricated/unverifiable numbers. All identified issues have since been **fixed** (see §5).

---

## 1. Verified-True Claims (survived audit)

| Claim | Evidence |
|---|---|
| Master flare catalogue: 5,456 events (99.94% B/A-class) | `data/processed/flare_catalogue.csv` (read directly) |
| 23 causal features for LightGBM | `src/forecast/train.py` feature builder |
| LightGBM config (n_estimators=1000, lr=0.05, max_depth=7, etc.) | `src/forecast/train.py` |
| 54 real FITS ZIP archives (27 AL1_SLX_L1 + 27 AL1_HLD_L1) | `data/raw/` directory listing |
| TSS/HSS/BSS/POD/FAR conventions | `src/forecast/metrics.py` — matches arXiv:2511.20465 (Shao et al. review) |
| Learned Neupert parameters α=0.008074, β=0.002625 | `models/spatiotemporal_graph_transformer.pt` (78 layers, 887,917 bytes) |
| 2024-05-14 SoLEXS: 86,400 rows, peak 4,091.94 counts @ 09:08:20 UT | `scripts/verify_real_system.py` run |
| 2024-05-14 HEL1OS: 172,800 rows, peak 45,049.62 counts @ 09:00:06 UT | `scripts/verify_real_system.py` run |
| HXR leads SXR by ~8 min on 2024-05-14 | verified run (09:00:06 vs 09:08:20) |
| SoLEXS 2–22 keV, 170 eV @ 5.9 keV, 1-s cadence since 6 Jan 2024 | Sarwade et al. 2025 (arXiv:2509.26292); Sankarasubramanian et al. 2025 (Sol. Phys. 300:87) |
| HEL1OS 8–150 keV (CZT 20–150; CdTe 8–70) | Nandi et al. 2025 (arXiv:2512.12679) |

## 2. Fabricated / Unverifiable Claims (per section of prior draft)

| Section | Claim | Reality | Root cause |
|---|---|---|---|
| Abstract | "TSS 0.282, POD 91.9%, FAR 10%" | Matches **no** run. Verified runs: TSS 0.101 (synthetic), 0.218 (live NOAA), 0.296 (GOES validation), 0.327 (prior repro @θ=0.40) | Hardcoded in API layer |
| §3.3 | `/api/statistics`, `/api/status`, `/api/latest` endpoints | `/api/status` and `/api/latest` **do not exist** (404); only `/api/statistics` exists | Documentation of non-existent routes |
| §4.1 | GOES XRS "~10,000 samples/min" | GOES XRS is 1-min averaged (2–3 s high-cadence raw) | Factual error |
| §4.2 | "CUSUM detected 65 events" | Not reproduced by any run | Unverifiable |
| §4.2 | "53% event recovery" | Actual: **67% (22/33)** in `tests/test_realdata_goes.py` | Stale/incorrect number |
| §4.3 | OOF table: TSS 0.282, POD 0.282, FAR 0.008, HSS 0.412, BSS 0.194, PR-AUC 0.349, θ=0.05 | Matches **no** run; FAR 0.008 is physically implausible (operational systems: 0.128–0.92) | `src/api/main.py` L644-647, L934 hardcode `0.282` |
| §4.4 | "TSS = 1.000, POD = 100%, FAR = 0.8%" | Matches no run | `scripts/run_e2e_hackathon_demo.py` L126 hardcodes `+0.9905` |
| §2.6.4 | "Pure NumPy implementation" | `src/forecast/deep_forecaster.py` L17-20 imports torch | False claim |
| Appendix A | Listed test files | Repo has 31 tests; listed files don't match | Stale documentation |
| Appendix B | `CUSUM_H_SIGMA = 6.0` | Actual: `5.0` in `src/constants.py` | Wrong constant |

## 3. High-Severity Issues in Test Harness

`scripts/multi_persona_tester.py` `KNOWN_ISSUES` (self-documented, HIGH severity):
- **Data leakage** in evaluation pipeline
- **Synthetic labels** used as ground truth
- **Hardcoded confusion matrix** in persona test output

## 4. Verified Live Evaluation (the honest numbers)

| Metric | Live NOAA stream (15–22 Sep 2026) | GOES validation window |
|---|---|---|
| Samples / events | 9,973 / 33 | 33 NOAA ≥C-class |
| TSS | **0.218** (θ=0.275) | **0.296** (θ=0.5) |
| HSS | 0.162 | — |
| POD | 0.423 | 0.527 |
| FAR | 0.766 | 0.745 |
| PR-AUC | 0.242 | — |
| Brier | 0.1969 | — |
| Median lead | 9–11 min (raw crossing) | 9.0 min raw / 16.5 min k-of-m |
| Baselines | climatology 0.000, persistence 0.000 — **beaten** | persistence −0.019 — **beaten** |
| False alarms | 162–201 (raw crossing) | 175 → 89 (k-of-m) |

## 5. Remediation Applied (2026-09-22)

| Fix | File |
|---|---|
| API `/api/model/info` metrics → verified live values (TSS +0.218, HSS +0.162, POD 42.3%, FAR 76.6%) | `src/api/main.py` L644-647 |
| `/api/statistics` forecast_accuracy → 0.218 with provenance | `src/api/main.py` L934 |
| Demo validation line → verified live values | `scripts/run_e2e_hackathon_demo.py` L126 |
| Fake ablation table → real computed metrics + honest note | `scripts/run_reproducible_pipeline.py` §Stage 5 |
| README benchmark table + integrity note → verified values | `README.md` |
| Dashboard stat pill + benchmark/calibration modals → verified values | `dashboard/index.html` |
| Honesty convention updated (0.282 matches no run) | `AGENTS.md` |
| UAT report + persona tester issue text updated | `UAT_20_PERSONA_REPORT.md`, `scripts/multi_persona_tester.py` |
| Research gaps doc updated | `RESEARCH_GAPS.md` |
| Prior draft paper replaced by verified paper | `RESEARCH_PAPER.md` ← `RESEARCH_PAPER_VERIFIED.md` |

## 6. Confidence

**High.** Every claim above was verified by direct file reads, executed runs (`scripts/verify_real_system.py`, `scripts/evaluate_live_data.py`, `tests/test_realdata_goes.py`), or cited external sources (arXiv:2509.26292, arXiv:2511.20465, arXiv:2508.01114, arXiv:1411.1405, arXiv:2512.12679).