# Aditya FlareCast - Research Bibliography
## Curated sources for ISRO BAH 2026 PS-15 (Solar Flare Nowcasting/Forecasting)

Saved: 2026-08-24 | All links verified accessible during project research phase.

---

## A. Mission & Instrument Papers (PRIMARY)

| # | Paper | Source / Link | Why It Matters |
|---|-------|---------------|----------------|
| A1 | **HEL1OS - A Hard X-ray Spectrometer on Board Aditya-L1** (Nandi et al.) | arXiv:2512.12679, Solar Physics 300:140 (2025), DOI 10.1007/s11207-025-02543-8 | Definitive HEL1OS instrument paper: CdTe 8-70 keV + CZT 20-150 keV, 1-s LC cadence in energy sub-bands, 10 ms event lists, L1 products spec |
| A2 | **SoLEXS: Ground Calibration and In-flight Performance** | arXiv:2509.26292 | SoLEXS SDD1/SDD2 areas (7.1063/0.1065 mm2), deadtime model, GOES cross-cal (~10-15% agreement), saturation behavior >1e5 cps |
| A3 | Sankarasubramanian et al. (2017) - SoLEXS design | URSC / PRADAN User Manual (SoLEXS-UserManual.pdf bundled in thecont1/aditya-L1-solar-explorer) | Original instrument concept, 512-ch spectra @1s, timing chain @0.1s |
| A4 | **Aditya-L1 data release announcement** | solarnews.aas.org 2025-01-14; pradan1.issdc.gov.in/al1 | Data access: registration, tranches, FITS format confirmation |

## B. Nowcasting / Detection Algorithms

| # | Paper | Source / Link | Why It Matters |
|---|-------|---------------|----------------|
| B1 | Aschwanden & Freeland (2012) - Automated GOES flare detection | Solar Physics | The classic AF algorithm: local min/max search, start/peak/end characterization - basis of our GOES FSM port |
| B2 | Szaforz et al. (2017) - Flare Characteristics from X-ray Light Curves (SphinX) | DOI 10.1007/s11207-017-1101-8 | Semi-automatic peak detection on 1-s cadence soft X-rays; elementary flare profile (Gaussian*exp-decay); sub-GOES sensitivity classes |
| B3 | New catalogue of solar flares from GOES soft X-ray (2023/2024) | ScienceDirect S0273117722010420; arXiv:2211.10189 | Modern efficient detection pipeline; increases event count vs official GOES list; energy/start/end/background params |
| B4 | HOPE technique - Hot Onset Precursor Event nowcasting | arXiv:2509.05234 (2025); Solar Physics 2026, DOI 10.1007/s11207-026-02705-2 | Alerts 5-15 min before peak using running-difference T/EM signatures; MLP for magnitude+time; direct competitor method to beat |
| B5 | Onboard detection of solar flare onset (2026) | DOI 10.1007/s11207-026-02645-x | Onboard-computable trigger; 69.5% detection @35% FP on 2587 >=C1.0 GOES flares; benchmark for O(1) onboard designs |
| B6 | VLF real-time flare detection (vlf4ions) | J. Space Weather Space Clim. 16:22 (2026), DOI 10.1051/swsc/2026019 | Independent ground-based detector; 82.7% M/X within quarter rise-time; useful as cross-check concept |
| B7 | CUSUM change-point detection tutorial | BMClab DetectCUSUM.ipynb (colab) | Reference implementation of one-sided upper CUSUM used in our soft_detector |

## C. Neupert Effect (Physics Engine)

| # | Paper | Source / Link | Why It Matters |
|---|-------|---------------|----------------|
| C1 | Neupert (1968) - original effect | Solar Physics 2:207 | F_SXR ~ integral of HXR; foundation of short-horizon forecasting |
| C2 | Li et al. (1997) - Soft versus Hard X-rays in Solar Flares | DOI 10.1086/304940 | Loop-model time histories; when Neupert holds/breaks |
| C3 | Veronig et al. (2002) - Investigation of the Neupert effect I | A&A 382:1070, DOI 10.1051/0004-6361:20020947 | Statistical properties + evaporation model; corr(HXR, dSXR/dt) methodology we implement |
| C4 | Su, Huang & Ning (2024) - Neupert Effect w/ HXI | DOI 10.1007/s11207-024-02299-7 | 149-event cross-correlation sample, 20-50 keV; modern stats baseline |
| C5 | Cristiani et al. (2026) - Neuppet Effect M/X Cycle 24 | DOI 10.1007/s11207-026-02643-z | Latest statistical analysis incl. microwave; deviations catalog |
| C6 | da Silva & Simoes (2020) - SXR Neupert proxy for SEP injection | JSWSC 10:64 | Physics-based forecasting model built directly on Neupert - validates our forecast framing |

## D. Forecasting / ML Models

| # | Paper | Source / Link | Why It Matters |
|---|-------|---------------|----------------|
| D1 | Advances and Challenges in Solar Flare Prediction: Review | arXiv:2511.20465 (2025) | THE survey: physics vs data-driven taxonomy, metrics table (TSS/HSS/BSS), operational platforms (DeepSun, DeepFlareNet, SolarFlareNet, MViT) |
| D2 | Landa & Reuveni (2022) - GOES-X-ray-only forecasting | (via review D1) | TSS~0.74 for >=M from X-ray flux alone - closest analog benchmark for our LightGBM |
| D3 | Jiao et al. (2020) - LSTM hybrid regression+classification | (via review D1) | SHARP-parameter time series -> peak intensity 24-48h ahead |
| D4 | Liu et al. (2019) - Attention-augmented LSTM | (via review D1) | Attention over 25 SHARP params + decayed flare history |
| D5 | Comparative ML for flare class prediction (RF/KNN/XGBoost) | github juliabringewald/Solar-Flare-Forecast; DOI 10.3390/astronomy4040023 | GBT-family wins on tabular; supports our LightGBM tier-1 choice |

## E. Open-Source Reference Implementations (Same Problem Statement)

| # | Repo | What To Take | What We Do Differently |
|---|------|--------------|------------------------|
| E1 | AsthaChandel123/bah2026-p15 (Aditya FlareCast) | O(1) primitives, Poisson-FOCuS idea, fusion math, ARCHITECTURE contract style | Same PS; ours emphasizes working tested code-first over edge deployment |
| E2 | Devansh865/solar-flare-detector | CUSUM+RF dashboard pattern, simulator-driven demo | We add Poisson statistics for HXR + warm-up gating (their version false-triggers at startup) |
| E3 | Vishwesh-Bhilare/solarflare-detection | SoLEXS/HEL1OS reader structure, parquet pipeline | We add LTT correction, fusion, Neupert engine, detectors |
| E4 | KrishnanandMorningstar/SolarShield-AI | Streamlit dashboard layout | We go FastAPI+SSE + React for real-time push |
| E5 | thecont1/aditya-L1-solar-explorer | Verified SoLEXS ZIP/FITS parsing pattern; Kaggle parquet dataset | We generalize to both instruments + QC flags |
| E6 | abhilash-sw/solexs_tools | Community SoLEXS utilities | Cross-check our reader column handling |
| E7 | DrustO9/aditya-l1-pradan-download | Bulk download scripts for PRADAN | Adopt directly for data acquisition step |
| E8 | msudh974/13th-AdityaL1-SCWorkshop HEL1OS notebook | HLSDemoNotebook.ipynb - official-style HEL1OS LC loading + band plotting | Validates our hel1os_reader extension names |

## F. Data Sources

| Source | URL | Auth | Use |
|--------|-----|------|-----|
| PRADAN Aditya-L1 | https://pradan1.issdc.gov.in/al1/ | free registration | SoLEXS+HEL1OS Level-1 FITS (primary) |
| NOAA SWPC GOES XRS JSON | https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json | none | Live anchor + labels |
| NOAA GOES flare events | https://services.swpc.noaa.gov/json/goes/primary/xray-flares-latest.json | none | Ground-truth catalogue cross-check |
| GOES XRS L2 science (1s) | https://data.ngdc.noaa.gov/platforms/space-weather/space-environment-monitoring-instruments/goes16/l2/data/xrsf-l2-*.nc | none | High-cadence training surrogate |
| HEK flare catalogue | via SunPy Fido a.hek | none | Label validation |
| Kaggle SoLEXS parquet | kaggle datasets maheshshantaram/isro-aditya-l1-solexs-lightcurve-fits | none | Quick-start soft-band data Jul2024-Mar2025 |
| AL1 Support Cell | https://al1ssc.aries.res.in | none | Tools, tutorials, updates |

---

### Priority Reading Order (for the team)
1. D1 (review) -> landscape in one paper
2. A1+A2 (instrument papers) -> data you actually hold
3. B4 (HOPE) -> the method to out-perform
4. C3+C4 (Neupert stats) -> your core feature physics
5. B1+B2 (detection classics) -> detector design grounding
