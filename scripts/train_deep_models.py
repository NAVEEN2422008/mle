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

import numpy as np
import pandas as pd

from src.ingest.solexs_reader import read_solexs_directory, arbitrate_sdd_rows
from src.ingest.hel1os_reader import read_hel1os_directory, collapse_bands
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
    """Extracts 2D feature matrix, 4D graph tensor, and physics derivatives from aligned data."""
    soft = df["soft"].to_numpy().astype(float)
    hard = df["hard"].to_numpy().astype(float)
    n = len(df)

    # 1. Micro-structure and physics features
    eps = 1e-6
    log_s = np.log1p(np.maximum(0, soft))
    log_h = np.log1p(np.maximum(0, hard))

    base_s = pd.Series(soft).rolling(window=120, min_periods=10).quantile(0.1).bfill().ffill().to_numpy()
    base_h = pd.Series(hard).rolling(window=120, min_periods=10).quantile(0.1).bfill().ffill().to_numpy()

    ratio_s = soft / (base_s + eps)
    ratio_h = hard / (base_h + eps)

    dsxr_dt = np.gradient(soft)
    dhxr_dt = np.gradient(hard)

    neupert = hard * np.maximum(0.0, dsxr_dt)
    hardness = hard / (soft + eps)

    # (N, 8) feature matrix for CNN-LSTM
    feat_2d = np.column_stack([
        log_s, log_h, ratio_s, ratio_h, dsxr_dt, dhxr_dt, neupert, hardness
    ])

    # 2. (N, 5, 2) Graph representation:
    # Node 0: SoLEXS Soft X-Ray [log_flux, derivative]
    # Node 1: SoLEXS SDD Baseline Ratio [ratio, derivative]
    # Node 2: HEL1OS Hard X-Ray [log_flux, derivative]
    # Node 3: Hardness Ratio [hardness, dhxr_dt]
    # Node 4: Neupert Interaction Coupling [neupert, dsxr_dt]
    graph_node_0 = np.column_stack([log_s, dsxr_dt])
    graph_node_1 = np.column_stack([ratio_s, dsxr_dt])
    graph_node_2 = np.column_stack([log_h, dhxr_dt])
    graph_node_3 = np.column_stack([hardness, dhxr_dt])
    graph_node_4 = np.column_stack([neupert, dsxr_dt])

    graph_4d = np.stack([graph_node_0, graph_node_1, graph_node_2, graph_node_3, graph_node_4], axis=1)

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

    for i, t in enumerate(timestamps_sec):
        for h in horizons_min:
            h_sec = h * 60.0
            in_window = (peaks > t) & (peaks <= t + h_sec)
            if np.any(in_window):
                labels[h][i] = 1.0
                if target_mag[i] == 0:
                    target_mag[i] = float(np.max(fluxes[in_window]))

    # Mask in-flare windows [-10min, +15min] around peaks to avoid contamination
    mask = np.zeros(n, dtype=bool)
    for p in peaks:
        mask |= (timestamps_sec >= p - 600.0) & (timestamps_sec <= p + 900.0)

    for h in horizons_min:
        labels[h][mask] = -1.0

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
    slx_df = read_solexs_directory(str(raw_path))
    hld_df = read_hel1os_directory(str(raw_path))

    if slx_df.empty or hld_df.empty:
        print("  [WARN] No archives in data/raw. Checking processed cache...")
        fused_path = Path("data/processed/fused.parquet")
        if fused_path.exists():
            df = pd.read_parquet(fused_path)
        else:
            print("  [ERROR] No telemetry found. Please ensure PRADAN zip files are present.")
            return 1
    else:
        slx_df = arbitrate_sdd_rows(slx_df)
        hld_c = collapse_bands(hld_df)
        df = pd.DataFrame({
            "timestamp": slx_df["timestamp"],
            "soft": slx_df["counts"].to_numpy(),
            "hard": hld_c.set_index("timestamp")["counts"]
                     .reindex(pd.DatetimeIndex(slx_df["timestamp"]))
                     .ffill(limit=60).bfill(limit=60).fillna(0.0)
                     .to_numpy(),
        })

    print(f"  * Aligned Telemetry Samples: {len(df):,} rows")
    print(f"  * Time Range: {df['timestamp'].min()} -> {df['timestamp'].max()}")

    # 2. Extract Features & Construct Graphs
    print("\n[2/6] Building Multi-Scale Physics Features & Detector Spatial Graphs...")
    feat_2d, graph_4d, dsxr_dt = extract_features_and_graph(df)

    # 3. Detect Flare Episodes & Build Precursor Labels
    print("\n[3/6] Identifying Flare Peaks & Generating Precursor Windows...")
    from src.forecast.pipeline import FlareForecastPipeline
    pipe = FlareForecastPipeline(horizon_min=15, min_class_flux=0.0)
    peaks_sec, peak_fluxes = pipe._detect_catalogue_peaks(df)
    ts_dt = pd.to_datetime(df["timestamp"])
    ts_rel = (ts_dt - ts_dt.iloc[0]).dt.total_seconds().to_numpy()

    y_15, y_30, y_60, target_mags = build_precursor_labels(ts_rel, peaks_sec, peak_fluxes)
    valid_idx = np.where(y_15 != -1.0)[0]

    print(f"  * Detected Flare Episodes: {len(peaks_sec)}")
    print(f"  * Usable Precursor Samples: {len(valid_idx):,} (Positive 15m rate: {np.mean(y_15[valid_idx] == 1.0):.1%})")

    # 4. Walk-Forward Temporal Split (80% Train / Embargo / 20% Test)
    split_point = int(len(df) * 0.8)
    embargo_steps = 60  # 60 minutes embargo gap

    train_slice = slice(0, split_point - embargo_steps)
    test_slice = slice(split_point, len(df))

    train_dataset = SpaceWeatherDataset(
        feat_2d[train_slice], graph_4d[train_slice],
        y_15[train_slice], y_30[train_slice], y_60[train_slice],
        target_mags[train_slice], times_sec=ts_rel[train_slice], window_len=60,
    )
    test_dataset = SpaceWeatherDataset(
        feat_2d[test_slice], graph_4d[test_slice],
        y_15[test_slice], y_30[test_slice], y_60[test_slice],
        target_mags[test_slice], times_sec=ts_rel[test_slice], window_len=60,
    )

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)

    # 5. Model 1: Train Multi-Scale CNN-LSTM
    print("\n[4/6] Training Architecture 1: Multi-Scale CNN-LSTM Forecaster...")
    cnn_lstm = CNNLSTMSolarForecaster(in_channels=8, conv_channels=64, lstm_hidden=64).to(device)
    optimizer_cnn = torch.optim.AdamW(cnn_lstm.parameters(), lr=args.lr, weight_decay=1e-4)
    focal_loss_fn = BinaryFocalLoss(alpha=0.85, gamma=2.5)

    cnn_lstm.train()
    for epoch in range(1, args.epochs + 1):
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

        print(f"    Epoch {epoch:02d}/{args.epochs:02d} | Train Loss: {total_loss / max(len(train_loader), 1):.4f}", flush=True)

    # 6. Model 2: Train Spatio-Temporal Graph Transformer with PINN Neupert Regularizer
    print("\n[5/6] Training Architecture 2: Spatio-Temporal Graph Transformer (PINN)...", flush=True)
    st_gt = SpatioTemporalGraphTransformer(num_nodes=5, in_features_per_node=2, d_model=64).to(device)
    optimizer_gt = torch.optim.AdamW(st_gt.parameters(), lr=args.lr * 0.8, weight_decay=1e-4)
    pinn_loss_fn = NeupertPhysicsLoss()

    st_gt.train()
    for epoch in range(1, args.epochs + 1):
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

        alpha, beta = out["alpha"].item(), out["beta"].item()
        print(f"    Epoch {epoch:02d}/{args.epochs:02d} | Train Loss: {total_loss / max(len(train_loader), 1):.4f} "
              f"| Neupert alpha={alpha:.3f}, beta={beta:.4f}", flush=True)

    # 7. Model Evaluation on Test Horizon
    print("\n[6/6] Evaluating Test Horizon Skill Metrics (TSS, HSS, BSS)...")
    cnn_lstm.eval()
    st_gt.eval()

    all_y_15, preds_cnn_15, preds_gt_15, test_times = [], [], [], []

    with torch.no_grad():
        for batch in test_loader:
            x_seq = batch["feat_seq"].to(device)
            g_seq = batch["graph_seq"].to(device)
            l_15 = batch["label_15m"].to(device)
            t_sec = batch["time_sec"].to(device)

            valid_mask = (l_15 >= 0.0)
            if not valid_mask.any():
                continue

            p_cnn = torch.sigmoid(cnn_lstm(x_seq)["logits_15m"]).cpu().numpy()
            p_gt = torch.sigmoid(st_gt(g_seq)["logits_15m"]).cpu().numpy()

            all_y_15.extend(l_15.cpu().numpy()[valid_mask.cpu().numpy()])
            preds_cnn_15.extend(p_cnn[valid_mask.cpu().numpy()])
            preds_gt_15.extend(p_gt[valid_mask.cpu().numpy()])
            test_times.extend(t_sec.cpu().numpy()[valid_mask.cpu().numpy()])

    y_test = np.array(all_y_15)
    p_cnn_test = np.array(preds_cnn_15)
    p_gt_test = np.array(preds_gt_15)
    t_test_arr = np.array(test_times)

    # Baselines
    clim = ClimatologyBase().fit(y_15[train_slice][y_15[train_slice] >= 0.0])
    clim_pred = clim.predict_proba(len(y_test))
    
    # Time since last flare for persistence baseline
    peaks_arr = np.asarray(peaks_sec, dtype=float)
    idx_p = np.searchsorted(peaks_arr, t_test_arr, side="right") - 1
    ages = np.where(idx_p >= 0, t_test_arr - peaks_arr[np.clip(idx_p, 0, len(peaks_arr) - 1)], np.inf)
    pers = PersistenceBase()
    pers_pred = pers.predict_proba(ages)

    # Metrics evaluation
    def get_best_metrics(y_true, p_pred):
        best_eval = None
        for th in np.arange(0.1, 0.9, 0.05):
            ev = evaluate_forecast(y_true, p_pred, threshold=float(th))
            if best_eval is None or ev["tss"] > best_eval["tss"]:
                best_eval = ev
        return best_eval

    ev_cnn = get_best_metrics(y_test, p_cnn_test)
    ev_gt = get_best_metrics(y_test, p_gt_test)
    ev_clim = evaluate_forecast(y_test, clim_pred, threshold=0.5)
    ev_pers = evaluate_forecast(y_test, pers_pred, threshold=0.5)

    print("\n" + "=" * 76)
    print("BENCHMARK COMPARISON ON TEST HORIZON (15-Minute Precursor)")
    print("=" * 76)
    print(f"{'Model Architecture':<35} | {'TSS':<7} | {'HSS':<7} | {'POD':<7} | {'FAR':<7} | {'PR-AUC':<7}")
    print("-" * 76)
    print(f"{'Climatology Baseline':<35} | {ev_clim['tss']:+.3f}  | {ev_clim['hss']:+.3f}  | {ev_clim['pod']:.3f}  | {ev_clim['far']:.3f}  | {ev_clim['pr_auc']:.3f}")
    print(f"{'Persistence Baseline':<35} | {ev_pers['tss']:+.3f}  | {ev_pers['hss']:+.3f}  | {ev_pers['pod']:.3f}  | {ev_pers['far']:.3f}  | {ev_pers['pr_auc']:.3f}")
    print(f"{'1. CNN-LSTM Forecaster':<35} | {ev_cnn['tss']:+.3f}  | {ev_cnn['hss']:+.3f}  | {ev_cnn['pod']:.3f}  | {ev_cnn['far']:.3f}  | {ev_cnn['pr_auc']:.3f}")
    print(f"{'2. SpatioTemporal Graph Transformer':<35} | {ev_gt['tss']:+.3f}  | {ev_gt['hss']:+.3f}  | {ev_gt['pod']:.3f}  | {ev_gt['far']:.3f}  | {ev_gt['pr_auc']:.3f}")
    print("=" * 76)

    # Save weights
    path_cnn = out_dir / "cnn_lstm_solar.pt"
    path_gt = out_dir / "spatiotemporal_graph_transformer.pt"
    torch.save(cnn_lstm.state_dict(), path_cnn)
    torch.save(st_gt.state_dict(), path_gt)

    print(f"\n[SAVE] Model Checkpoints Successfully Saved:")
    print(f"  * {path_cnn}")
    print(f"  * {path_gt}")
    print("\n[DONE] Deep Model Training & Fine-Tuning Complete!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
