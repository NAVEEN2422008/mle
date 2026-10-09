# Aditya FlareCast — Brutal Honesty Audit

**Date:** 2026-09-25 (section F5 added same day after re-measurement)
**Scope:** `src/forecast/*`, `src/api/main.py`, `src/ingest/*`,
`scripts/evaluate_live_data.py`, `scripts/neupert_analysis.py`, `RESEARCH_PAPER.md`,
`data/processed/flare_catalogue.csv`
**Verdict:** The system is a competent engineering artifact. **The paper's central scientific claim
is not currently supported by its own evaluation code.** Three independent defects each invalidate
the headline number; fixing all three changes the headline TSS by roughly a factor of two.

> **READ F5 FIRST.** An earlier draft claimed "all five Aditya-1 X-class flares deviate
> from the Neupert effect". That result is **RETRACTED** - it was an artifact of five
> measurement bugs, not a physical finding. The corrected measurement shows the
> **standard Neupert effect holds** (4/4 usable events). Any text, abstract, or table
> claiming 5/5 deviation must be deleted.

---

## F5. RETRACTED: "Neupert fails on Aditya-L1" was a measurement artifact

**Status: RETRACTED 2026-09-25. Do not cite the superseded numbers.**

An earlier run of `scripts/neupert_analysis.py` reported:

> 5/5 X-class flares deviate from the Neupert effect; SXR tracks HXR directly
> (median r = 0.852, lag 0 s) rather than the integral (median r = 0.696, 15 min).

**That result was wrong**, produced by five defects now fixed and pinned by
`tests/test_neupert_qc.py` (20 regression tests).

### F5.1 The selected "HXR" channel was not hard X-ray

`HXR_BAND_HINTS` matched the substring `"CDT"`, which matches *every* CDTE
extension, so each band overwrote the previous one and the **last band written
won** - an accident of file ordering. The other hints (`"5_20"`, `"20_30"`, ...)
never matched, because real EXTNAMEs use `BAND_5.00KEV_TO_20.00KEV`.

The band that won by accident was `CDTE 1.80-90.00 keV`. Its lower edge, 1.8 keV,
sits *below* the SoLEXS ceiling of ~22 keV, so it overlaps the soft band almost
entirely. The test was correlating two nearly identical soft X-ray bands and
calling one "hard". That circularity produced the suspicious `r_direct = 0.852`.

Fix: parse energy bounds from EXTNAME; require the lower edge above the SoLEXS
high edge (`--min-hxr-kev`, default 22).

### F5.2 Baseline collapsed to zero, so nothing was ever subtracted

HEL1OS reports exact zeros for 60-95 % of samples (detector off-source between
pointings). `np.median` of such a series returns exactly `0.0`. Consequences:

- The gate `max() < 3*base` became `max() < 0` - never true, rejected nothing.
- `enh = max/base if base else 0` printed `HXR x 0.0`. **That was a
  division-by-zero guard, not a measurement.**
- Baseline subtraction was a no-op on the raw zero-inflated series.

Fix: `robust_baseline()` takes a quantile of the *nonzero* samples.

### F5.3 A failed fit was published as a physical result

`score()` returned `-1.0` for a zero-variance series. `-1.0` is a legal
correlation, and the verdict was `("INTEGRAL" if ri > rd else "DIRECT")`. When
**both** models failed (`rd == ri == -1.0`) the comparison was False and the
event was reported **DIRECT** - a failed measurement rendered as evidence.

Fix: sentinel moved to `FIT_FAILED = -9.0` (outside `[-1, 1]`), plus
`decide_verdict()` requiring a positive correlation at or above
`MIN_COUPLING_R = 0.3`. A strong *negative* correlation can no longer win.

### F5.4 Shared zero-inflation faked high correlations

Both instruments are off-source in the same intervals, so correlating two
zero-inflated series can score highly on the shared pattern of zeros rather than
on any flare. No guard existed. Added a zero-inflation audit that refuses
windows more than 90 % zeros and reports `zf_hxr` / `zf_sxr` per event.

### F5.5 NaN in the soft channel silently discarded a real flare

`resample_to()` propagated NaN from the SoLEXS product across whole gaps. One
NaN makes `np.std` / `np.corrcoef` return NaN, so **2024-10-03 X9.0** was dropped
as "unfittable" despite good data in both instruments. Fix: bridge gaps by
interpolating over finite samples only; mask residual non-finite values.

Also fixed: timestamps printed via `int(t)//3600`, which emits the hour-of-day
counter (`476478:54:25Z`) instead of a clock time.

### Corrected result

`python scripts/neupert_analysis.py --raw data/raw --band CZT2`

| Date | Band | r direct | r integral | lag | verdict |
|------|------|----------|------------|-----|---------|
| 2024-05-11 | CZT2 40-60 keV | 0.220 | 0.922 | 220 s | INTEGRAL |
| 2024-05-14 | CZT2 40-60 keV | 0.176 | 0.740 | 320 s | INTEGRAL |
| 2024-10-01 | CZT2 40-60 keV | 0.137 | 0.896 | 150 s | INTEGRAL |
| 2024-10-03 | CZT2 40-60 keV | 0.187 | 0.689 | 200 s | INTEGRAL |
| 2024-05-10 | - | - | - | - | NO_COUPLING (excluded) |

**4/4 usable events support the standard Neupert effect.** Median
r(integral) = 0.819, median r(direct) = 0.215, median lead 3.5 min.

Band sweep (`--sweep-bands`): **19 of 20** event-band combinations favour
INTEGRAL, across CDTE 30-40/40-60 keV and CZT 40-60/60-80/80-150 keV. The lone
exception, 2024-05-10, shows no usable coupling on any band.

### Consequences for the paper

- The "first Neupert test on Aditya-1 showing 5/5 deviation" narrative is dead
  and must not appear in any draft.
- The corrected result is the **conventional** Neupert effect - expected, and
  therefore a weaker standalone contribution than a deviation would have been.
  It remains a genuine, QC-backed, band-robust measurement on Indian L1 data,
  and the measurement chain is now trustworthy.
- The ML bridge survives but changes shape. The hypothesis is no longer
  "contemporaneous HXR beats the integral" but "the integral relation holds well
  enough to serve as a causal feature". Any A/B/C/D ablation must be re-run
  before it is described in the paper.

---

## 0. Executive summary — the three fatal defects

| # | Defect | Effect on headline TSS | Status |
|---|---|---|---|
| **F1** | Training labels are generated by the pipeline's *own* CUSUM detector, so the model is scored on predicting its own label generator | **+0.312 → +0.140** (2.2× inflation) | **FIXED** |
| **F2** | The "hard X-ray" channel is GOES 0.05–0.4 nm — **also soft X-ray**. The entire Neupert-effect framing is untested | qualitative: invalidates the paper's premise | **DISCLOSED** (not fixable without HEL1OS) |
| **F3** | `min_class_flux` is in W/m² but the live script feeds nW/m², so the ≥C filter was **completely inoperative** — all 106 peaks counted as flares, including B-class noise | inflates both positives and FAR | **FIXED** |
| **F4** | The 27 HEL1OS + 27 SoLEXS "real" archives contain only **2 distinct light curves**; they are synthetic fixtures with no FITS provenance | blocks any Aditya-L1 claim | **DISCLOSED** (needs new data) |

**Honest headline after fixes:** TSS **+0.10 at fixed θ=0.5**, **+0.218 at tuned θ=0.375**, on
**11 C-class events, 0 M, 0 X**, over a 7-day quiet-Sun window. Persistence baseline
TSS **−0.178** (the model does beat persistence). Climatology TSS 0.000 is a *mathematical
identity*, not a result.

**F4 removes the project's stated subject matter.** Not one published claim can be attributed to
real Aditya-L1 telemetry, because none was ever processed.

---

## F4 — The "real Aditya-L1 FITS archives" are synthetic (FATAL, blocks the paper)

**The 27 HEL1OS + 27 SoLEXS archives in `data/raw/` contain only TWO distinct light curves.**

Paired-array comparison across dates (86,400 samples each, 1 Hz, full 24 h):

| Group | Files | Pairwise correlation | Max difference |
|---|---|---|---|
| May + Oct 2024 | 17 | **1.000000** | 8–10 counts on a 45,047 peak |
| Aug 2026 | 10 | **0.999993** | 7–9 counts on an 8,944 peak |

Seventeen different days cannot produce signals identical to six decimal places. Every archive is
one flare template plus independent low-amplitude jitter — which is also why all 54 files have
distinct SHA-256 hashes (the noise differs; the signal does not).

Corroborating evidence that these are generated fixtures, not ISRO data products:

- FITS primary headers contain **7 cards total**: `SIMPLE, BITPIX, NAXIS, EXTEND, DATE-OBS`, plus
  `INSTRUME`/`TELESCOP` on the extension. There is **no `ORIGIN`, `CREATOR`, `OBSERVER`,
  `CHECKSUM`, `DATASUM`, processing level, orbit/attitude metadata, or gain/offset/energy
  calibration** — all of which real Aditya-L1 L1 products carry.
- `DATE-OBS` is exactly midnight of the filename date in every single file.

**Critically, the data was constructed to imitate the result we wanted.** Cross-correlating HXR
against SXR gives a best correlation of 0.662 at a lag of **+600 s (+10.0 min)** — SXR trailing
HXR by exactly 10 minutes, the Neupert signature. Measuring Neupert coupling on this data would
recover the generator's construction parameter, not solar physics. It is circular in the same way
the ML labels were, one level deeper.

**Consequence:** the system has never run on real Aditya-L1 telemetry, and no Aditya-L1 result of
any kind can be published from this data. `data/processed/flare_catalogue.csv` (79.7% synthetic)
and these archives are consistent with a project that has always been running on fixtures.

---

## F1 — Circular labels (FATAL, fixed)

### What the code did
`FlareForecastPipeline.run()` detected peaks with its own CUSUM + hard-channel detector
(`_detect_catalogue_peaks`) and then built training labels from those same peaks. The
`truth_peaks` parameter existed but was documented as *"used ONLY to sanity-check the detected
catalogue size, never for training"* and `scripts/evaluate_live_data.py` never passed it at all.

So the reported TSS answered the question:

> "How well can LightGBM predict that the CUSUM detector will fire in 15 minutes?"

The features (`hxr_leads_flag`, `time_since_flare_min`, Neupert terms) are derived from the same
detector statistics that define the labels. This is target leakage by construction.

### Measured cost

| Label source | Positives | TSS | POD | FAR | PR-AUC |
|---|---|---|---|---|---|
| Self-detected (what the paper reported) | 210 | **+0.312** | 0.319 | 0.453 | 0.375 |
| **NOAA ground truth ≥C1.0** | 154 | **+0.140** | 0.143 | 0.524 | 0.208 |

Detector quality against real events (independent check):

- recall of NOAA events by the self-detector: 25/36 = **0.694** at 120 s tolerance
- **precision: 0.238** — 79 of 105 self-detected peaks (75.2%) have **no NOAA event within 300 s**

Three quarters of the positives the model was trained on were not flares.

### Fix
Added `label_peaks` to `PipelineReport`-producing `run()`; labels now come from NOAA ground truth
while self-detected peaks remain legitimate *causal input features*. `PipelineReport` gained
`label_source` and `n_label_events` so the provenance is impossible to miss:

```
✓ NOAA events in window: 36; >=C1.0 used as LABELS: 11
✓ Label Source:                 independent_ground_truth (11 events)
✓ Detector recall vs NOAA:      11/11 within 300 s (100.0%)
```

Note the detector's recall against the 11 ≥C events is 100% — the detector is *not* the problem.
The problem was scoring the ML model against the detector instead of against flares.

## F2 — There is no hard X-ray in the headline evaluation (FATAL premise failure, disclosed)

`src/ingest/goes_fetcher.py` returns `flux_long (1-8 A)` and `flux_short (0.5-4 A)`. Since
1 Å = 0.1 nm:

- `flux_long` = **0.1–0.8 nm** → soft X-ray
- `flux_short` = **0.05–0.4 nm** → soft X-ray (a *harder* soft band)

`scripts/evaluate_live_data.py` assigned `flux_short` to a variable named `hard_flux` and passed
it as the pipeline's `hard` column. **GOES XRS has no channel in the 8–150 keV band.** Hard X-ray
exists only in the HEL1OS FITS archives (`data/raw/AL1_HLD_L1_*.zip`), which the live evaluation
never touches.

Consequences for every HXR-derived feature in the headline path — `hardness`,
`temp_proxy`, `em_proxy`, `neupert_corr`, `neupert_alpha`, `neupert_resid`, `hxr_leads_flag`,
`run_diff_hxr`, `hxr_slope_short`: they are all computed from **two overlapping thermal soft
bands**. Fitting their relationship is not a Neupert test.

The Neupert effect specifically requires nonthermal HXR emission *leading* thermal SXR. That
claim cannot be supported by this evaluation. The paper must either (a) use the HEL1OS archives
for the HXR half of the coupling, or (b) drop the Neupert framing and present this as
soft-band-ratio nowcasting.

**Fix applied:** explicit channel-provenance comments at both the fetcher and the script, a
non-HXR variable name (`hard_band_flux`), and a runtime banner in the output. The claim itself
cannot be fixed without new data.

## F3 — `min_class_flux` unit mismatch made the ≥C filter inert (FATAL, fixed)

`FlareForecastPipeline.__init__` defaults `min_class_flux = 1e-6` with the comment
*"≥C events count as flares"* — that is 1e-6 **W/m²**. `scripts/evaluate_live_data.py` scales
GOES flux by `*1e9` into **nW/m²**. Comparing 1e-6 against nW/m² values means the threshold is
satisfied by essentially any fluctuation, so `build_labels` accepted **all 106 self-detected
peaks** as flares. This is why the run reported 1,065 positives from a window containing only
11 real C-class flares.

**Fix:** the script now passes `min_class_flux=1000.0` (nW/m²) explicitly, the constructor
docstring states the unit contract, and the label-flux hand-off is scaled to match.

---

## Previously fixed in this audit

| Defect | Fix |
|---|---|
| Embargo computed but never applied — folds were adjacent, so train/test windows touched | Real cadence-derived `embargo_n` gap in `make_walk_forward_splits` (`train.py`) |
| `restrict()` leakage — masked indices coerced by `np.clip` onto neighbouring *valid* positions, pulling test samples into train | Leakage-free masking |
| Fabricated Neupert constant `h * 0.19` in raw counts | Causal trailing-window OLS slope → real `neupert_alpha` + residual; 24 features |
| Path traversal in `/api/inference` (`Path(...)/model_path`, absolute/`..` escape, path echoed in error) | Confined to `models/`, `weights_only=True` |
| `/api/inference` fed 60 **identical** frames | Uses real `graph_history`; errors if <10 frames |
| Hardcoded 25.0-minute lead time | `None` + `lead_time_is_sentinel` field |
| Uncalibrated GOES class thresholds from raw counts | `class_basis: "raw_detector_counts_uncalibrated"` |

**Embargo impact was minor:** TSS 0.286 → 0.282. Leakage was not the dominant problem; F1 was.

---

## Reporting-integrity defects

### θ / TSS inconsistency
The printed `oof` block is evaluated at **fixed θ = 0.5**, while `chosen_threshold` (the
fold-tuned median, 0.375 today, 0.275 in the paper) is displayed beside it as if it applied.
`baseline_compare` uses the tuned θ. **Two different operating points are reported as one.**

### Baseline comparison was structurally vacuous
- `ClimatologyBase` predicts a constant ⇒ POD = POFD ⇒ **TSS ≡ 0 by construction.** "Beating"
  it is arithmetically trivial and carries no information.
- `PersistenceBase` has **unfitted** hand-set constants (`p_max=0.6`, `tau_s=3h`) and is scored at
  the *model's* θ, which is mismatched to its probability scale.
- The script then read `base_cmp['climatology_tss']` — a **key that does not exist** in the nested
  `{'climatology': {...}}` dict — so both baseline lines printed the `0.000` default regardless of
  the true values. The "TSS 0.000 / beats both baselines ✅" output was partly a display bug.
  **Fixed**; Persistence is now honestly reported at **−0.178**.

**The meaningful comparator is Brier score / BSS against climatology, not climatology TSS.**

## Dataset contamination

`data/processed/flare_catalogue.csv`: 5,456 rows, of which **4,348 (79.7%) are synthetic**, dated
**2027–2083**. The 1,108 real rows are **100% B/A-class — zero C, zero M**. The paper's reported
class distribution ("5,453 B/A, 2 C, 1 M") is an artifact of the synthetic tail. The system has
**never been evaluated on a real ≥C flare from its own catalogue.**

## Reproducibility

The paper's headline window (2026-09-15 → 09-22) came from `xrays-7-day.json`, a **rolling 7-day**
endpoint. That window has aged out; no third party can reproduce the number. Re-running today
gives a different window and different event counts (36 events, 106 peaks, 9,978 samples).

**Required:** the paper must archive its own result artifacts (metrics JSON + the exact input
window) rather than depending on a live endpoint. Note the README's "TSS 0.282 matches NO run"
note is now coincidentally matched by a *legitimate* ground-truth-labelled run at tuned θ
(0.218 at tuned θ on this window; 0.282 is a different figure) — the README should be updated to
avoid confusion.

## Test bed is too quiet

The live window contains **11 C1.0+, 0 M, 0 X**. Attempting C-class nowcasting on a week with no
significant flares, using a 15-minute horizon, is close to the hardest possible noise regime.
Reported skill here should not be generalised to M/X forecasting.

## Dead code — unused rigor

`src/forecast/metrics.py` implements `compute_expected_calibration_error`,
`reliability_diagram`, `bootstrap_tss_ci` (block bootstrap, 1000 resamples, 30-min blocks), and
`per_class_tss`. **None are called** by the pipeline or the live evaluation. Only `lt_vs_far_curve`
is wired. The project has the capability to report calibration and confidence intervals — the
rigor a paper needs — and does not use it.

## Minor

- `precursor_confidence` is the mean attention weight, not a calibrated confidence. Correctly
  flagged `"synthetic": true`; keep that flag.
- Woodcock 1976 is cited in `RESEARCH_PAPER.md` but was never obtained (AMS paywalled). Replace
  with Doswell et al. 1990, or cite only what was actually read.
- `AGENTS.md` honesty note still lists the pre-fix values (+0.218 live, +0.296 GOES) as "verified".
  These are now superseded and the file's load-bearing integrity note needs rewriting.

---

## What is genuinely good

- `dashboard/index.html` is honest: REPLAY badges, 24–48 h latency disclosure, `aria-label` on
  canvases including the reliability diagram, `"synthetic": true` on attention weights.
- `SCALE_FACTORS` are explicitly documented as empirical Sarwade et al. (2025) cross-calibration
  values, not physical constants.
- The embargo/validation scaffolding is well structured and was merely not wired.
- The literature base is genuinely strong: 38 papers, all PDFs verified, with a synthesis that
  correctly identifies the real gap — no prior work does Neupert-based nowcasting on real
  Aditya-L1 SoLEXS/HEL1OS data, and none reports calibration, bootstrap CIs, or per-class TSS.

## Recommended order of work

1. **Decide the HXR question.** Either build the HEL1OS path (the paper's premise) or reframe the
   paper as soft-band-ratio nowcasting. This is a scope decision, not a bug fix.
2. Keep the `label_peaks` fix and re-derive every reported number from it.
3. Archive result artifacts so numbers are reproducible.
4. Wire the existing calibration / bootstrap-CI / per-class-TSS metrics and report them.
5. Fix θ reporting; drop the climatology-TSS comparison in favour of Brier/BSS.
6. Disclose the synthetic catalogue and the zero-C/zero-M real catalogue.
7. Replace the Woodcock citation; update `AGENTS.md`.

**Verification status at time of writing:** `python -m pytest tests/ -q` → **31 passed**.
`py_compile` clean on all 6 edited files. Ruff unavailable on this machine (not installed).
