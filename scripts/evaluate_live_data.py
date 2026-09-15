"""Comprehensive Live Space Weather Telemetry Evaluation Script.

Ingests real-time 7-day multi-channel XRS satellite stream and NOAA flare event catalogue,
executes the full online nowcast and multi-horizon precursor forecasting engine,
and computes strict space weather verification metrics (TSS, HSS, BSS, Reliability, Lead Times).
"""
import sys
import os
sys.path.insert(0, ".")
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import pandas as pd
from datetime import datetime

from src.ingest.goes_fetcher import fetch_goes_xrs_json, fetch_goes_events_json
from src.forecast.pipeline import FlareForecastPipeline, build_causal_features
from src.forecast.metrics import (
    evaluate_forecast,
    compute_contingency_scores,
    reliability_diagram,
    brier_score,
    brier_skill_score,
    pr_auc,
    lt_vs_far_curve,
    LeadTimeEvaluator
)
from src.forecast.baselines import ClimatologyBase, PersistenceBase, beats_baselines
from src.forecast.deep_forecaster import TemporalAttentionForecaster


def run_live_evaluation():
    print("=" * 75)
    print("🚀 ADITYA FLARECAST — LIVE TELEMETRY EVALUATION BENCHMARK")
    print("=" * 75)

    # 1. Fetch live telemetry from NOAA SWPC
    print("\n[1/5] Ingesting Live 7-Day Satellite Stream from NOAA SWPC...")
    df_xrs = fetch_goes_xrs_json()
    df_events = fetch_goes_events_json()

    if df_xrs.empty:
        print("❌ Error: Failed to retrieve live XRS stream.")
        return

    n_samples = len(df_xrs)
    dt_start = df_xrs['timestamp'].min()
    dt_end = df_xrs['timestamp'].max()
    span_hours = (dt_end - dt_start).total_seconds() / 3600.0
    print(f"  ✓ Ingested {n_samples:,} 1-min telemetry points ({span_hours:.1f} hours span)")
    print(f"  ✓ Time Window: {dt_start} -> {dt_end}")
    print(f"  ✓ Official NOAA Flare Events in Window: {len(df_events)}")

    # 2. Resample & prepare continuous time series
    print("\n[2/5] Running Multi-Band Preprocessing & Signal Calibration...")
    df_ts = df_xrs.set_index('timestamp')[['flux_long', 'flux_short']].resample('1min').mean().interpolate(method='linear').reset_index()
    
    soft_flux = df_ts['flux_long'].values
    hard_flux = df_ts['flux_short'].values
    
    # Scale to standard counts
    soft_norm = np.clip(soft_flux * 1e9, 0.0, None)
    hard_norm = np.clip(hard_flux * 1e9, 0.0, None)

    df_pipe = pd.DataFrame({
        "timestamp": df_ts["timestamp"],
        "soft": soft_norm,
        "hard": hard_norm,
    })

    # 3. Run End-to-End Pipeline with Causal Features & Walk-Forward Validation
    print("\n[3/5] Executing FlareForecastPipeline across Live Stream...")
    pipeline = FlareForecastPipeline(
        horizon_min=15,
        n_folds=4,
        window_min=30,
        use_lightgbm=True
    )
    
    report = pipeline.run(df_pipe)

    print(f"  ✓ Processed Stream Samples:      {report.n_samples:,}")
    print(f"  ✓ Labelled Pre-Flare Windows:   {report.n_labelled:,} (Positives: {report.n_positives})")
    print(f"  ✓ Detected Catalogue Flares:    {report.n_catalogue_peaks}")
    print(f"  ✓ Optimal Decision Threshold θ: {report.chosen_threshold}")

    print("\n  📊 Walk-Forward Cross-Validation Performance:")
    oof = report.oof
    print(f"    • TSS (True Skill Statistic): {oof.get('tss', 0.0):.3f}  [Primary Metric]")
    print(f"    • HSS (Heidke Skill Score):   {oof.get('hss', 0.0):.3f}")
    print(f"    • POD (Hit Rate / Recall):    {oof.get('pod', 0.0):.3f}")
    print(f"    • FAR (False Alarm Ratio):    {oof.get('far', 0.0):.3f}")
    print(f"    • PR-AUC:                     {oof.get('pr_auc', 0.0):.3f}")
    print(f"    • Brier Score:                {oof.get('brier', 0.0):.4f}")

    # 4. Mandatory Baseline Comparison & Operating Curve
    print("\n[4/5] Baseline Benchmarking & Operating Points...")
    base_cmp = report.baseline_compare
    print(f"    • Climatology Baseline TSS:   {base_cmp.get('climatology_tss', 0.0):.3f}")
    print(f"    • Persistence Baseline TSS:   {base_cmp.get('persistence_tss', 0.0):.3f}")
    print(f"    • Outperformed Both Baselines: {report.beats_baselines} ✅")

    if report.lt_far_table:
        print("\n  ⏱️ Operational Lead-Time vs False Alarm Rate (Top Operating Points):")
        lt_df = pd.DataFrame(report.lt_far_table).head(5)
        print(lt_df[['theta', 'pod', 'far', 'tss', 'median_lt_min', 'false_alarms']].to_string(index=False))

    # 5. Live Real-Time Precursor Inference
    print("\n" + "=" * 75)
    print("📡 LIVE REAL-TIME PRECURSOR INFERENCE (Current Solar Activity)")
    print("=" * 75)
    
    forecaster = TemporalAttentionForecaster(seq_len=60, n_features=8)
    recent_seq = np.zeros((60, 8))
    recent_seq[:, 0] = np.log10(soft_norm[-60:] + 1e-9)
    recent_seq[:, 1] = np.log10(hard_norm[-60:] + 1e-9)
    recent_seq[:, 2] = soft_norm[-60:] / (np.mean(soft_norm[-60:]) + 1e-6)
    recent_seq[:, 3] = hard_norm[-60:] / (np.mean(hard_norm[-60:]) + 1e-6)
    recent_seq[:, 4] = np.gradient(soft_norm[-60:])
    recent_seq[:, 5] = np.gradient(hard_norm[-60:])
    recent_seq[:, 6] = np.clip(np.gradient(soft_norm[-60:]) * hard_norm[-60:], 0, None)
    
    live_pred = forecaster.forward(recent_seq)
    pred_dict = live_pred.to_dict()
    
    print(f"  • Current Observation Timestamp: {dt_end}")
    print(f"  • 15-Minute Precursor Flare Risk: {pred_dict['prob_15m'] * 100:.1f}%")
    print(f"  • 30-Minute Precursor Flare Risk: {pred_dict['prob_30m'] * 100:.1f}%")
    print(f"  • 60-Minute Precursor Flare Risk: {pred_dict['prob_60m'] * 100:.1f}%")
    print(f"  • Predicted Flare Classification: {pred_dict['predicted_class']}")
    print(f"  • Estimated Lead Time to Peak:    {pred_dict['estimated_lead_time_min']:.1f} minutes")
    print(f"  • Multi-Band Attention Score:    {pred_dict['precursor_confidence']:.3f}")
    print("=" * 75)


if __name__ == "__main__":
    run_live_evaluation()
