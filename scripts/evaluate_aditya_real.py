"""Evaluate the ML pipeline on REAL Aditya-L1 SoLEXS+HEL1OS data with NOAA labels.

This replaces the GOES-only evaluation with genuine simultaneous SXR+HXR data.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
from datetime import datetime, timezone

from src.ingest.aditya_l1 import build_aditya_pipeline_df
from src.ingest.goes_fetcher import fetch_goes_events_json
from src.forecast.pipeline import FlareForecastPipeline
from src.forecast.metrics import (
    evaluate_forecast,
    compute_contingency_scores,
    reliability_diagram,
    brier_score,
    brier_skill_score,
    pr_auc,
    lt_vs_far_curve,
)


def run_aditya_evaluation():
    print("=" * 75)
    print("ADITYA-L1 REAL DATA EVALUATION - SoLEXS + HEL1OS (CZT 40-60 keV)")
    print("=" * 75)

    # 1. Build aligned Aditya-L1 dataset
    print("\n[1/5] Building aligned Aditya-L1 dataset from PRADAN archives...")
    df_aditya = build_aditya_pipeline_df("data/raw", target_band="40-60 keV", resample_min=1)

    if df_aditya.empty:
        print("  No data available.")
        return

    n_samples = len(df_aditya)
    dt_start = df_aditya['timestamp'].min()
    dt_end = df_aditya['timestamp'].max()
    span_hours = (dt_end - dt_start).total_seconds() / 3600.0
    print(f"  Ingested {n_samples:,} 1-min telemetry points ({span_hours:.1f} hours span)")
    print(f"  Time Window: {dt_start} -> {dt_end}")
    print(f"  Dates covered: {sorted(df_aditya['date'].unique())}")

    # 2. Load NOAA events from local catalogue (historical X-class)
    print("\n[2/5] Loading NOAA X-class flare catalogue...")
    labels_path = "data/noaa_xclass_labels.csv"
    if os.path.exists(labels_path):
        df_events = pd.read_csv(labels_path, comment='#',
                                names=["peak_time", "peak_flux", "class_type", "source"])
        df_events["peak_time"] = pd.to_datetime(df_events["peak_time"], utc=True)
        df_events["peak_flux"] = pd.to_numeric(df_events["peak_flux"], errors="coerce")
        # Filter to our time window
        _t0 = df_aditya["timestamp"].iloc[0]
        _t1 = df_aditya["timestamp"].iloc[-1]
        if _t0.tz is None:
            _t0 = _t0.tz_localize("UTC")
        if _t1.tz is None:
            _t1 = _t1.tz_localize("UTC")
        df_events = df_events[
            (df_events["peak_time"] >= _t0) &
            (df_events["peak_time"] <= _t1)
        ].copy()
        print(f"  NOAA X-class events in window: {len(df_events)}")
        for _, ev in df_events.iterrows():
            print(f"    {ev['peak_time']}  {ev['class_type']}  flux={ev['peak_flux']:.1e} W/m^2")
    else:
        print(f"  Warning: {labels_path} not found.")
        df_events = pd.DataFrame()

    # 3. Prepare pipeline input
    print("\n[3/5] Preparing pipeline input...")
    df_pipe = df_aditya[["timestamp", "soft", "hard"]].copy()
    print(f"  soft (SoLEXS SDD2 2-22 keV): median={df_pipe['soft'].median():.1f} cts/s")
    print(f"  hard (HEL1OS CZT 40-60 keV): median={df_pipe['hard'].median():.4f} cts/s")

    # 4. Build NOAA ground-truth labels
    print("\n[4/5] Building NOAA ground-truth labels...")
    if not df_events.empty:
        _ev = df_events.copy()
        _ev["peak_time"] = pd.to_datetime(_ev["peak_time"], utc=True)
        _tf = pd.to_numeric(_ev["peak_flux"], errors="coerce").fillna(0.0).to_numpy()
        _tp = _ev["peak_time"].array.view('int64') // 10**6
        C1_WM2 = 1e-6
        label_peaks = [(float(t), float(f) * 1e9)
                       for t, f in zip(_tp, _tf) if f >= C1_WM2]
        n_all_ev = len(_tp)
        print(f"  NOAA events in window: {n_all_ev}; >=C1.0 used as labels: {len(label_peaks)}")
        for t, f in label_peaks:
            print(f"    t={t} ({datetime.fromtimestamp(t, tz=timezone.utc)})  flux={f:.1f} nW/m^2")
    else:
        label_peaks = []
        print("  No NOAA events - running unsupervised feature check only.")
    print("\n[5/5] Running FlareForecastPipeline with walk-forward CV...")
    pipeline = FlareForecastPipeline(
        horizon_min=15,
        n_folds=4,
        window_min=30,
        min_class_flux=1000.0,   # nW/m^2
        use_lightgbm=True
    )

    # Pipeline expects timestamp column parseable by pd.to_datetime -> nanoseconds.
    # Our df_pipe['timestamp'] is datetime64[s, UTC]; convert to datetime64[ns, UTC].
    df_pipe_for_pipeline = df_pipe.copy()
    df_pipe_for_pipeline["timestamp"] = df_pipe_for_pipeline["timestamp"].astype("datetime64[ns, UTC]")

    if label_peaks:
        report = pipeline.run(df_pipe_for_pipeline, truth_peaks=label_peaks, label_peaks=label_peaks)
        oof = report.oof

        # pipeline.run sets rep.oof to the FIXED pre-registered threshold result
        # and rep.baseline_compare["model"] to the median fold-tuned result.
        # The previous code looked for oof["model"], which never exists, so the
        # detailed block below was dead and only the bare dict was printed.
        fixed = oof if isinstance(oof, dict) else {}
        tuned = {}
        bc = getattr(report, "baseline_compare", None) or {}
        if isinstance(bc.get("model"), dict):
            tuned = bc["model"]

        if fixed.get("tss") is None and not tuned:
            print(f"\n  No OOF metrics produced. Pipeline report: {oof}")
        else:
            print("\n" + "=" * 75)
            print("WALK-FORWARD CROSS-VALIDATION RESULTS (Real Aditya-L1 Data)")
            print("=" * 75)
            fmt = [
                ("tss", "TSS (True Skill Statistic)"),
                ("hss", "HSS (Heidke Skill Score)"),
                ("pod", "POD (Probability of Detection)"),
                ("far", "FAR (False Alarm Ratio)"),
                ("pr_auc", "PR-AUC"),
                ("brier", "Brier Score"),
                ("bss", "Brier Skill Score vs Climatology"),
            ]
            for key, label in fmt:
                v = fixed.get(key, tuned.get(key))
                print(f"  {label:<38} {v:>9.4f}" if v is not None
                      else f"  {label:<38} {'N/A':>9}")
            print(f"  {'Threshold (fixed, pre-registered)':<38} "
                  f"{fixed.get('threshold', float('nan')):>9.4f}")
            print(f"  {'Threshold (median fold-tuned)':<38} "
                  f"{report.chosen_threshold:>9.4f}")

            # Baseline comparison
            print("\n  Baseline Benchmarking:")
            print(f"    Model TSS @ fixed theta      {fixed.get('tss', float('nan')):.4f}")
            for name in ("climatology", "persistence"):
                d = bc.get(name)
                if isinstance(d, dict):
                    print(f"    {name.capitalize():<23} TSS {d.get('tss', float('nan')):.4f}"
                          f"  POD {d.get('pod', float('nan')):.4f}"
                          f"  FAR {d.get('far', float('nan')):.4f}")
            print("    NOTE: both baselines score 0 because at this threshold they never")
            print("          predict a positive class, so 'beats_baselines' is vacuous.")

            # Lead-time vs FAR
            if getattr(report, "lt_far_table", None):
                rows = report.lt_far_table
                pods = {r["pod"] for r in rows}
                fars = {r["far"] for r in rows}
                if pods == {0.0} and fars == {1.0}:
                    print("\n  Lead-Time vs FAR: DEGENERATE - POD=0 and FAR=1 at every")
                    print("    threshold, so no lead-time curve can be derived. Not reported.")
                else:
                    print("\n  Lead-Time vs FAR (Top Operating Points):")
                    for row in rows[:5]:
                        print(f"    theta={row['theta']:.2f}  POD={row['pod']:.3f}  "
                              f"FAR={row['far']:.3f}  TSS={row['tss']:.3f}  "
                              f"median_lt={row['median_lt_min']:.1f}min  "
                              f"false_alarms={row['false_alarms']}")

            if bc.get("oof_coverage_frac") is not None:
                print(f"\n  OOF Coverage:                   {bc['oof_coverage_frac']:.2%}")
            print(f"  Beats Both Baselines (vacuous):  {report.beats_baselines}")

    else:
        print("  Skipping supervised evaluation (no NOAA labels).")

    print("\n" + "=" * 75)
    print("Provenance: this evaluation uses REAL Aditya-L1 SoLEXS (2-22 keV) +")
    print("HEL1OS CZT 40-60 keV Level-1 data. The 'hard' channel is genuine HXR above")
    print("the SoLEXS ceiling, not a GOES soft-band proxy.")
    print("TSS here is the Peirce score, POD - POFD, which is algebraically")
    print("identical to the Hanssen-Kuipers discriminant (a*d-b*c)/((a+c)(b+d))")
    print("used by Bloomfield et al. 2012, so these values ARE comparable to")
    print("that convention. Note some papers loosely call HTR-FAR 'TSS'; those")
    print("are NOT comparable. Either way this model is far below the 24-h")
    print("optima in that work (0.46 for >=C1.0, 0.74 for X-class).")
    print("=" * 75)


if __name__ == "__main__":
    run_aditya_evaluation()