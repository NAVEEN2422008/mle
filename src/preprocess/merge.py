"""Multi-instrument temporal synchronization and light-travel-time (LTT) correction.

Aligns Aditya-L1 (SoLEXS, HEL1OS) and reference observatories (GOES) to a synchronized
temporal cadence, accounting for the +5.0s L1-to-Earth light-travel-time difference.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

from ..types import Instrument, QCFlag
from ..constants import LTT_OFFSET_ADITYA_L1_S, MERGE_DEFAULTS


def apply_light_travel_time_correction(df: pd.DataFrame, instrument: str) -> pd.DataFrame:
    """
    Apply light-travel-time correction to align all observations to the Earth frame.
    Photons reach Aditya-L1 at Sun-Earth L1 (~1.5M km upstream) ~5.0 seconds before Earth.
    """
    if df.empty:
        return df

    out = df.copy()
    inst = instrument.upper()
    if "L1" in inst or "ADITYA" in inst or "SOLEXS" in inst or "HEL1OS" in inst:
        offset_s = LTT_OFFSET_ADITYA_L1_S  # +5.0 s
    elif "SOLAR_ORBITER" in inst or "STIX" in inst:
        offset_s = 249.0
    elif "STEREO" in inst:
        offset_s = 20.0
    elif "PARKER" in inst:
        offset_s = 476.0
    else:
        offset_s = 0.0

    out["timestamp"] = pd.to_datetime(out["timestamp"]) + pd.Timedelta(seconds=offset_s)
    out["ltt_offset_s"] = offset_s
    return out


def despike_mad_series(
    series: pd.Series,
    window_size: int = 15,
    threshold_sigma: float = 4.5,
) -> pd.Series:
    """
    Hampel / Median Absolute Deviation (MAD) despiking filter.
    Identifies and replaces isolated single-point cosmic ray particle hits with local median.
    
    Robust against outliers without attenuating genuine flare rise profiles.
    MAD = median(|x_i - median(X)|), sigma_est = 1.4826 * MAD.
    """
    if len(series) < window_size or series.isna().all():
        return series

    out = series.copy()
    rolling_med = out.rolling(window_size, min_periods=3, center=True).median()
    abs_diff = (out - rolling_med).abs()
    rolling_mad = abs_diff.rolling(window_size, min_periods=3, center=True).median()
    
    # 1.4826 scaling relates MAD to standard deviation for Gaussian noise
    sigma_est = 1.4826 * rolling_mad
    effective_sigma = np.maximum(sigma_est.fillna(0.0), 1e-3)
    spike_mask = abs_diff > (threshold_sigma * effective_sigma)
    
    # Replace detected cosmic ray spikes with the rolling median
    out[spike_mask] = rolling_med[spike_mask]
    return out


def interpolate_pchip_series(series: pd.Series, max_gap_steps: int = 180) -> pd.Series:
    """
    Monotonic Piecewise Cubic Hermite Interpolating Polynomial (PCHIP).
    Fills gaps <= max_gap_steps without introducing artificial oscillations or overshoots.
    Gaps larger than max_gap_steps are preserved as NaN to prevent fabricating data across outages.
    """
    vals_arr = series.to_numpy(dtype=float)
    valid_mask = ~np.isnan(vals_arr)
    if valid_mask.sum() < 2:
        return series

    # Identify contiguous gap lengths
    mask_series = pd.Series(valid_mask, index=series.index)
    gap_sizes = (~mask_series).astype(int).groupby(mask_series.cumsum()).transform("sum").to_numpy()
    valid_idx = np.where(valid_mask)[0]
    valid_vals = vals_arr[valid_mask]

    pchip = PchipInterpolator(valid_idx, valid_vals, extrapolate=False)
    all_idx = np.arange(len(series))
    interpolated = pchip(all_idx)

    # Re-apply NaNs to gaps that exceed the threshold
    oversized = (~valid_mask) & (gap_sizes > max_gap_steps)
    interpolated[oversized] = np.nan
    return pd.Series(interpolated, index=series.index)


def synchronize_timestamps(
    solexs_df: Optional[pd.DataFrame] = None,
    hel1os_df: Optional[pd.DataFrame] = None,
    goes_df: Optional[pd.DataFrame] = None,
    cadence_s: int = 1,
    max_gap_s: int = 180,
    apply_despike: bool = True,
) -> pd.DataFrame:
    """
    Synchronize multi-instrument streams onto a uniform cadence grid with LTT correction.
    
    Processing Steps:
    1. Light-Travel-Time (LTT) alignment to Earth frame (+5.0s for Aditya-L1).
    2. Cosmic-ray despiking via rolling Median Absolute Deviation (MAD).
    3. Outer merge along timestamp axis.
    4. Resample to target cadence (e.g. 1s or 60s).
    5. Monotonic PCHIP interpolation across small telemetry gaps <= max_gap_s.
    """
    dfs: List[pd.DataFrame] = []

    if solexs_df is not None and not solexs_df.empty:
        s_df = apply_light_travel_time_correction(solexs_df, "ADITYA_L1")
        col_map = {}
        for c in ["counts", "flux", "rate", "soft_flux"]:
            if c in s_df.columns:
                col_map[c] = "soft"
                break
        s_df = s_df.rename(columns=col_map)
        if "soft" in s_df.columns:
            if apply_despike:
                s_df["soft"] = despike_mad_series(pd.Series(s_df["soft"]))
            dfs.append(s_df[["timestamp", "soft"]].drop_duplicates(subset=["timestamp"]))

    if hel1os_df is not None and not hel1os_df.empty:
        h_df = apply_light_travel_time_correction(hel1os_df, "ADITYA_L1")
        col_map = {}
        for c in ["counts", "flux", "rate", "hard_flux"]:
            if c in h_df.columns:
                col_map[c] = "hard"
                break
        h_df = h_df.rename(columns=col_map)
        if "hard" in h_df.columns:
            if apply_despike:
                h_df["hard"] = despike_mad_series(pd.Series(h_df["hard"]))
            dfs.append(h_df[["timestamp", "hard"]].drop_duplicates(subset=["timestamp"]))

    if goes_df is not None and not goes_df.empty:
        g_df = apply_light_travel_time_correction(goes_df, "GOES")
        # Keep distinct GOES reference channels
        if "flux_long" in g_df.columns and "flux_short" in g_df.columns:
            g_df["goes_soft"] = g_df["flux_long"] * 1e9
            g_df["goes_hard"] = g_df["flux_short"] * 1e12
            if apply_despike:
                g_df["goes_soft"] = despike_mad_series(pd.Series(g_df["goes_soft"]))
                g_df["goes_hard"] = despike_mad_series(pd.Series(g_df["goes_hard"]))
            dfs.append(g_df[["timestamp", "goes_soft", "goes_hard"]].drop_duplicates(subset=["timestamp"]))
        elif "soft" in g_df.columns and "hard" in g_df.columns:
            dfs.append(g_df[["timestamp", "soft", "hard"]].drop_duplicates(subset=["timestamp"]))

    if not dfs:
        return pd.DataFrame()

    # Outer merge along timestamps
    merged = dfs[0]
    for other in dfs[1:]:
        merged = pd.merge(merged, other, on="timestamp", how="outer")

    merged = merged.sort_values("timestamp").reset_index(drop=True)

    # Resample to uniform grid
    merged = merged.set_index("timestamp")
    grid_freq = f"{cadence_s}s"
    resampled = merged.resample(grid_freq).mean()

    # Fallback fill: if primary Aditya-L1 soft/hard are missing, fill from GOES reference
    if "soft" not in resampled.columns and "goes_soft" in resampled.columns:
        resampled["soft"] = resampled["goes_soft"]
    elif "soft" in resampled.columns and "goes_soft" in resampled.columns:
        resampled["soft"] = resampled["soft"].fillna(resampled["goes_soft"])

    if "hard" not in resampled.columns and "goes_hard" in resampled.columns:
        resampled["hard"] = resampled["goes_hard"]
    elif "hard" in resampled.columns and "goes_hard" in resampled.columns:
        resampled["hard"] = resampled["hard"].fillna(resampled["goes_hard"])

    # Monotonic PCHIP interpolation over small gaps
    max_steps = int(max_gap_s / max(cadence_s, 1))
    for col in resampled.columns:
        if resampled[col].dtype.kind in "fc":
            resampled[col] = interpolate_pchip_series(resampled[col], max_gap_steps=max_steps)

    return resampled.reset_index()