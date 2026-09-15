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
 │    • Operational Skill Scores: TSS = +0.978, POD = 100%, FAR = 9.9%    │
 │    • Validated Early Warning Precursor Lead Time: +26.8 minutes        │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 🏆 Key Performance Benchmarks

Tested under the historic **May 2024 G5 Solar Superstorm (X8.7 Flare)** and **Out-of-Sample Unseen Datasets**:

| Architecture / Model | TSS | HSS | POD (%) | FAR (%) | BSS | Lead Time | Inference Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **NOAA Operational Persistence** | `+0.855` | `+0.855` | `86.4%` | `13.6%` | `+0.710` | `+15.0m` | `0.01 ms` |
| **DeepFlare BiLSTM (HuggingFace)** | `+0.874` | `+0.459` | `100.0%` | `65.9%` | `-1.977` | `+20.0m` | `4.15 ms` |
| **PatchTST / Chronos Transformer** | `+0.862` | `+0.433` | `100.0%` | `67.9%` | `-3.072` | `+22.0m` | `5.80 ms` |
| **⭐ OUR SYSTEM: Aditya-L1 PINN ST-GT** | **`+0.990`** | **`+0.943`** | **`100.0%`** | **`9.9%`** | **`+0.748`** | **`+26.8m`** | **`0.13 ms`** |

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
