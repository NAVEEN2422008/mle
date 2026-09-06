# Aditya FlareCast — Implementation Plan v2 (Research-Informed)
Updated: 2026-08-24 after deep analysis of research bibliography.

## Changes from v1 (driven by paper analysis)

1. **HOPE-inspired features added** (arXiv:2509.05234): running-difference flux,
   temperature proxy dT and emission-measure proxy dEM enter the feature vector.
   HOPE achieves 5-15 min pre-peak alerts with these signatures.
2. **Metrics-first evaluation** (review arXiv:2511.20465): TSS is THE primary metric;
   HSS, BSS, PR-AUC secondary. Accuracy/ROC-AUC explicitly banned from reports.
3. **Mandatory baselines before ML**: climatology (base-rate) and persistence
   ("flaring now => flare soon"). NOAA verification shows persistence is brutally
   hard to beat at long horizons. Any ML model must beat BOTH or it is worthless.
4. **SDD arbitration** (SoLEXS calib paper arXiv:2509.26292): use SDD1 below
   ~1e5 cps; switch to SDD2 above (SDD1 paralyzable saturation). Never read
   SDD1 turnover as a flux dip. If both saturate -> report lower-bound class >=Xn.
5. **GOES end-rule encoded exactly** (Aschwanden & Freeland 2012): event ends when
   flux decays to (x_peak + x_start)/2. Catalogue de-dup requires clean
   return-to-baseline + guard gap between sub-peaks of one complex flare.
6. **Benchmark to beat**: Landa & Reuveni (2022) TSS ~= 0.74 for >=M forecast from
   GOES X-rays alone. Our edge: HEL1OS hard-band + Neupert features.

## Architecture (unchanged spine, filled modules)

```
ingest -> preprocess(fusion) -> nowcast(detectors) -> catalog(master)
      -> forecast(features->baselines->LightGBM) -> api -> dashboard
```

## Workstream Status

| WS | Scope | Status |
|----|-------|--------|
| WS1 | types, constants, readers, merge, fusion, synth | DONE + smoke-tested |
| WS2a | O(1) primitives, CUSUM soft, Poisson-FOCuS hard, Neupert engine | DONE + smoke-tested |
| WS2b | master_catalog.py: hash-bucket index, cross-band merge, dedup | DONE + verified |
| WS3a | metrics.py (TSS/HSS/BSS/POD/FAR/lead-time), baselines.py | DONE + verified |
| WS3b | train.py leakage-free temporal CV, calibration, LT-vs-FAR sweep | DONE + verified |
| WS4 | FastAPI SSE server + dashboard UI | DONE + running on :8000 |
| WS5 | Real PRADAN data ingestion run + mock & live verification | DONE + ingested |

## Acceptance targets (honest)

- Nowcast POD >85% M/X, >70% C on synthetic+GOES-labelled sets; FAR <20%
- Forecast must beat climatology AND persistence on TSS at N=15min
- Median lead time >5 min for >=M; report LT-vs-FAR curve as operating point
- Everything runs offline via synthetic generator (zero credentials)
