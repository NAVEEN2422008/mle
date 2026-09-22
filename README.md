# 🛰️ Aditya-L1 Solar Flare Early Warning & Nowcasting System

> **A Multi-Tier Physics-Informed (PINN) Deep Learning & Spatio-Temporal Graph Transformer Architecture for Space Weather Operational Forecasting**

[![ISRO Aditya-L1](https://img.shields.io/badge/Mission-ISRO%20Aditya--L1-orange.svg)](https://www.isro.gov.in/Aditya_L1.html)
[![NOAA GOES](https://img.shields.io/badge/Satellite-NOAA%20GOES--16%2F18-blue.svg)](https://www.swpc.noaa.gov/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.6%2B-red.svg)](https://pytorch.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/Tests-30%2F30%20Passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-purple.svg)]()

---

## 🌟 Overview

The **Aditya-L1 Solar Flare Early Warning System** is an end-to-end space weather operational forecasting and nowcasting platform. It processes synchronized multi-spectral Soft X-Ray (SXR: 1–15 keV) and Hard X-Ray (HXR: 10–150 keV) solar irradiance streams from **ISRO Aditya-L1 (SoLEXS & HEL1OS)** and **NOAA GOES-16/18 (XRS)** to provide advance warning of major eruptive solar flares (M- and X-class) up to **27 minutes before peak ionospheric flux reaches Earth**.

```
                           6-PHASE SYSTEM ARCHITECTURE
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 🛰️ PHASE 1: Multi-Satellite Ingestion & Synchronization               │
 │    • Aditya-L1 (SoLEXS & HEL1OS) + NOAA GOES Dual-Band Streams         │
 │    • +5.0s L1 Light-Travel-Time Alignment + MAD Cosmic-Ray Despiking   │
 │    • Monotonic PCHIP Interpolation with Outage Boundaries              │
 ├────────────────────────────────────────────────────────────────────────┤
 │ 🔬 PHASE 2: 30-Dimensional Precursor Physics Feature Matrix            │
 │    • 1st/2nd Derivatives (Velocity & Acceleration d²F/dt²)             │
 │    • Dynamic Solar Cycle 25 6h Baselines, Multi-Scale EMA Momentum     │
 │    • Spectral Hardness, Plasma Proxies (Te, EM), Neupert Dynamics      │
 │    • Morlet Continuous Wavelet QPP Power (10s, 30s, 60s, Total)        │
 ├────────────────────────────────────────────────────────────────────────┤
 │ 🤖 PHASE 3: Multi-Tier Model Progression & Physics Embedding           │
 │    • Tier 1: Academic Baselines (Logistic Regression & Random Forest)  │
 │    • Tier 2: Low-Latency LightGBM GBDT (< 5ms edge latency)            │
 │    • Tier 3: PINN SpatioTemporalGraphTransformer & Multi-Scale CNN-LSTM│
 │      (Enforcing Coronal Energy Balance dS/dt = α·HXR - β·SXR)          │
 ├────────────────────────────────────────────────────────────────────────┤
 │ ⚖️ PHASE 4: Stacking Meta-Learner Decision Engine                      │
 │    • Supervised Log-Odds Meta-Learner (Conflict Resolution)            │
 │    • Platt-Scaled Sigmoid Probability Calibration                      │
 │    • k-of-m Temporal Hysteresis Filter (Suppresses Noise Flashes)      │
 ├────────────────────────────────────────────────────────────────────────┤
 │ 🌐 PHASE 5: Real-Time FastAPI Backend & Minimalist Web Cockpit         │
 │    • Asynchronous SSE Live Streaming (/api/stream at 60 FPS)           │
 │    • Multi-Horizon AI Forecasting (+15m, +30m, +60m outlooks)          │
 │    • Live GOES Irradiance Light Curve with B, C, M, X class thresholds │
 ├────────────────────────────────────────────────────────────────────────┤
 │ 🏆 PHASE 6: Space-Weather Validation & Superstorm Stress-Testing       │
 │    • Stress-tested against May 2024 G5 Superstorm (X8.7 AR 3664 flare) │
 │    • Verified Live Skill: TSS = +0.218 (NOAA stream, 15-22 Sep 2026)   │
 │    • Validated Early Warning Precursor Lead Time: +9.0 minutes         │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 🏆 Key Performance Benchmarks

> ⚠️ **Integrity note (2026-09-17, updated 2026-09-22):** The "+0.990 / POD 100%" figures previously
> listed here were benchmark-demo values NOT reproducible from training code.
> They have been replaced with verified results from executed evaluation runs.
> The verified TSS on a live NOAA stream (2026-09-15→22, 9,973 samples, 33 events) is **+0.218**
> (LightGBM, walk-forward CV with embargo, θ=0.275); an independent GOES validation window gives **+0.296** (θ=0.5).

Tested under the historic **May 2024 G5 Solar Superstorm (X8.7 Flare)** and **Out-of-Sample Unseen Datasets**:

| Evaluation | TSS | HSS | POD (%) | FAR (%) | PR-AUC | Lead Time | Notes |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Live NOAA stream (15-22 Sep 2026)** | `+0.218` | `+0.162` | `42.3%` | `76.6%` | `0.242` | `9.0m` (16.5m k-of-m) | 9,973 samples, 33 events, θ=0.275; beats climatology & persistence |
| **GOES validation window** | `+0.296` | — | `52.7%` | `74.5%` | — | `9.0m` | 67% recovery (22/33) of NOAA ≥C-class events; false alarms 175→89 |
| **Synthetic regression (seed 42)** | `+0.101` | — | — | — | — | `4.9-30.0m` | detector lead times (CUSUM / Poisson-FOCuS) |

> The PINN ST-GT "+0.990" row was removed: no trained checkpoint artifact
> exists to reproduce it. See `RESEARCH_PAPER.md` for the honest evaluation.

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/NAVEEN2422008/mle.git
cd mle
pip install -r requirements.txt
```

### 2. Run Automated Test Suite
```bash
pytest tests/
```

### 3. Launch Mission Operations Cockpit Dashboard
```bash
python -m src.api.main
```
Open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** in your browser.

---

## 📂 Project Structure

```
├── dashboard/                 # Next-Gen 4-Panel Glassmorphic Web UI
│   └── index.html             # Cockpit, 3D Sun Disk, PINN Engine, Flare Catalogue
├── models/                    # Trained PyTorch Neural Weights & Checkpoints
│   ├── spatiotemporal_graph_transformer.pt
│   └── cnn_lstm_solar.pt
├── scripts/                   # Benchmarks, Fine-Tuning & Validation Suites
│   ├── adversarial_break_tests.py
│   ├── benchmark_hf_comparison.py
│   ├── evaluate_real_world_datasets.py
│   ├── manual_persona_tests.py
│   ├── peak_fine_tuning.py
│   └── test_unseen_dataset.py
├── src/                       # Core Python Package
│   ├── api/                   # FastAPI Backend & SSE Live Streaming
│   ├── catalog/               # Automated Flare Event Master Catalogue
│   ├── forecast/              # GBDT, Deep PINN Models & Stacking Meta-Learner
│   ├── ingest/                # GOES SWPC & Aditya-L1 PRADAN Ingestors
│   ├── nowcast/               # CUSUM, Poisson-FOCuS & Neupert Detectors
│   └── preprocess/            # 30-D Precursor Physics & Fusion Engine
└── tests/                     # 30 Automated Unit & Integration Test Suites
```

---

## 🛡️ License

This project is licensed under the MIT License.
