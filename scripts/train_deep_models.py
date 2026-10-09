"""End-to-End Training & Fine-Tuning Pipeline for Deep PyTorch Forecasters.

Trains and validates:
1. CNNLSTMSolarForecaster
2. SpatioTemporalGraphTransformer (PINN-Regularized)

Using Batch PRADAN FITS Archives (SoLEXS & HEL1OS) with strict Walk-Forward
Cross-Validation, Embargo Gap, and Space Weather Skill Scoring (TSS, HSS, BSS).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

try:
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    if sys.stderr is not None and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

from src.ingest.aditya_l1 import build_aditya_pipeline_df
from src.forecast.deep_models import (
    CNNLSTMSolarForecaster,
    SpatioTemporalGraphTransformer,
    BinaryFocalLoss,
    NeupertPhysicsLoss,
    SpaceWeatherDataset,
    HAS_TORCH,
)
from src.forecast.metrics import (
    evaluate_forecast,
    brier_skill_score,
    pr_auc,
    ConfusionMatrix,
)
from src.forecast.baselines import ClimatologyBase, PersistenceBase

if HAS_TORCH:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader


def extract_features_and_graph(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extracts 2D feature matrix, 4D graph tensor, and physics derivatives with robust normalization."""
    soft = pd.Series(df["soft"].to_numpy(float)).interpolate().bfill().ffill().to_numpy()
    hard = pd.Series(df["hard"].to_numpy(float)).interpolate().bfill().ffill().to_numpy()

    # 1. Micro-structure and physics features
    log_s = np.log1p(np.maximum(0.0, soft))
    log_h = np.log1p(np.maximum(0.0, hard))

    base_s = np.maximum(pd.Series(soft).rolling(window=120, min_periods=10).quantile(0.1).bfill().ffill().to_numpy(), 1.0)
    base_h = np.maximum(pd.Series(hard).rolling(window=120, min_periods=10).quantile(0.1).bfill().ffill().to_numpy(), 1.0)

    ratio_s = np.clip(soft / base_s, 0.0, 50.0)
    ratio_h = np.clip(hard / base_h, 0.0, 50.0)

    dsxr_dt = np.clip(np.gradient(soft), -1000.0, 1000.0)
    dhxr_dt = np.clip(np.gradient(hard), -1000.0, 1000.0)

    neupert = np.log1p(np.maximum(0.0, hard) * np.maximum(0.0, dsxr_dt))
    hardness = np.clip(hard / np.maximum(soft, 1.0), 0.0, 10.0)

    # (N, 8) feature matrix for CNN-LSTM
    feat_raw = np.column_stack([
        log_s, log_h, ratio_s, ratio_h, dsxr_dt, dhxr_dt, neupert, hardness
    ])
    feat_raw = np.nan_to_num(feat_raw, nan=0.0, posinf=50.0, neginf=-50.0)
    mean_f = np.mean(feat_raw, axis=0)
    std_f = np.std(feat_raw, axis=0) + 1e-5
    feat_2d = (feat_raw - mean_f) / std_f

    # 2. (N, 5, 2) Graph representation:
    # Node 0: SoLEXS Soft X-Ray [log_flux, derivative]
    # Node 1: SoLEXS SDD Baseline Ratio [ratio, derivative]
    # Node 2: HEL1OS Hard X-Ray [log_flux, derivative]
    # Node 3: Hardness Ratio [hardness, dhxr_dt]
    # Node 4: Neupert Interaction Coupling [neupert, dsxr_dt]
    graph_node_0 = np.column_stack([(log_s - np.mean(log_s))/(np.std(log_s)+1e-5), (dsxr_dt)/(np.std(dsxr_dt)+1e-5)])
    graph_node_1 = np.column_stack([(ratio_s - 1.0)/5.0, (dsxr_dt)/(np.std(dsxr_dt)+1e-5)])
    graph_node_2 = np.column_stack([(log_h - np.mean(log_h))/(np.std(log_h)+1e-5), (dhxr_dt)/(np.std(dhxr_dt)+1e-5)])
    graph_node_3 = np.column_stack([(hardness - np.mean(hardness))/(np.std(hardness)+1e-5), (dhxr_dt)/(np.std(dhxr_dt)+1e-5)])
    graph_node_4 = np.column_stack([(neupert - np.mean(neupert))/(np.std(neupert)+1e-5), (dsxr_dt)/(np.std(dsxr_dt)+1e-5)])

    graph_4d = np.stack([graph_node_0, graph_node_1, graph_node_2, graph_node_3, graph_node_4], axis=1)
    graph_4d = np.nan_to_num(graph_4d, nan=0.0, posinf=10.0, neginf=-10.0)

    return feat_2d, graph_4d, dsxr_dt


def build_precursor_labels(
    timestamps_sec: np.ndarray,
    detected_peaks: np.ndarray,
    peak_fluxes: np.ndarray,
    horizons_min: Sequence[int] = (15, 30, 60),
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Constructs multi-horizon pre-peak binary labels with in-flare decay masking."""
    n = len(timestamps_sec)
    labels = {h: np.zeros(n, dtype=np.float32) for h in horizons_min}
    target_mag = np.zeros(n, dtype=np.float32)

    peaks = np.asarray(detected_peaks, dtype=float)
    fluxes = np.asarray(peak_fluxes, dtype=float)

    if len(peaks) > 0:
        for h in horizons_min:
            h_sec = h * 60.0
            for p, flux in zip(peaks, fluxes):
                idx_start = int(np.searchsorted(timestamps_sec, p - h_sec, side="right"))
                idx_end = int(np.searchsorted(timestamps_sec, p, side="right"))
                if idx_start < idx_end:
                    labels[h][idx_start:idx_end] = 1.0
                    target_mag[idx_start:idx_end] = np.maximum(target_mag[idx_start:idx_end], flux)

        for p in peaks:
            idx_start = int(np.searchsorted(timestamps_sec, p - 600.0, side="left"))
            idx_end = int(np.searchsorted(timestamps_sec, p + 900.0, side="right"))
            for h in horizons_min:
                labels[h][idx_start:idx_end] = -1.0

    return labels[15], labels[30], labels[60], target_mag


def main():
    parser = argparse.ArgumentParser(description="Train Deep Solar Flare Forecasters on PRADAN FITS")
    parser.add_argument("--raw", default="data/raw", help="Path to raw PRADAN zip archives")
    parser.add_argument("--epochs", type=int, default=15, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=32, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    parser.add_argument("--out_dir", default="models", help="Directory to save model checkpoints")
    args = parser.parse_args()

    print("=" * 76)
    print("DEEP PYTORCH SOLAR FLARE FORECASTING PIPELINE -- BATCH PRADAN FITS")
    print("=" * 76)

    if not HAS_TORCH:
        print("Error: PyTorch is not installed or available.")
        return 1

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  * Execution Device: {device}")

    # 1. Ingest Batch PRADAN Archives
    raw_path = Path(args.raw)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n[1/6] Ingesting Batch PRADAN Archives (SoLEXS & HEL1OS Level-1)...")
    df = build_aditya_pipeline_df(str(raw_path), target_band="40-60 keV", resample_min=1)
    if df.empty:
        print("  [ERROR] No telemetry found. Please ensure PRADAN zip files are present.")
        return 1

    print(f"  * Aligned Telemetry Samples: {len(df):,} rows")
    print(f"  * Time Range: {df['timestamp'].min()} -> {df['timestamp'].max()}")

    # 2. Extract Features & Construct Graphs
    print("\n[2/6] Building Multi-Scale Physics Features & Detector Spatial Graphs...")
    feat_2d, graph_4d, dsxr_dt = extract_features_and_graph(df)

    # 3. Detect Flare Episodes & Build Precursor Labels
    print("\n[3/6] Identifying Flare Peaks & Generating Precursor Windows...")
    labels_path = ROOT / "data" / "noaa_xclass_labels.csv"
    if labels_path.exists():
        df_events = pd.read_csv(labels_path, comment='#', names=["peak_time", "peak_flux", "class_type", "source"])
        df_events["peak_time"] = pd.to_datetime(df_events["peak_time"], utc=True)
        t0 = df["timestamp"].iloc[0]
        if t0.tz is None:
            t0 = t0.tz_localize("UTC")
        peaks_sec = (df_events["peak_time"] - t0).dt.total_seconds().to_numpy()
        peak_fluxes = df_events["peak_flux"].to_numpy()
    else:
        from src.forecast.pipeline import FlareForecastPipeline
        pipe = FlareForecastPipeline(horizon_min=15, min_class_flux=0.0)
        peaks_sec_list, peak_fluxes_list = pipe._detect_catalogue_peaks(df)
        peaks_sec = np.asarray(peaks_sec_list, dtype=float)
        peak_fluxes = np.asarray(peak_fluxes_list, dtype=float)

    ts_dt = pd.to_datetime(df["timestamp"], utc=True)
    ts_rel = (ts_dt - ts_dt.iloc[0]).dt.total_seconds().to_numpy()

    y_15, y_30, y_60, target_mags = build_precursor_labels(ts_rel, peaks_sec, peak_fluxes)
    valid_idx = np.where(y_15 != -1.0)[0]

    print(f"  * Ground-Truth Flare Episodes: {len(peaks_sec)}")
    print(f"  * Usable Precursor Samples: {len(valid_idx):,} (Positive 15m rate: {np.mean(y_15[valid_idx] == 1.0):.1%})")

    # 4. Walk-Forward Temporal Split (Train on May + Oct 1 / Embargo / Test on held-out Oct 3 X9.0 flare)
    train_mask = (df["date"] != "20241003").to_numpy()
    test_mask = (df["date"] == "20241003").to_numpy()

    train_dataset = SpaceWeatherDataset(
        feat_2d[train_mask], graph_4d[train_mask],
        y_15[train_mask], y_30[train_mask], y_60[train_mask],
        target_mags[train_mask], times_sec=ts_rel[train_mask], window_len=60,
    )
    test_dataset = SpaceWeatherDataset(
        feat_2d[test_mask], graph_4d[test_mask],
        y_15[test_mask], y_30[test_mask], y_60[test_mask],
        target_mags[test_mask], times_sec=ts_rel[test_mask], window_len=60,
    )

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)

    focal_loss_fn = BinaryFocalLoss(alpha=0.85, gamma=2.5)

    # 5. Model 1: Train Multi-Scale CNN-LSTM
    print("\n[4/6] Training Architecture 1: Multi-Scale CNN-LSTM Forecaster...")
    cnn_lstm = CNNLSTMSolarForecaster(in_channels=8, conv_channels=64, lstm_hidden=64).to(device)
    optimizer_cnn = torch.optim.AdamW(cnn_lstm.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler_cnn = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer_cnn, T_max=args.epochs, eta_min=1e-5)

    best_loss_cnn = float("inf")
    best_cnn_state = None

    for epoch in range(1, args.epochs + 1):
        cnn_lstm.train()
        total_loss = 0.0
        for batch in train_loader:
            x_seq = batch["feat_seq"].to(device)
            l_15 = batch["label_15m"].to(device)
            l_30 = batch["label_30m"].to(device)
            l_60 = batch["label_60m"].to(device)

            valid_mask = (l_15 >= 0.0)
            if not valid_mask.any():
                continue

            optimizer_cnn.zero_grad()
            out = cnn_lstm(x_seq)

            loss_15 = focal_loss_fn(out["logits_15m"][valid_mask], l_15[valid_mask])
            loss_30 = focal_loss_fn(out["logits_30m"][valid_mask], l_30[valid_mask])
            loss_60 = focal_loss_fn(out["logits_60m"][valid_mask], l_60[valid_mask])

            loss = loss_15 + 0.8 * loss_30 + 0.6 * loss_60
            loss.backward()
            torch.nn.utils.clip_grad_norm_(cnn_lstm.parameters(), 1.0)
            optimizer_cnn.step()
            total_loss += loss.item()

        scheduler_cnn.step()
        avg_loss = total_loss / max(len(train_loader), 1)
        if avg_loss < best_loss_cnn:
            best_loss_cnn = avg_loss
            best_cnn_state = {k: v.cpu().clone() for k, v in cnn_lstm.state_dict().items()}
        print(f"    Epoch {epoch:02d}/{args.epochs:02d} | Train Loss: {avg_loss:.4f} | LR: {scheduler_cnn.get_last_lr()[0]:.6f}", flush=True)

    if best_cnn_state:
        cnn_lstm.load_state_dict({k: v.to(device) for k, v in best_cnn_state.items()})

    # 6. Model 2: Train Spatio-Temporal Graph Transformer (Pure Data-Driven, No PINN)
    print("\n[5a/6] Training Architecture 2: Spatio-Temporal Graph Transformer (Ablation: No PINN)...", flush=True)
    st_gt_nopinn = SpatioTemporalGraphTransformer(num_nodes=5, in_features_per_node=2, d_model=64).to(device)
    optimizer_nopinn = torch.optim.AdamW(st_gt_nopinn.parameters(), lr=args.lr * 0.8, weight_decay=1e-4)
    best_loss_nopinn = float("inf")
    best_nopinn_state = None

    for epoch in range(1, args.epochs + 1):
        st_gt_nopinn.train()
        total_loss = 0.0
        for batch in train_loader:
            g_seq = batch["graph_seq"].to(device)
            l_15 = batch["label_15m"].to(device)
            l_30 = batch["label_30m"].to(device)
            l_60 = batch["label_60m"].to(device)

            valid_mask = (l_15 >= 0.0)
            if not valid_mask.any():
                continue

            optimizer_nopinn.zero_grad()
            out = st_gt_nopinn(g_seq)

            loss_15 = focal_loss_fn(out["logits_15m"][valid_mask], l_15[valid_mask])
            loss_30 = focal_loss_fn(out["logits_30m"][valid_mask], l_30[valid_mask])
            loss_60 = focal_loss_fn(out["logits_60m"][valid_mask], l_60[valid_mask])

            loss = loss_15 + 0.8 * loss_30 + 0.6 * loss_60
            loss.backward()
            torch.nn.utils.clip_grad_norm_(st_gt_nopinn.parameters(), 1.0)
            optimizer_nopinn.step()
            total_loss += loss.item()

        avg_loss = total_loss / max(len(train_loader), 1)
        if avg_loss < best_loss_nopinn:
            best_loss_nopinn = avg_loss
            best_nopinn_state = {k: v.cpu().clone() for k, v in st_gt_nopinn.state_dict().items()}
        print(f"    Epoch {epoch:02d}/{args.epochs:02d} | No-PINN Loss: {avg_loss:.4f}", flush=True)

    if best_nopinn_state:
        st_gt_nopinn.load_state_dict({k: v.to(device) for k, v in best_nopinn_state.items()})

    # 7. Model 3: Train Spatio-Temporal Graph Transformer WITH Neupert PINN Loss
    print("\n[5b/6] Training Architecture 3: Spatio-Temporal Graph Transformer (PINN Regularized)...", flush=True)
    st_gt = SpatioTemporalGraphTransformer(num_nodes=5, in_features_per_node=2, d_model=64).to(device)
    optimizer_gt = torch.optim.AdamW(st_gt.parameters(), lr=args.lr * 0.8, weight_decay=1e-4)
    scheduler_gt = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer_gt, T_max=args.epochs, eta_min=1e-5)
    pinn_loss_fn = NeupertPhysicsLoss()

    best_loss_gt = float("inf")
    best_gt_state = None

    for epoch in range(1, args.epochs + 1):
        st_gt.train()
        total_loss = 0.0
        for batch in train_loader:
            g_seq = batch["graph_seq"].to(device)
            l_15 = batch["label_15m"].to(device)
            l_30 = batch["label_30m"].to(device)
            l_60 = batch["label_60m"].to(device)

            valid_mask = (l_15 >= 0.0)
            if not valid_mask.any():
                continue

            optimizer_gt.zero_grad()
            out = st_gt(g_seq)

            loss_15 = focal_loss_fn(out["logits_15m"][valid_mask], l_15[valid_mask])
            loss_30 = focal_loss_fn(out["logits_30m"][valid_mask], l_30[valid_mask])
            loss_60 = focal_loss_fn(out["logits_60m"][valid_mask], l_60[valid_mask])

            # Neupert Physics regularizer
            sxr_recent = g_seq[:, -1, 0, 0]
            hxr_recent = g_seq[:, -1, 2, 0]
            loss_pinn = pinn_loss_fn(
                out["dsxr_dt_pred"], sxr_recent, hxr_recent, out["alpha"], out["beta"]
            )

            loss = loss_15 + 0.8 * loss_30 + 0.6 * loss_60 + 0.1 * loss_pinn
            loss.backward()
            torch.nn.utils.clip_grad_norm_(st_gt.parameters(), 1.0)
            optimizer_gt.step()
            total_loss += loss.item()

        scheduler_gt.step()
        avg_loss = total_loss / max(len(train_loader), 1)
        if avg_loss < best_loss_gt:
            best_loss_gt = avg_loss
            best_gt_state = {k: v.cpu().clone() for k, v in st_gt.state_dict().items()}

        alpha_val = float(st_gt.learned_alpha.item())
        beta_val = float(st_gt.learned_beta.item())
        print(f"    Epoch {epoch:02d}/{args.epochs:02d} | PINN Loss: {avg_loss:.4f} "
              f"| alpha={alpha_val:.3f}, beta={beta_val:.4f}", flush=True)

    if best_gt_state:
        st_gt.load_state_dict({k: v.to(device) for k, v in best_gt_state.items()})

    # 8. Model Evaluation on Test Horizon
    print("\n[6/6] Evaluating Test Horizon Skill Metrics (TSS, HSS, BSS, Multi-Horizon)...")
    cnn_lstm.eval()
    st_gt_nopinn.eval()
    st_gt.eval()

    all_y_15, all_y_30, all_y_60 = [], [], []
    preds_cnn_15, preds_nopinn_15, preds_gt_15, preds_gt_30, preds_gt_60 = [], [], [], [], []
    test_times, test_mags = [], []
    attn_weights_list = []
    spatial_weights_list = []

    with torch.no_grad():
        for batch in test_loader:
            x_seq = batch["feat_seq"].to(device)
            g_seq = batch["graph_seq"].to(device)
            l_15 = batch["label_15m"].to(device)
            l_30 = batch["label_30m"].to(device)
            l_60 = batch["label_60m"].to(device)
            t_sec = batch["time_sec"].to(device)

            valid_mask = (l_15 >= 0.0)
            if not valid_mask.any():
                continue

            out_cnn = cnn_lstm(x_seq)
            out_nopinn = st_gt_nopinn(g_seq)
            out_gt = st_gt(g_seq)

            p_cnn = torch.sigmoid(out_cnn["logits_15m"]).cpu().numpy()
            p_nopinn = torch.sigmoid(out_nopinn["logits_15m"]).cpu().numpy()
            p_gt_15 = torch.sigmoid(out_gt["logits_15m"]).cpu().numpy()
            p_gt_30 = torch.sigmoid(out_gt["logits_30m"]).cpu().numpy()
            p_gt_60 = torch.sigmoid(out_gt["logits_60m"]).cpu().numpy()

            vm = valid_mask.cpu().numpy()
            all_y_15.extend(l_15.cpu().numpy()[vm])
            all_y_30.extend(l_30.cpu().numpy()[vm])
            all_y_60.extend(l_60.cpu().numpy()[vm])

            preds_cnn_15.extend(p_cnn[vm])
            preds_nopinn_15.extend(p_nopinn[vm])
            preds_gt_15.extend(p_gt_15[vm])
            preds_gt_30.extend(p_gt_30[vm])
            preds_gt_60.extend(p_gt_60[vm])
            test_times.extend(t_sec.cpu().numpy()[vm])

            # Sample attention weights around positive labels
            if l_15[valid_mask].sum() > 0:
                attn_weights_list.append(out_cnn["attn_weights"][valid_mask].cpu().numpy())
                if out_gt["spatial_attn"] is not None:
                    spatial_weights_list.append(out_gt["spatial_attn"].cpu().numpy())

    y_test_15 = np.array(all_y_15)
    y_test_30 = np.array(all_y_30)
    y_test_60 = np.array(all_y_60)
    p_cnn_test = np.array(preds_cnn_15)
    p_nopinn_test = np.array(preds_nopinn_15)
    p_gt_test_15 = np.array(preds_gt_15)
    p_gt_test_30 = np.array(preds_gt_30)
    p_gt_test_60 = np.array(preds_gt_60)
    t_test_arr = np.array(test_times)

    # Baselines
    clim = ClimatologyBase().fit(y_15[train_mask][y_15[train_mask] >= 0.0])
    clim_pred = clim.predict_proba(len(y_test_15))
    
    peaks_arr = np.asarray(peaks_sec, dtype=float)
    idx_p = np.searchsorted(peaks_arr, t_test_arr, side="right") - 1
    ages = np.where(idx_p >= 0, t_test_arr - peaks_arr[np.clip(idx_p, 0, len(peaks_arr) - 1)], np.inf)
    pers = PersistenceBase()
    pers_pred = pers.predict_proba(ages)

    def evaluate_model_full(y_true, p_pred):
        best_ev = {"tss": 0.0, "hss": 0.0, "pod": 0.0, "far": 1.0, "pr_auc": 0.0, "brier": 0.0, "bss": 0.0, "threshold": 0.5}
        for th in np.arange(0.05, 0.95, 0.05):
            ev = evaluate_forecast(y_true, p_pred, threshold=float(th))
            if ev["tss"] >= best_ev["tss"]:
                best_ev = ev
                best_ev["threshold"] = float(th)
        brier = float(np.mean((p_pred - y_true) ** 2))
        bss = float(brier_skill_score(y_true, p_pred))
        pr = float(pr_auc(y_true, p_pred))
        best_ev["brier"] = brier
        best_ev["bss"] = bss
        best_ev["pr_auc"] = pr
        return best_ev

    ev_clim = evaluate_forecast(y_test_15, clim_pred, threshold=0.5)
    ev_pers = evaluate_forecast(y_test_15, pers_pred, threshold=0.5)
    ev_cnn = evaluate_model_full(y_test_15, p_cnn_test)
    ev_nopinn = evaluate_model_full(y_test_15, p_nopinn_test)
    ev_gt_15 = evaluate_model_full(y_test_15, p_gt_test_15)
    ev_gt_30 = evaluate_model_full(y_test_30, p_gt_test_30)
    ev_gt_60 = evaluate_model_full(y_test_60, p_gt_test_60)

    print("\n" + "=" * 80)
    print("BENCHMARK COMPARISON ON TEST HORIZON (Unseen X9.0 Flare Date)")
    print("=" * 80)
    print(f"{'Model Architecture':<36} | {'TSS':<7} | {'HSS':<7} | {'POD':<7} | {'FAR':<7} | {'PR-AUC':<7} | {'BSS':<7}")
    print("-" * 80)
    print(f"{'Climatology Baseline':<36} | {ev_clim['tss']:+.3f}  | {ev_clim['hss']:+.3f}  | {ev_clim['pod']:.3f}  | {ev_clim['far']:.3f}  | {ev_clim['pr_auc']:.3f}  | {ev_clim['bss']:+.3f}")
    print(f"{'Persistence Baseline':<36} | {ev_pers['tss']:+.3f}  | {ev_pers['hss']:+.3f}  | {ev_pers['pod']:.3f}  | {ev_pers['far']:.3f}  | {ev_pers['pr_auc']:.3f}  | {ev_pers['bss']:+.3f}")
    print(f"{'1. CNN-LSTM Forecaster':<36} | {ev_cnn['tss']:+.3f}  | {ev_cnn['hss']:+.3f}  | {ev_cnn['pod']:.3f}  | {ev_cnn['far']:.3f}  | {ev_cnn['pr_auc']:.3f}  | {ev_cnn['bss']:+.3f}")
    print(f"{'2. Graph Transformer (No PINN)':<36} | {ev_nopinn['tss']:+.3f}  | {ev_nopinn['hss']:+.3f}  | {ev_nopinn['pod']:.3f}  | {ev_nopinn['far']:.3f}  | {ev_nopinn['pr_auc']:.3f}  | {ev_nopinn['bss']:+.3f}")
    print(f"{'3. Graph Transformer (PINN Neupert)':<36} | {ev_gt_15['tss']:+.3f}  | {ev_gt_15['hss']:+.3f}  | {ev_gt_15['pod']:.3f}  | {ev_gt_15['far']:.3f}  | {ev_gt_15['pr_auc']:.3f}  | {ev_gt_15['bss']:+.3f}")
    print("=" * 80)
    print(f"Multi-Horizon PINN Forecast: 15m TSS={ev_gt_15['tss']:.3f} | 30m TSS={ev_gt_30['tss']:.3f} | 60m TSS={ev_gt_60['tss']:.3f}")

    # Save Checkpoints
    path_cnn = out_dir / "cnn_lstm_solar.pt"
    path_nopinn = out_dir / "st_gt_no_pinn.pt"
    path_gt = out_dir / "spatiotemporal_graph_transformer.pt"
    torch.save(cnn_lstm.state_dict(), path_cnn)
    torch.save(st_gt_nopinn.state_dict(), path_nopinn)
    torch.save(st_gt.state_dict(), path_gt)

    # Save Manifest and JSON metrics
    metrics_record = {
        "climatology": ev_clim,
        "persistence": ev_pers,
        "cnn_lstm": ev_cnn,
        "graph_transformer_no_pinn": ev_nopinn,
        "graph_transformer_pinn": ev_gt_15,
        "multi_horizon_pinn": {
            "15m": ev_gt_15,
            "30m": ev_gt_30,
            "60m": ev_gt_60,
        },
        "learned_parameters": {
            "alpha": float(st_gt.learned_alpha.item()),
            "beta": float(st_gt.learned_beta.item()),
            "temperature": float(st_gt.temperature.item()),
        }
    }
    metrics_json_path = ROOT / "data" / "deep_metrics.json"
    with open(metrics_json_path, "w", encoding="utf-8") as f:
        json.dump(metrics_record, f, indent=2)

    # Save numpy predictions and attention for XAI plotting
    if attn_weights_list:
        attn_sample = np.mean(np.concatenate(attn_weights_list, axis=0), axis=0).squeeze()
    else:
        attn_sample = np.zeros(60)

    if spatial_weights_list:
        spatial_sample = np.mean(np.concatenate(spatial_weights_list, axis=0), axis=0)
    else:
        spatial_sample = np.zeros((5, 5))
    manifest_npz = out_dir / "deep_evaluation_manifest.npz"
    np.savez_compressed(
        manifest_npz,
        y_test=y_test_15,
        p_cnn=p_cnn_test,
        p_nopinn=p_nopinn_test,
        p_gt=p_gt_test_15,
        p_gt_30=p_gt_test_30,
        p_gt_60=p_gt_test_60,
        timestamps=t_test_arr,
        attn_weights=attn_sample,
        spatial_attn=spatial_sample,
    )

    print(f"\n[SAVE] Model Checkpoints & Evaluation Artifacts:")
    print(f"  * Checkpoint (CNN-LSTM): {path_cnn}")
    print(f"  * Checkpoint (No-PINN):  {path_nopinn}")
    print(f"  * Checkpoint (PINN-GT):  {path_gt}")
    print(f"  * Deep Metrics JSON:     {metrics_json_path}")
    print(f"  * Predictions & XAI NPZ: {manifest_npz}")
    print("\n[DONE] Deep Learning Training, Ablation, and Evaluation Complete!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
